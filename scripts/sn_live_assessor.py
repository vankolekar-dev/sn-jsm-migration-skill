#!/usr/bin/env python3
"""
sn_live_assessor.py — Live ServiceNow REST API Assessment Tool

Connects directly to a live ServiceNow instance via REST API and performs
a full pre-migration assessment without needing XML exports. Produces the
same assessment JSON and markdown report as sn_assessor.py.

Usage:
    python3 scripts/sn_live_assessor.py \\
        --instance https://dev317128.service-now.com \\
        --user admin --password YOUR_PASSWORD \\
        --report live-assessment.md

    # Scope to specific tables/apps only
    python3 scripts/sn_live_assessor.py \\
        --instance https://dev317128.service-now.com \\
        --user admin --password YOUR_PASSWORD \\
        --scope incident,change_request,sc_cat_item \\
        --report scoped-assessment.md

    # JSON output only
    python3 scripts/sn_live_assessor.py \\
        --instance https://dev317128.service-now.com \\
        --user admin --password YOUR_PASSWORD \\
        --json-only
"""

import argparse, base64, getpass, hashlib, json, re, subprocess, sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from sn_complexity_scorer import score_complexity
    from sn_report_generator import generate_report
except ImportError:
    def score_complexity(pl): return {"overall_risk": "UNKNOWN", "score": 0, "label": ""}
    def generate_report(a, p=None): return ""

# ── REST API Client ───────────────────────────────────────────────────────────

class OAuthConfigurationError(RuntimeError):
    """Raised when OAuth credentials cannot be loaded or used safely."""


def keychain_password(service, account=None):
    """Read a generic-password item without printing its value."""
    account = account or getpass.getuser()
    command = ["security", "find-generic-password", "-a", account, "-s", service, "-w"]
    try:
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True)
    except FileNotFoundError as exc:
        raise OAuthConfigurationError("macOS Keychain utility 'security' is unavailable") from exc
    except subprocess.CalledProcessError as exc:
        raise OAuthConfigurationError(
            f"Keychain item for service '{service}' is missing or inaccessible"
        ) from exc
    value = result.stdout.rstrip("\n")
    if not value:
        raise OAuthConfigurationError(f"Keychain item for service '{service}' is empty")
    return value


class SNClient:
    def __init__(self, instance, authorization, verbose=False):
        self.base = instance.rstrip("/")
        self.authorization = authorization
        self.verbose = verbose

    @classmethod
    def basic(cls, instance, user, password, verbose=False):
        encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
        return cls(instance, f"Basic {encoded}", verbose)

    @classmethod
    def oauth_client_credentials(cls, instance, client_id, client_secret, verbose=False):
        """Exchange OAuth client credentials for an in-memory bearer token."""
        # ServiceNow's external-client registry expects client credentials in the
        # form body for this grant. HTTPS protects the request in transit; no values
        # are included in output, exceptions, or logs.
        request = urllib.request.Request(
            f"{instance.rstrip('/')}/oauth_token.do",
            data=urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }).encode(),
            headers={"Accept": "application/json",
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise OAuthConfigurationError(
                f"OAuth token request failed with HTTP {exc.code}; verify the client, grant type, and instance"
            ) from exc
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise OAuthConfigurationError("OAuth token request failed; verify network access and ServiceNow OAuth configuration") from exc
        token = payload.get("access_token")
        if not token:
            raise OAuthConfigurationError("OAuth token response did not include an access token")
        return cls(instance, f"Bearer {token}", verbose)

    def _headers(self):
        return {"Authorization": self.authorization, "Accept": "application/json"}

    def get(self, table, fields=None, query=None, limit=500, offset=0, strict=False):
        """Read one Table API page. Strict callers receive explicit failures."""
        params = [f"sysparm_limit={limit}", f"sysparm_offset={offset}"]
        if fields:
            params.append(f"sysparm_fields={','.join(fields)}")
        if query:
            params.append(f"sysparm_query={urllib.parse.quote(query)}")
        url = f"{self.base}/api/now/table/{table}?{'&'.join(params)}"
        if self.verbose:
            print(f"  → GET /{table} (offset={offset}, limit={limit})", file=sys.stderr)
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())["result"]
        except urllib.error.HTTPError as exc:
            if strict:
                raise RuntimeError(f"Table API request for {table} failed with HTTP {exc.code}") from exc
            if self.verbose:
                print(f"  ⚠️  HTTP {exc.code} on /{table}", file=sys.stderr)
            return []
        except Exception as exc:
            if strict:
                raise RuntimeError(f"Table API request for {table} failed: {exc}") from exc
            if self.verbose:
                print(f"  ⚠️  Error on /{table}: {exc}", file=sys.stderr)
            return []

    def get_paginated(self, table, fields=None, query=None, page_size=500):
        """Read every matching record with a stable sys_id order and no silent truncation."""
        stable_query = f"{query}^ORDERBYsys_id" if query else "ORDERBYsys_id"
        records, offset = [], 0
        while True:
            page = self.get(table, fields, stable_query, limit=page_size, offset=offset, strict=True)
            records.extend(page)
            if self.verbose:
                print(f"    {table}: retrieved {len(records)} record(s)", file=sys.stderr)
            if len(page) < page_size:
                return records
            offset += len(page)

    def count(self, table, query=None):
        """Get record count via stats API."""
        params = ["sysparm_count=true", "sysparm_limit=1"]
        if query:
            params.append(f"sysparm_query={urllib.parse.quote(query)}")
        url = f"{self.base}/api/now/stats/{table}?{'&'.join(params)}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                return int(data.get("result", {}).get("stats", {}).get("count", 0))
        except Exception:
            return -1  # -1 means count unavailable


# ── Assessment Sections ───────────────────────────────────────────────────────

def assess_flows(client, deep_discovery=False):
    print("  📋 Flows / Automations...", file=sys.stderr)
    flows = get_records(client, "sys_hub_flow", ["name", "description", "active", "trigger_type"], limit=500, deep_discovery=deep_discovery)
    active = [f for f in flows if f.get("active") == "true"]
    inactive = [f for f in flows if f.get("active") != "true"]
    templates = [f for f in active if "template" in f.get("name","").lower() or "Template" in f.get("name","")]
    custom = [f for f in active if f not in templates]
    return {
        "total": len(flows),
        "active": len(active),
        "inactive": len(inactive),
        "templates": len(templates),
        "custom_active": len(custom),
        "items": [{"name": f["name"], "active": f.get("active")=="true"} for f in flows[:50]],
    }


def assess_catalog(client, deep_discovery=False):
    print("  🛒 Service Catalog...", file=sys.stderr)
    items = get_records(client, "sc_cat_item", ["name", "category", "active", "short_description"], limit=500, deep_discovery=deep_discovery)
    active = [i for i in items if i.get("active") == "true"]
    variables = get_records(client, "item_option_new", ["name", "question_text", "type", "mandatory"], limit=500, deep_discovery=deep_discovery)
    return {
        "total_items": len(items),
        "active_items": len(active),
        "total_variables": len(variables),
        "items": [{"name": i["name"], "active": i.get("active")=="true",
                   "category": i.get("category","")} for i in items[:50]],
        "variables_sample": [{"name": v.get("name",""), "type": v.get("type",""),
                               "mandatory": v.get("mandatory","")=="true"} for v in variables[:20]],
    }


SCRIPT_INDICATORS = {
    "dynamic_evaluation": re.compile(r"\beval\s*\(", re.I),
    "outbound_http": re.compile(r"\b(?:sn_ws\.)?RESTMessageV2\b|\bXMLHttpRequest\b", re.I),
    "database_access": re.compile(r"\bGlideRecord\b", re.I),
    "property_access": re.compile(r"\bgs\.getProperty\s*\(", re.I),
    "impersonation": re.compile(r"\bimpersonate\s*\(", re.I),
}


def analyze_script_source(source):
    """Return source-derived metrics only; never return or persist source text."""
    source = source or ""
    return {
        "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "line_count": source.count("\n") + (1 if source else 0),
        "byte_count": len(source.encode("utf-8")),
        "indicators": sorted(name for name, pattern in SCRIPT_INDICATORS.items() if pattern.search(source)),
    }


def get_records(client, table, fields, query=None, limit=500, deep_discovery=False):
    return (client.get_paginated(table, fields, query, page_size=limit)
            if deep_discovery else client.get(table, fields, query, limit=limit))


def assess_business_rules(client, deep_discovery=False, include_script_source=False):
    print("  ⚙️  Business Rules...", file=sys.stderr)
    fields = ["name", "collection", "when", "active"]
    if include_script_source:
        fields.append("script")
    rules = get_records(client, "sys_script", fields, limit=500, deep_discovery=deep_discovery)
    active = [r for r in rules if r.get("active") == "true"]
    custom = [r for r in active if not r.get("name","").startswith("SNC ")
              and "sample" not in r.get("name","").lower()]
    result = {
        "total": len(rules),
        "active": len(active),
        "custom_active": len(custom),
        "full_inventory": deep_discovery,
        "risk": "HIGH",
        "note": "Active business rules run server-side Groovy. Must be rewritten as Jira Automation rules.",
        "items": [{"name": r["name"], "table": r.get("collection",""),
                   "when": r.get("when","")} for r in active[:30]],
    }
    if include_script_source:
        result["source_analysis"] = [
            {"name": rule.get("name", ""), "table": rule.get("collection", ""),
             **analyze_script_source(rule.get("script", ""))}
            for rule in custom
        ]
    return result


def assess_client_scripts(client, deep_discovery=False, include_script_source=False):
    print("  🖥️  Client Scripts...", file=sys.stderr)
    fields = ["name", "type", "table", "active"]
    if include_script_source:
        fields.append("script")
    scripts = get_records(client, "sys_script_client", fields, limit=500, deep_discovery=deep_discovery)
    active = [s for s in scripts if s.get("active") == "true"]
    custom = [s for s in active if "sample" not in s.get("name","").lower()
              and not s.get("name","").startswith("SNC ")]
    result = {
        "total": len(scripts),
        "active": len(active),
        "custom_active": len(custom),
        "full_inventory": deep_discovery,
        "risk": "HIGH",
        "note": "Client scripts have no direct JSM equivalent. Use ProForma conditional logic or Forge UI Kit.",
        "by_type": {
            "onChange": len([s for s in active if s.get("type") == "onChange"]),
            "onLoad": len([s for s in active if s.get("type") == "onLoad"]),
            "onSubmit": len([s for s in active if s.get("type") == "onSubmit"]),
        },
    }
    if include_script_source:
        result["source_analysis"] = [
            {"name": script.get("name", ""), "table": script.get("table", ""),
             "type": script.get("type", ""), **analyze_script_source(script.get("script", ""))}
            for script in custom
        ]
    return result


def assess_ui_policies(client, deep_discovery=False):
    print("  🎨 UI Policies...", file=sys.stderr)
    policies = get_records(client, "sys_ui_policy", ["short_description", "table", "active"], limit=500, deep_discovery=deep_discovery)
    active = [p for p in policies if p.get("active") == "true"]
    return {
        "total": len(policies),
        "active": len(active),
        "risk": "MEDIUM",
        "note": "UI policies have limited equivalent in ProForma conditional logic (~60% coverage).",
        "items": [{"name": p.get("short_description","?"), "table": p.get("table","")}
                  for p in active[:20]],
    }


def assess_slas(client):
    print("  ⏱️  SLA Definitions...", file=sys.stderr)
    slas = client.get("contract_sla", ["name", "type", "duration", "active"], limit=200)
    active = [s for s in slas if s.get("active") == "true"]
    by_type = {}
    for s in active:
        t = s.get("type", "SLA")
        by_type[t] = by_type.get(t, 0) + 1
    return {
        "total": len(slas),
        "active": len(active),
        "by_type": by_type,
        "risk": "MEDIUM",
        "note": "SLA policies must be recreated via JSM project settings → SLAs. UI only.",
        "items": [{"name": s["name"], "type": s.get("type",""),
                   "duration": s.get("duration","")} for s in active],
    }


def assess_acls(client):
    print("  🔐 ACLs / Security Rules...", file=sys.stderr)
    acls = client.get("sys_security_acl", ["name", "operation", "active"], limit=500)
    active = [a for a in acls if a.get("active") == "true"]
    custom = [a for a in active if not a.get("name","").startswith("sysauto")
              and not a.get("name","").startswith("sys_")]
    return {
        "total": len(acls),
        "active": len(active),
        "custom_active": len(custom),
        "risk": "HIGH",
        "note": "ACLs must be mapped to JSM issue security schemes and permission schemes. Manual UI config.",
        "items": [{"name": a["name"], "operation": a.get("operation","")}
                  for a in custom[:20]],
    }


def assess_workflows(client):
    print("  🔄 Workflows (legacy)...", file=sys.stderr)
    workflows = client.get("wf_workflow", ["name", "table", "active"], limit=200)
    active = [w for w in workflows if w.get("active") == "true"]
    return {
        "total": len(workflows),
        "active": len(active),
        "risk": "MEDIUM",
        "note": "Workflow creation is UI-only in JSM Cloud. Statuses and transitions must be recreated manually.",
        "items": [{"name": w["name"], "table": w.get("table","")} for w in active[:20]],
    }


def assess_notifications(client):
    print("  📧 Email Notifications...", file=sys.stderr)
    notifs = client.get("sysevent_email_action", ["name", "event_name", "active"], limit=200)
    active = [n for n in notifs if n.get("active") == "true"]
    return {
        "total": len(notifs),
        "active": len(active),
        "risk": "LOW",
        "note": "Email notifications can be recreated as JSM automation rules with send email action.",
        "items": [{"name": n["name"], "event": n.get("event_name","")} for n in active[:20]],
    }


def service_now_value(value, default="<unclassified>"):
    """Normalize ServiceNow scalar/reference values returned as strings or objects."""
    if isinstance(value, dict):
        value = value.get("display_value") or value.get("value")
    return str(value) if value not in (None, "") else default


def assess_cmdb(client, deep_discovery=False):
    print("  🗄️  CMDB...", file=sys.stderr)
    if not deep_discovery:
        count = client.count("cmdb_ci", "active=true")
        classes_sample = client.get("cmdb_ci", ["sys_class_name"], limit=200)
        classes = sorted({c.get("sys_class_name", "") for c in classes_sample if c.get("sys_class_name")})
        return {
            "total_cis": count if count >= 0 else len(classes_sample),
            "ci_classes": classes,
            "full_inventory": False,
            "risk": "HIGH",
            "note": "Rapid sample only. Use --deep-discovery for complete CI and relationship inventory.",
        }

    cis = client.get_paginated("cmdb_ci", ["sys_id", "sys_class_name", "install_status", "operational_status"])
    relationships = client.get_paginated("cmdb_rel_ci", ["sys_id", "type", "parent", "child"])
    class_counts, relationship_type_counts = {}, {}
    for ci in cis:
        name = service_now_value(ci.get("sys_class_name"))
        class_counts[name] = class_counts.get(name, 0) + 1
    for relationship in relationships:
        relationship_type = service_now_value(relationship.get("type"), default="<untyped>")
        relationship_type_counts[relationship_type] = relationship_type_counts.get(relationship_type, 0) + 1
    return {
        "total_cis": len(cis),
        "ci_classes": sorted(class_counts),
        "class_distribution": dict(sorted(class_counts.items())),
        "relationship_total": len(relationships),
        "relationship_type_distribution": dict(sorted(relationship_type_counts.items())),
        "full_inventory": True,
        "risk": "HIGH",
        "note": "Complete paginated CMDB inventory. Map classes and relationships to a reviewed Atlassian Assets schema before import.",
    }


def assess_knowledge_base(client):
    print("  📚 Knowledge Base...", file=sys.stderr)
    count = client.count("kb_knowledge", "workflow_state=published")
    categories = client.get("kb_category", ["label", "full_category"], limit=100)
    return {
        "total_articles": count if count >= 0 else 0,
        "total_categories": len(categories),
        "risk": "MEDIUM",
        "note": "KB articles must be manually migrated to Confluence. JSM links to Confluence spaces for KB.",
        "categories": [c.get("label","") or c.get("full_category","") for c in categories[:20]],
    }


def assess_approvals(client):
    print("  ✅ Approval Definitions...", file=sys.stderr)
    # Approval rules in Flow Designer
    flow_approvals = client.get("sys_hub_action_instance",
                                ["name", "action_type", "active"],
                                query="action_type=approval", limit=200)
    return {
        "total": len(flow_approvals),
        "risk": "MEDIUM",
        "note": "Approval steps must be added to JSM workflow transitions via UI.",
        "items": [{"name": a["name"]} for a in flow_approvals[:20]],
    }


def assess_scheduled_jobs(client):
    print("  ⏰ Scheduled Jobs...", file=sys.stderr)
    jobs = client.get("sysauto_script", ["name", "active"], limit=100)
    active = [j for j in jobs if j.get("active") == "true"]
    return {
        "total": len(jobs),
        "active": len(active),
        "risk": "LOW",
        "note": "Scheduled jobs can be recreated as scheduled automation rules in JSM.",
        "items": [{"name": j["name"]} for j in active[:20]],
    }


# ── Full Instance Assessment ──────────────────────────────────────────────────

def run_live_assessment(client, instance_url, scope=None, deep_discovery=False, include_script_source=False):
    print(f"\n🔍 Connecting to: {instance_url}", file=sys.stderr)
    print(f"{'━'*60}", file=sys.stderr)

    assessment = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "instance": instance_url,
        "assessment_type": "live_api",
        "total_files": 1,
        "sections": {},
    }

    # Run all assessments
    sections = assessment["sections"]
    sections["flows"]           = assess_flows(client, deep_discovery)
    sections["catalog"]         = assess_catalog(client, deep_discovery)
    sections["business_rules"]  = assess_business_rules(client, deep_discovery, include_script_source)
    sections["client_scripts"]  = assess_client_scripts(client, deep_discovery, include_script_source)
    sections["ui_policies"]     = assess_ui_policies(client, deep_discovery)
    sections["slas"]            = assess_slas(client)
    sections["acls"]            = assess_acls(client)
    sections["workflows"]       = assess_workflows(client)
    sections["notifications"]   = assess_notifications(client)
    sections["cmdb"]            = assess_cmdb(client, deep_discovery)
    sections["knowledge_base"]  = assess_knowledge_base(client)
    sections["approvals"]       = assess_approvals(client)
    sections["scheduled_jobs"]  = assess_scheduled_jobs(client)
    assessment["discovery"] = {
        "mode": "deep" if deep_discovery else "rapid",
        "script_source_analyzed": include_script_source,
        "script_source_persisted": False,
    }

    # Build summary (matching sn_assessor.py format for scorer/reporter compatibility)
    s = sections
    assessment["summary"] = {
        "total_flows":         s["flows"]["active"],
        "total_steps":         s["flows"]["active"],
        "total_approvals":     s["approvals"]["total"],
        "total_notifications": s["notifications"]["active"],
        "total_scripts":       0,  # Flow-level scripts not enumerable via API easily
        "total_business_rules":s["business_rules"]["custom_active"],
        "total_client_scripts":s["client_scripts"]["custom_active"],
        "total_acls":          s["acls"]["custom_active"],
        "total_ui_policies":   s["ui_policies"]["active"],
        "total_catalog_items": s["catalog"]["active_items"],
        "total_custom_fields": s["catalog"]["total_variables"],
        "total_sla_definitions":s["slas"]["active"],
        "total_workflows":     s["workflows"]["active"],
        "total_ci_records":    s["cmdb"]["total_cis"],
        "total_kb_articles":   s["knowledge_base"]["total_articles"],
        "total_high_risk_items": (
            s["business_rules"]["custom_active"] +
            s["client_scripts"]["custom_active"] +
            s["acls"]["custom_active"]
        ),
        "api_migratable_count": (
            s["catalog"]["active_items"] +
            s["catalog"]["total_variables"] +
            s["notifications"]["active"] +
            s["scheduled_jobs"]["active"]
        ),
        "ui_only_count": (
            s["approvals"]["total"] +
            s["slas"]["active"] +
            s["workflows"]["active"] +
            s["ui_policies"]["active"]
        ),
        "no_equivalent_count": (
            s["business_rules"]["custom_active"] +
            s["client_scripts"]["custom_active"] +
            (1 if s["cmdb"]["total_cis"] > 0 else 0) +
            (1 if s["knowledge_base"]["total_articles"] > 0 else 0)
        ),
    }

    # Migration blockers
    assessment["migration_blockers"] = []
    bl = assessment["migration_blockers"]

    if s["business_rules"]["custom_active"] > 0:
        bl.append({"severity": "HIGH",
                   "blocker": f"{s['business_rules']['custom_active']} custom business rule(s)",
                   "action": "Must be rewritten as Jira Automation rules. No Groovy in JSM Cloud."})
    if s["client_scripts"]["custom_active"] > 0:
        bl.append({"severity": "HIGH",
                   "blocker": f"{s['client_scripts']['custom_active']} client-side script(s)",
                   "action": "No direct JSM equivalent. Use ProForma conditional logic or Forge UI Kit."})
    if s["acls"]["custom_active"] > 0:
        bl.append({"severity": "HIGH",
                   "blocker": f"{s['acls']['custom_active']} custom ACL(s)",
                   "action": "Map to JSM issue security schemes. Manual UI configuration required."})
    if s["cmdb"]["total_cis"] > 0:
        bl.append({"severity": "HIGH",
                   "blocker": f"{s['cmdb']['total_cis']} CMDB CI record(s) ({len(s['cmdb']['ci_classes'])} CI classes)",
                   "action": "Use Atlassian Assets (Insight). Requires separate schema design + CSV/API import."})
    if s["ui_policies"]["active"] > 0:
        bl.append({"severity": "MEDIUM",
                   "blocker": f"{s['ui_policies']['active']} UI policy(ies)",
                   "action": "Limited equivalent in ProForma conditional logic. ~60% coverage."})
    if s["slas"]["active"] > 0:
        bl.append({"severity": "MEDIUM",
                   "blocker": f"{s['slas']['active']} SLA policy(ies)",
                   "action": "Must be recreated via JSM project settings → SLAs. UI only."})
    if s["workflows"]["active"] > 0:
        bl.append({"severity": "MEDIUM",
                   "blocker": f"{s['workflows']['active']} legacy workflow(s)",
                   "action": "Workflow creation is UI-only in JSM Cloud. Recreate in workflow editor."})
    if s["knowledge_base"]["total_articles"] > 0:
        bl.append({"severity": "MEDIUM",
                   "blocker": f"{s['knowledge_base']['total_articles']} KB article(s)",
                   "action": "Manually migrate to Confluence. JSM links to Confluence for KB."})
    if s["approvals"]["total"] > 0:
        bl.append({"severity": "LOW",
                   "blocker": f"{s['approvals']['total']} approval stage(s)",
                   "action": "Add approval steps to JSM workflow transitions via UI."})

    # Recommended project types
    assessment["recommended_jsm_project_types"] = ["IT Service Management"]
    if s["workflows"]["active"] > 0 or s["slas"]["active"] > 0:
        assessment["recommended_jsm_project_types"].append("IT Incident Management")
    if s["cmdb"]["total_cis"] > 0:
        assessment["recommended_jsm_project_types"].append("Assets (Atlassian Insight)")
    if s["knowledge_base"]["total_articles"] > 0:
        assessment["recommended_jsm_project_types"].append("Confluence Knowledge Base")

    # Score complexity using a synthetic parsed list compatible with scorer
    synthetic_parsed = [{
        "name": instance_url,
        "source_type": "live_api",
        "scripts": [],
        "business_rules": [{"name": f"rule_{i}"} for i in range(s["business_rules"]["custom_active"])],
        "client_scripts": [{"name": f"cs_{i}"} for i in range(s["client_scripts"]["custom_active"])],
        "acls": [{"name": f"acl_{i}"} for i in range(s["acls"]["custom_active"])],
        "subflows": [],
        "ci_records": [{"name": f"ci_{i}"} for i in range(min(s["cmdb"]["total_cis"], 200))],
        "ui_policies": [{"name": f"up_{i}"} for i in range(s["ui_policies"]["active"])],
        "sla_definitions": [{"name": f"sla_{i}"} for i in range(s["slas"]["active"])],
        "workflows": [{"name": f"wf_{i}"} for i in range(s["workflows"]["active"])],
        "articles": [{"name": f"kb_{i}"} for i in range(min(s["knowledge_base"]["total_articles"], 100))],
        "approvals": [{"name": f"apr_{i}"} for i in range(s["approvals"]["total"])],
        "steps": [{"name": f"step_{i}"} for i in range(s["flows"]["active"])],
        "notifications": [{"name": f"notif_{i}"} for i in range(s["notifications"]["active"])],
        "catalog_items": [{"name": f"ci_{i}"} for i in range(s["catalog"]["active_items"])],
        "jsm_mapping": {"custom_fields": [{"name": f"f_{i}"} for i in range(s["catalog"]["total_variables"])]},
    }]
    assessment["complexity"] = score_complexity(synthetic_parsed)
    assessment["files"] = [{
        "name": instance_url,
        "file": instance_url,
        "type": "live_api",
        "steps": s["flows"]["active"],
        "approvals": s["approvals"]["total"],
        "scripts": s["business_rules"]["custom_active"] + s["client_scripts"]["custom_active"],
        "high_risk_items": assessment["summary"]["total_high_risk_items"],
        "recommended_project_type": assessment["recommended_jsm_project_types"][0],
        "api_migratable": assessment["summary"]["api_migratable_count"],
        "ui_only": assessment["summary"]["ui_only_count"],
        "no_equivalent": assessment["summary"]["no_equivalent_count"],
    }]

    return assessment


# ── Console Summary ───────────────────────────────────────────────────────────

def print_live_summary(assessment):
    s = assessment["summary"]
    c = assessment.get("complexity", {})
    risk = c.get("overall_risk", "UNKNOWN")
    score = c.get("score", 0)
    risk_icons = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "CRITICAL": "🚨", "UNKNOWN": "⚪"}
    sec = assessment["sections"]

    print(f"\n{'━'*65}")
    print(f"  🔍 ServiceNow Live Instance Assessment")
    print(f"  Instance : {assessment['instance']}")
    print(f"  Generated: {assessment['generated_at']}")
    print(f"{'━'*65}")
    print(f"\n{risk_icons.get(risk,'⚪')} MIGRATION COMPLEXITY: {risk}  (Score: {score}/100)")
    print(f"   {c.get('label','')}")
    print(f"   Timeline: {c.get('estimated_timeline','?')}")
    if c.get("partner_recommended"):
        print(f"   ⚠️  Atlassian certified partner recommended")

    print(f"\n📊 INVENTORY SUMMARY")
    print(f"  {'Active Flows / Automations:':<38} {sec['flows']['active']:>6}  (of {sec['flows']['total']} total)")
    print(f"  {'Custom Active Business Rules:':<38} {sec['business_rules']['custom_active']:>6}  🔴 HIGH RISK")
    print(f"  {'Custom Active Client Scripts:':<38} {sec['client_scripts']['custom_active']:>6}  🔴 HIGH RISK")
    print(f"  {'Active ACLs / Security Rules:':<38} {sec['acls']['custom_active']:>6}  🔴 HIGH RISK")
    print(f"  {'Active UI Policies:':<38} {sec['ui_policies']['active']:>6}  🟡 MEDIUM RISK")
    print(f"  {'Active Catalog Items:':<38} {sec['catalog']['active_items']:>6}  ✅ API-migratable")
    print(f"  {'Catalog Variables (Custom Fields):':<38} {sec['catalog']['total_variables']:>6}  ✅ API-migratable")
    print(f"  {'Active SLA Definitions:':<38} {sec['slas']['active']:>6}  🖥️  UI-only")
    print(f"  {'Legacy Workflows:':<38} {sec['workflows']['active']:>6}  🖥️  UI-only")
    print(f"  {'Approval Stages:':<38} {sec['approvals']['total']:>6}  🖥️  UI-only")
    print(f"  {'Email Notifications:':<38} {sec['notifications']['active']:>6}  ✅ API-migratable")
    print(f"  {'Scheduled Jobs:':<38} {sec['scheduled_jobs']['active']:>6}  ✅ API-migratable")
    print(f"  {'CMDB CI Records:':<38} {sec['cmdb']['total_cis']:>6}  🔴 HIGH RISK")
    print(f"  {'KB Articles (published):':<38} {sec['knowledge_base']['total_articles']:>6}  🟡 MEDIUM RISK")

    if sec["cmdb"]["ci_classes"]:
        print(f"\n  CMDB CI Classes detected: {', '.join(sec['cmdb']['ci_classes'][:8])}")

    total = s["api_migratable_count"] + s["ui_only_count"] + s["no_equivalent_count"]
    if total > 0:
        print(f"\n✅ MIGRATION READINESS")
        print(f"  🤖 API-migratable:  {s['api_migratable_count']:>5} items  ({int(s['api_migratable_count']/total*100)}%)")
        print(f"  🖥️  UI-only:         {s['ui_only_count']:>5} items  ({int(s['ui_only_count']/total*100)}%)")
        print(f"  ❌ No equivalent:   {s['no_equivalent_count']:>5} items  ({int(s['no_equivalent_count']/total*100)}%)")

    blockers = assessment.get("migration_blockers", [])
    if blockers:
        print(f"\n🚧 MIGRATION BLOCKERS ({len(blockers)})")
        icons = {"HIGH": "🚨", "MEDIUM": "⚠️ ", "LOW": "ℹ️ "}
        for b in blockers:
            print(f"  {icons.get(b['severity'],'•')} [{b['severity']}] {b['blocker']}")
            print(f"      → {b['action']}")

    print(f"\n{'━'*65}")
    print(f"  Next Steps:")
    print(f"  1. Add --report report.md for a full customer-ready report")
    print(f"  2. Export key flows as XML → use jsm-workflow-builder to migrate")
    print(f"  3. Address HIGH blockers before migration")
    print(f"{'━'*65}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="Live ServiceNow REST API Assessment Tool — pre-migration analysis for JSM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/sn_live_assessor.py \\
      --instance https://dev317128.service-now.com \\
      --user admin --password YOUR_PASSWORD \\
      --report live-assessment.md

  python3 scripts/sn_live_assessor.py \\
      --instance https://dev317128.service-now.com \\
      --user admin --password YOUR_PASSWORD \\
      --json-only --output assessment.json
        """,
    )
    p.add_argument("--instance", "-I", required=True, help="ServiceNow instance URL")
    p.add_argument("--auth", choices=("basic", "basic-keychain", "oauth-client-credentials"), default="basic",
                   help="Authentication method (default: basic)")
    p.add_argument("--user", "-u", help="ServiceNow username (required with --auth basic)")
    p.add_argument("--password", "-p", help="ServiceNow password (required with --auth basic)")
    p.add_argument("--keychain-account", default=getpass.getuser(),
                   help="macOS Keychain account for stored credentials (default: current user)")
    p.add_argument("--basic-username-service",
                   help="Keychain service containing the Basic-auth username")
    p.add_argument("--basic-password-service",
                   help="Keychain service containing the Basic-auth password")
    p.add_argument("--oauth-client-id-service",
                   help="Keychain service containing the OAuth client ID")
    p.add_argument("--oauth-client-secret-service",
                   help="Keychain service containing the OAuth client secret")
    p.add_argument("--report", "-r", help="Output markdown report file")
    p.add_argument("--output", "-o", help="Save assessment JSON to file")
    p.add_argument("--output-dir", help="Save all outputs to directory")
    p.add_argument("--json-only", action="store_true", help="Print JSON to stdout only")
    p.add_argument("--deep-discovery", action="store_true",
                   help="Paginate complete CMDB, relationship, flow, catalog, and script metadata inventories")
    p.add_argument("--include-script-source", action="store_true",
                   help="Analyze business/client script bodies in memory; only hashes, metrics, and indicators are persisted")
    p.add_argument("--verbose", "-v", action="store_true", help="Verbose API call output")
    args = p.parse_args()

    if args.auth == "basic":
        if not args.user or not args.password:
            p.error("--user and --password are required with --auth basic")
        client = SNClient.basic(args.instance, args.user, args.password, args.verbose)
    else:
        hostname = urllib.parse.urlparse(args.instance).hostname
        if not hostname:
            p.error("--instance must be a valid URL with a hostname")
        instance_name = hostname.split(".", 1)[0]
        try:
            if args.auth == "basic-keychain":
                username_service = args.basic_username_service or f"rovo.servicenow.{instance_name}.basic.username"
                password_service = args.basic_password_service or f"rovo.servicenow.{instance_name}.basic.password"
                username = keychain_password(username_service, args.keychain_account)
                password = keychain_password(password_service, args.keychain_account)
                client = SNClient.basic(args.instance, username, password, args.verbose)
            else:
                client_id_service = args.oauth_client_id_service or f"rovo.servicenow.{instance_name}.oauth.client-id"
                client_secret_service = args.oauth_client_secret_service or f"rovo.servicenow.{instance_name}.oauth.client-secret"
                client_id = keychain_password(client_id_service, args.keychain_account)
                client_secret = keychain_password(client_secret_service, args.keychain_account)
                client = SNClient.oauth_client_credentials(args.instance, client_id, client_secret, args.verbose)
        except OAuthConfigurationError as exc:
            p.error(str(exc))

    if args.include_script_source and not args.deep_discovery:
        p.error("--include-script-source requires --deep-discovery")
    assessment = run_live_assessment(
        client, args.instance,
        deep_discovery=args.deep_discovery,
        include_script_source=args.include_script_source,
    )

    if args.json_only:
        out = {k: v for k, v in assessment.items() if k != "parsed_details"}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return

    out_dir = Path(args.output_dir) if args.output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    json_path = args.output or (str(out_dir / "live-assessment.json") if out_dir else None)
    if json_path:
        Path(json_path).write_text(json.dumps(assessment, indent=2, ensure_ascii=False))
        print(f"💾 Assessment JSON saved: {json_path}")

    print_live_summary(assessment)

    report_path = args.report or (str(out_dir / "live-assessment-report.md") if out_dir else None)
    if report_path:
        try:
            generate_report(assessment, report_path)
            print(f"📄 Report saved: {report_path}")
        except Exception as e:
            print(f"⚠️  Report generation failed: {e}", file=sys.stderr)
    else:
        print("💡 Tip: Add --report live-assessment.md for a full markdown report")


if __name__ == "__main__":
    main()
