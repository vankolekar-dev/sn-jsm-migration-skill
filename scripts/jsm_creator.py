#!/usr/bin/env python3
"""
jsm_creator.py — Create JSM custom fields, request types, and automation rules
from a parsed ServiceNow migration JSON (output of sn_xml_parser.py).

Usage:
    python3 scripts/jsm_creator.py \
        --input migration.json \
        --site https://ps-se-demo.atlassian-us-gov-mod.net \
        --email your@email.com --token YOUR_TOKEN \
        --project ITO [--dry-run] [--verbose]
        [--skip-fields] [--skip-rt] [--skip-auto] [--only-summary]
"""

import argparse, base64, json, sys, time
from pathlib import Path
try:
    import urllib.request as urlreq
    import urllib.error as urlerr
except ImportError:
    pass

FIELD_TYPE_MAP = {
    "Text field (single line)": "com.atlassian.jira.plugin.system.customfieldtypes:textfield",
    "Text field (multi-line)": "com.atlassian.jira.plugin.system.customfieldtypes:textarea",
    "Select list": "com.atlassian.jira.plugin.system.customfieldtypes:select",
    "Date picker": "com.atlassian.jira.plugin.system.customfieldtypes:datepicker",
    "Number": "com.atlassian.jira.plugin.system.customfieldtypes:float",
    "Checkbox": "com.atlassian.jira.plugin.system.customfieldtypes:multicheckboxes",
    "User picker": "com.atlassian.jira.plugin.system.customfieldtypes:userpicker",
    "URL": "com.atlassian.jira.plugin.system.customfieldtypes:url",
}

class JSMClient:
    def __init__(self, site, email, token, dry_run=False, verbose=False):
        self.site = site.rstrip("/")
        self.dry_run = dry_run
        self.verbose = verbose
        creds = base64.b64encode(f"{email}:{token}".encode()).decode()
        self.headers = {"Authorization": f"Basic {creds}",
                        "Content-Type": "application/json", "Accept": "application/json"}
        self.created, self.skipped, self.errors = [], [], []

    def _req(self, method, path, body=None):
        url = f"{self.site}{path}"
        data = json.dumps(body).encode() if body else None
        req = urlreq.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urlreq.urlopen(req, timeout=30) as r:
                content = r.read().decode()
                return json.loads(content) if content else {}
        except urlerr.HTTPError as e:
            msg = e.read().decode()[:300]
            if self.verbose: print(f"  ⚠️  HTTP {e.code} {method} {path}: {msg}", file=sys.stderr)
            raise

    def get(self, path): return self._req("GET", path)

    def post(self, path, body):
        if self.dry_run:
            print(f"  [DRY-RUN] POST {path}\n  {json.dumps(body,indent=4)[:300]}")
            return {"id":"dry-run"}
        return self._req("POST", path, body)

    def ok(self, res, name, url=""):
        self.created.append({"resource":res,"name":name})
        print(f"  ✅ {res}: {name}" + (f" → {url}" if url else ""))

    def skip(self, res, name, why="exists"):
        self.skipped.append({"resource":res,"name":name})
        print(f"  ⏭️  Skip {res}: {name} ({why})")

    def err(self, res, name, e):
        self.errors.append({"resource":res,"name":name,"error":str(e)})
        print(f"  ❌ {res}: {name} — {e}", file=sys.stderr)

def create_custom_fields(client, mapping):
    fields = mapping.get("custom_fields", [])
    if not fields: return {}
    print(f"\n🔧 Creating {len(fields)} custom field(s)...")
    field_map = {}
    try:
        existing = {f["name"].lower(): f["id"] for f in client.get("/rest/api/3/field")}
    except Exception: existing = {}
    for f in fields:
        name = f.get("name","")
        if not name: continue
        if name.lower() in existing:
            field_map[name] = existing[name.lower()]
            client.skip("Custom Field", name, f"exists as {existing[name.lower()]}")
            continue
        ftype = f.get("jsm_field_type","Text field (single line)")
        type_key = FIELD_TYPE_MAP.get(ftype, FIELD_TYPE_MAP["Text field (single line)"])
        try:
            r = client.post("/rest/api/3/field", {"name": name, "type": type_key})
            field_map[name] = r.get("id","?")
            client.ok("Custom Field", name)
        except Exception as e: client.err("Custom Field", name, e)
    return field_map

def get_sd_id(client, project_key):
    try:
        r = client.get("/rest/servicedeskapi/servicedesk")
        for sd in r.get("values",[]):
            if sd.get("projectKey") == project_key: return str(sd["id"])
    except Exception as e:
        print(f"  ⚠️  Could not list service desks: {e}", file=sys.stderr)
    return None

def create_request_types(client, project_key, mapping):
    rts = mapping.get("request_types",[])
    if not rts: return
    sd_id = get_sd_id(client, project_key)
    if not sd_id:
        print(f"  ⚠️  No service desk for {project_key} — skipping request types"); return
    print(f"\n📝 Creating {len(rts)} request type(s) in {project_key}...")
    try:
        existing = {rt["name"].lower() for rt in
                    client.get(f"/rest/servicedeskapi/servicedesk/{sd_id}/requesttype?limit=100").get("values",[])}
    except Exception: existing = set()
    for rt in rts:
        name = rt.get("name","")
        if not name: continue
        if name.lower() in existing: client.skip("Request Type", name); continue
        try:
            client.post(f"/rest/servicedeskapi/servicedesk/{sd_id}/requesttype",
                        {"name":name,"description":rt.get("description",f"Migrated: {name}"),"helpText":""})
            client.ok("Request Type", name,
                      f"{client.site}/jira/servicedesk/projects/{project_key}/settings/requesttypes")
        except Exception as e: client.err("Request Type", name, e)

TRIGGER_MAP = {
    "Issue created": "ISSUE_CREATED", "Issue updated": "ISSUE_UPDATED",
    "Issue created or updated": "ISSUE_CREATED_OR_UPDATED",
    "Scheduled": "SCHEDULED", "Manual trigger": "MANUAL",
}

def build_auto_json(rule, project_key):
    trigger_type = TRIGGER_MAP.get(rule.get("trigger","Issue created"), "ISSUE_CREATED")
    components = [{"component":"TRIGGER","type":trigger_type,"value":{},"children":[],"conditions":[]}]
    for cond in rule.get("conditions",[])[:3]:
        components.append({
            "component":"CONDITION","type":"FIELD_CONDITION",
            "value":{"field":{"type":"issue","value":"summary"},"comparator":"CONTAINS",
                     "compareValue":{"type":"free","value":cond[:50]}},
            "children":[],"conditions":[]
        })
    for action in rule.get("actions",[])[:5]:
        clean = action.lstrip("→ ").strip()
        atype = "SEND_EMAIL" if "email" in clean.lower() else \
                "CREATE_ISSUE" if "sub-task" in clean.lower() else "COMMENT"
        val = {"comment": f"Automated: {clean}", "internal": False} if atype == "COMMENT" else {}
        components.append({"component":"ACTION","type":atype,"value":val,"children":[],"conditions":[]})
    return {"name":rule.get("name","Migrated Rule"),"state":"DISABLED",
            "projects":[{"projectKey":project_key}],"components":components}

def create_automation_rules(client, project_key, mapping):
    rules = mapping.get("automation_rules",[])
    if not rules: return
    print(f"\n🤖 Creating {len(rules)} automation rule(s)...")
    for rule in rules:
        name = rule.get("name","Migrated Rule")
        auto_json = build_auto_json(rule, project_key)
        safe = name.lower().replace(" ","_").replace("[","").replace("]","")[:40]
        out = Path(f"/tmp/jsm_rule_{safe}.json")
        out.write_text(json.dumps({"rules":[auto_json]}, indent=2))
        print(f"  💾 Import file: {out}")
        try:
            client.post(f"/rest/cb-automation/latest/projects/{project_key}/rules", auto_json)
            client.ok("Automation Rule", name,
                      f"{client.site}/jira/servicedesk/projects/{project_key}/settings/automate")
        except Exception as e:
            es = str(e)
            if any(c in es for c in ["401","403","404"]):
                print(f"  ⚠️  API blocked — import manually: Project Settings → Automation → Import rules")
                print(f"      File: {out}")
            else: client.err("Automation Rule", name, e)

def print_plan(migration):
    m = migration.get("jsm_mapping",{})
    print(f"\n{'━'*60}\n  📋 MIGRATION PLAN: {migration.get('name','?')}")
    print(f"  Type: {migration.get('source_type','?').upper()} | "
          f"Recommended: {m.get('recommended_project_type','?')}")
    t = migration.get("trigger",{})
    print(f"  Trigger: {t.get('jsm_equivalent',t.get('type','—'))}")
    print(f"{'━'*60}")
    steps = migration.get("steps",[])
    ICONS = {"approval":"✔️","condition":"🔀","action":"⚙️","notification":"📧","script":"📝","subflow":"🔗"}
    print(f"\n📊 Steps ({len(steps)}):")
    for s in steps[:12]:
        print(f"  {ICONS.get(s['type'],'•')} [{s['type'].upper():<12}] {s['label']:<30} → {s.get('jsm_equivalent','—')}")
    if len(steps)>12: print(f"  ... +{len(steps)-12} more")
    for apr in migration.get("approvals",[]):
        print(f"  ✔️  Approval: {apr['stage']} — approver: {apr.get('approver','—')}")
    if m.get("custom_fields"):
        print(f"\n🔧 Custom Fields ({len(m['custom_fields'])}):")
        for f in m["custom_fields"]:
            print(f"  • {f['name']} [{f['jsm_field_type']}]{'  ✱req' if f.get('mandatory') else ''}")
    if m.get("request_types"):
        print(f"\n📝 Request Types ({len(m['request_types'])}):")
        for rt in m["request_types"]: print(f"  • {rt['name']}")
    if m.get("automation_rules"):
        print(f"\n🤖 Automation Rules ({len(m['automation_rules'])}):")
        for r in m["automation_rules"]:
            print(f"  • {r['name']} | Trigger: {r['trigger']}")
    print(f"\n{'━'*60}")

def main():
    p = argparse.ArgumentParser(description="Create JSM resources from SN migration JSON")
    p.add_argument("--input","-i",required=True)
    p.add_argument("--site","-s"); p.add_argument("--email","-e")
    p.add_argument("--token","-t"); p.add_argument("--project","-p")
    p.add_argument("--dry-run",action="store_true")
    p.add_argument("--only-summary",action="store_true")
    p.add_argument("--skip-fields",action="store_true")
    p.add_argument("--skip-rt",action="store_true")
    p.add_argument("--skip-auto",action="store_true")
    p.add_argument("--verbose","-v",action="store_true")
    args = p.parse_args()
    migration = json.loads(Path(args.input).read_text())
    print_plan(migration)
    if args.only_summary: return
    if not all([args.site,args.email,args.token,args.project]):
        print("ERROR: --site --email --token --project required",file=sys.stderr); sys.exit(1)
    client = JSMClient(args.site,args.email,args.token,args.dry_run,args.verbose)
    mapping = migration.get("jsm_mapping",{})
    print(f"\n🚀 {'DRY RUN — ' if args.dry_run else ''}Creating in {args.project} @ {args.site}\n")
    if not args.skip_fields: create_custom_fields(client, mapping); time.sleep(0.3)
    if not args.skip_rt: create_request_types(client, args.project, mapping); time.sleep(0.3)
    if not args.skip_auto: create_automation_rules(client, args.project, mapping)
    print(f"\n{'='*50}\n✅ Created: {len(client.created)} | ⏭️ Skipped: {len(client.skipped)} | ❌ Errors: {len(client.errors)}")
    for e in client.errors: print(f"  ❌ {e['resource']} '{e['name']}': {e['error']}")
    print("="*50)

if __name__ == "__main__":
    main()
