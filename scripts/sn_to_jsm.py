#!/usr/bin/env python3
"""
sn_to_jsm.py — End-to-end ServiceNow XML → JSM migration orchestrator.
This is the ONE script Rovo Dev calls. It:
  1. Parses the ServiceNow XML  (sn_xml_parser.py)
  2. Prints a full analysis / migration plan
  3. Optionally creates everything in JSM via API  (jsm_creator.py)

Usage examples:

  # Analyze only (no API calls):
  python3 scripts/sn_to_jsm.py --input export.xml

  # Dry run — see what WOULD be created:
  python3 scripts/sn_to_jsm.py --input export.xml \
      --site https://ps-se-demo.atlassian-us-gov-mod.net \
      --email vankolekar@atlassian.com --token YOUR_TOKEN \
      --project ITO --dry-run

  # Full migration (creates fields, request types, automation JSONs):
  python3 scripts/sn_to_jsm.py --input export.xml \
      --site https://ps-se-demo.atlassian-us-gov-mod.net \
      --email vankolekar@atlassian.com --token YOUR_TOKEN \
      --project ITO

  # Save the parsed JSON for Rovo Dev to inspect:
  python3 scripts/sn_to_jsm.py --input export.xml --save-json migration.json
"""

import argparse, json, subprocess, sys
from pathlib import Path

SCRIPTS = Path(__file__).parent


def run_parser(xml_path, save_json=None, verbose=False):
    cmd = [sys.executable, str(SCRIPTS / "sn_xml_parser.py"), "--input", xml_path]
    if save_json: cmd += ["--output", save_json]
    if verbose: cmd.append("--verbose")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"❌ Parser error:\n{r.stderr}", file=sys.stderr); sys.exit(1)
    if verbose and r.stderr: print(r.stderr, file=sys.stderr)
    if save_json and Path(save_json).exists():
        return json.loads(Path(save_json).read_text())
    return json.loads(r.stdout)


def run_creator(json_path, site, email, token, project,
                dry_run=False, verbose=False,
                skip_fields=False, skip_rt=False, skip_auto=False):
    cmd = [sys.executable, str(SCRIPTS / "jsm_creator.py"),
           "--input", json_path, "--site", site,
           "--email", email, "--token", token, "--project", project]
    if dry_run: cmd.append("--dry-run")
    if verbose: cmd.append("--verbose")
    if skip_fields: cmd.append("--skip-fields")
    if skip_rt: cmd.append("--skip-rt")
    if skip_auto: cmd.append("--skip-auto")
    return subprocess.run(cmd, text=True).returncode


def print_analysis(parsed):
    m = parsed.get("jsm_mapping", {})
    name = parsed.get("name", "ServiceNow Export")
    src_type = parsed.get("source_type", "unknown")
    trigger = parsed.get("trigger", {})

    print("\n" + "━"*65)
    print("  🔍  SERVICENOW → JSM  ANALYSIS REPORT")
    print("━"*65)
    print(f"  Flow Name  : {name}")
    print(f"  Export Type: {src_type.upper()}")
    print(f"  SN Trigger : {trigger.get('type','—')} (SN table: {trigger.get('table','—')})")
    print(f"  JSM Trigger: {trigger.get('jsm_equivalent','—')}")
    print(f"  ➜  Recommended JSM Project Type: {m.get('recommended_project_type','—')}")
    print("━"*65)

    ICONS = {"approval":"✔️ ","condition":"🔀","action":"⚙️ ","notification":"📧","script":"📝","subflow":"🔗"}
    steps = parsed.get("steps", [])
    print(f"\n📊 Flow Steps ({len(steps)} total)")
    for s in steps[:15]:
        print(f"  {ICONS.get(s['type'],'• ')} [{s['type'].upper():<12}] {s['label']:<32} → {s.get('jsm_equivalent','—')}")
    if len(steps) > 15: print(f"  ... and {len(steps)-15} more steps")

    approvals = parsed.get("approvals", [])
    if approvals:
        print(f"\n✔️  Approval Stages ({len(approvals)})")
        for a in approvals:
            print(f"  • Stage: {a['stage']:<30} Approver: {a.get('approver','—')}")
            print(f"    → JSM: Add approval step on workflow transition")

    notifications = parsed.get("notifications", [])
    if notifications:
        print(f"\n📧 Notifications ({len(notifications)})")
        for n in notifications:
            print(f"  • {n.get('trigger','—')} → {n.get('recipients','—')}")
            print(f"    → JSM: {n.get('jsm_equivalent','Send email / Add comment')}")

    cf = m.get("custom_fields", [])
    if cf:
        print(f"\n🔧 Custom Fields to Create ({len(cf)})")
        for f in cf:
            req = "  ✱required" if f.get("mandatory") else ""
            print(f"  • {f['name']:<35} [{f['jsm_field_type']}]{req}")

    rts = m.get("request_types", [])
    if rts:
        print(f"\n📝 Request Types to Create ({len(rts)})")
        for rt in rts: print(f"  • {rt['name']}")

    rules = m.get("automation_rules", [])
    if rules:
        print(f"\n🤖 Automation Rules ({len(rules)})")
        for r in rules:
            print(f"  • {r['name']}")
            print(f"    Trigger: {r['trigger']}")
            for a in r.get("actions", [])[:3]: print(f"    {a}")
            if r.get("note"): print(f"    ℹ️  {r['note']}")

    ws = m.get("workflow_statuses", [])
    if ws:
        print(f"\n🔄 JSM Workflow Statuses Suggested")
        print(f"  {' → '.join(ws[:8])}" + (f" +{len(ws)-8} more" if len(ws)>8 else ""))

    print(f"\n{'━'*65}")
    print("  ✅ Rovo Dev CAN create via API:")
    print(f"     • Custom fields ({len(cf)})")
    print(f"     • Request types ({len(rts)})")
    print(f"     • Automation rule import JSON files ({len(rules)})")
    print("  ⚠️  Requires UI (Project Settings):")
    print("     • Workflow status additions")
    print("     • Approval step configuration on transitions")
    print("     • Enabling automation rules after import")
    print("━"*65 + "\n")


def main():
    p = argparse.ArgumentParser(
        description="ServiceNow XML → JSM full migration. Run without --site to analyze only."
    )
    p.add_argument("--input", "-i", required=True, help="ServiceNow XML export file")
    p.add_argument("--site", "-s",  help="JSM site URL (e.g. https://mysite.atlassian.net)")
    p.add_argument("--email", "-e", help="Atlassian email")
    p.add_argument("--token", "-t", help="Atlassian API token")
    p.add_argument("--project", "-p", help="JSM project key (e.g. ITO, CON)")
    p.add_argument("--save-json", metavar="PATH", help="Also save parsed JSON to this file")
    p.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    p.add_argument("--skip-fields", action="store_true")
    p.add_argument("--skip-rt", action="store_true")
    p.add_argument("--skip-auto", action="store_true")
    p.add_argument("--skip-workflow-check", action="store_true",
                   help="Skip interactive workflow-ready prompt (for CI/scripted runs)")
    p.add_argument("--workflow-guide", metavar="PATH",
                   help="Save workflow UI guide to this file (e.g. /tmp/guide.md)")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    xml_path = args.input
    if not Path(xml_path).exists():
        print(f"❌ File not found: {xml_path}", file=sys.stderr); sys.exit(1)

    # Step 1 — Parse
    print(f"\n📂 Step 1/3 — Parsing ServiceNow XML: {xml_path}")
    json_out = args.save_json or f"/tmp/sn_migration_{Path(xml_path).stem}.json"
    parsed = run_parser(xml_path, save_json=json_out, verbose=args.verbose)
    print(f"   ✅ Parsed → {json_out}\n")

    # Step 2 — Analyze
    print("📊 Step 2/3 — Analysis")
    print_analysis(parsed)

    # Step 3 — Create (only if credentials supplied)
    if not args.site:
        print("ℹ️  Analysis complete. To create resources in JSM, re-run with:")
        print(f"   --site YOUR_JSM_URL --email EMAIL --token TOKEN --project PROJECT_KEY")
        print(f"   Parsed JSON: {json_out}\n")
        return

    if not all([args.email, args.token, args.project]):
        print("❌ --email, --token, and --project are required when --site is given.", file=sys.stderr)
        sys.exit(1)

    # ── PAUSE: Workflow must be created in UI before API steps ──────────────
    print()
    print("━"*65)
    print("  ⏸️   WORKFLOW CREATION REQUIRED BEFORE CONTINUING")
    print("━"*65)
    print()
    print("  JSM workflows cannot be created via API — you must create")
    print("  the workflow manually in the Jira UI first.")
    print()
    print("  📋 The workflow guide has been saved above (or to your")
    print("     --workflow-guide path if specified).")
    print()
    print("  ✅ CHECKLIST before continuing:")
    print("     1. Created the workflow in Jira UI (Settings → Issues → Workflows)")
    print("     2. Published the workflow")
    print("     3. Assigned it to your project (Project Settings → Workflows)")
    print()

    if not args.dry_run and not args.skip_workflow_check:
        try:
            answer = input("  Have you completed the workflow setup? [y/N]: ").strip().lower()
        except EOFError:
            answer = "y"  # non-interactive mode (CI/script) — assume yes

        if answer not in ("y", "yes"):
            print()
            print("  ⏸️  Paused. Re-run this script with --skip-workflow-check")
            print("     to skip this prompt after workflow is ready.")
            print()
            sys.exit(0)

    print()
    print(f"🚀 Step 3/3 — Creating JSM resources {'(DRY RUN)' if args.dry_run else ''}")
    rc = run_creator(json_out, args.site, args.email, args.token, args.project,
                     dry_run=args.dry_run, verbose=args.verbose,
                     skip_fields=args.skip_fields, skip_rt=args.skip_rt, skip_auto=args.skip_auto)
    sys.exit(rc)


if __name__ == "__main__":
    main()


# ─────────────────────────────────────────────────────────────────────────────
# WORKFLOW UI GUIDE GENERATOR
# Called when --generate-workflow-guide flag is set
# Produces a step-by-step guide for manual workflow creation in Jira UI
# ─────────────────────────────────────────────────────────────────────────────
def generate_workflow_guide(migration_data: dict, output_path: str = None) -> str:
    """Generate a step-by-step UI guide for creating the workflow in Jira."""
    wf = migration_data.get("workflow_summary", {})
    statuses = wf.get("statuses", [])
    transitions = wf.get("transitions", [])
    wf_name = migration_data.get("source_name", "Migrated Workflow")

    lines = []
    lines.append(f"# Jira Workflow Creation Guide")
    lines.append(f"## Migrated from: {migration_data.get('source_file', 'ServiceNow')}")
    lines.append(f"## Workflow Name: {wf_name}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Step 1: Navigate to Workflow Editor")
    lines.append("1. Go to **Jira Settings** (gear icon, top right)")
    lines.append("2. Click **Issues** → **Workflows**")
    lines.append("3. Click **Add workflow** → **Create new workflow**")
    lines.append(f"4. Name it: `{wf_name}`")
    lines.append(f"5. Description: `Migrated from ServiceNow`")
    lines.append("6. Click **Create**")
    lines.append("")
    lines.append("## Step 2: Add Statuses")
    lines.append("In the workflow diagram, add these statuses:")
    lines.append("")
    for i, s in enumerate(statuses, 1):
        category_map = {"TODO": "🔵 To Do", "IN_PROGRESS": "🟡 In Progress", "DONE": "🟢 Done"}
        cat = category_map.get(s.get("category", "TODO"), s.get("category", ""))
        lines.append(f"  {i}. **{s['name']}** — Category: {cat}")
    lines.append("")
    lines.append("## Step 3: Add Transitions")
    lines.append("Click **Add transition** for each:")
    lines.append("")
    for i, t in enumerate(transitions, 1):
        frm = t.get("from", [])
        to  = t.get("to", "")
        if not frm:
            lines.append(f"  {i}. **{t['name']}** (Initial) → to: `{to}`")
        else:
            from_str = ", ".join(f"`{f}`" for f in frm)
            lines.append(f"  {i}. **{t['name']}** — from: {from_str} → to: `{to}`")
        if t.get("has_approval"):
            lines.append(f"     ⚠️  Add approval step on this transition")
        if t.get("has_notification"):
            lines.append(f"     📧  Add email notification post-function")
    lines.append("")
    lines.append("## Step 4: Add Post-Functions (for approvals/notifications)")
    approvals = [t for t in transitions if t.get("has_approval")]
    if approvals:
        lines.append("For the following transitions, add JSM **Approval** post-functions:")
        for t in approvals:
            lines.append(f"  - **{t['name']}**: Add approver group/user")
    else:
        lines.append("_No approval post-functions needed._")
    lines.append("")
    lines.append("## Step 5: Publish the Workflow")
    lines.append("1. Click **Publish** (top right of workflow editor)")
    lines.append("2. Assign it to your JSM project:")
    lines.append("   - Go to **Project Settings** → **Workflows**")
    lines.append("   - Click **Switch Scheme** → assign this workflow to your issue type")
    lines.append("")
    lines.append("## Step 6: Create Matching Automation Rules")
    lines.append("The following automation rules from ServiceNow should be created:")
    for rule in migration_data.get("automation_rules", []):
        lines.append(f"  - **{rule.get('name', 'Unnamed')}**: {rule.get('description', '')}")
    lines.append("")
    lines.append("---")
    lines.append("_Generated by Rovo Dev JSM Migration Tool_")

    guide_text = "\n".join(lines)

    if output_path:
        with open(output_path, "w") as f:
            f.write(guide_text)
        print(f"✅ Workflow guide saved to: {output_path}")
    else:
        print(guide_text)

    return guide_text
