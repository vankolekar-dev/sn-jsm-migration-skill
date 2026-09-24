#!/usr/bin/env python3
"""
sn_report_generator.py — Markdown Assessment Report Generator

Generates a customer-ready migration assessment report from the
output of sn_assessor.py. Covers inventory, risk scoring, blockers,
migration readiness, and recommended next steps.

Used by sn_assessor.py (--report flag) — can also be run standalone:
    python3 scripts/sn_report_generator.py --input assessment.json --output report.md
"""

import argparse, json, sys
from pathlib import Path
from datetime import datetime


def _pct_bar(value, total, width=20):
    """Return a simple ASCII percentage bar."""
    if total == 0:
        return "[" + " " * width + "] 0%"
    filled = int(value / total * width)
    pct = int(value / total * 100)
    return f"[{'█' * filled}{'░' * (width - filled)}] {pct}%"


def generate_report(assessment, output_path=None):
    """
    Generate a full markdown assessment report from an assessment dict.
    Returns the report as a string and optionally saves to output_path.
    """
    s = assessment.get("summary", {})
    c = assessment.get("complexity", {})
    blockers = assessment.get("migration_blockers", [])
    files = assessment.get("files", [])
    project_types = assessment.get("recommended_jsm_project_types", [])
    generated_at = assessment.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    risk = c.get("overall_risk", "UNKNOWN")
    score = c.get("score", 0)
    risk_icon = c.get("risk_icon", "⚪")
    risk_label = c.get("label", "")
    timeline = c.get("estimated_timeline", "Unknown")
    partner_note = c.get("partner_note", "")
    breakdown = c.get("aggregated_breakdown", [])

    total_items = s.get("api_migratable_count", 0) + s.get("ui_only_count", 0) + s.get("no_equivalent_count", 0)

    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        "# ServiceNow → JSM Migration Assessment Report",
        "",
        f"**Generated:** {generated_at}  ",
        f"**Files Analyzed:** {assessment.get('total_files', 0)}  ",
        f"**Tool:** Rovo Dev `sn-assessment` skill  ",
        "",
        "---",
        "",
    ]

    # ── Executive Summary ─────────────────────────────────────────────────────
    lines += [
        "## Executive Summary",
        "",
        f"| | |",
        f"|---|---|",
        f"| **Migration Complexity** | {risk_icon} **{risk}** (Score: {score}/100) |",
        f"| **Estimated Timeline** | {timeline} |",
        f"| **Migration Blockers** | {len(blockers)} identified |",
        f"| **Partner Recommended** | {'✅ Yes' if c.get('partner_recommended') else '❌ Not required'} |",
        "",
        f"> {risk_label}",
        "",
        f"{partner_note}",
        "",
        "---",
        "",
    ]

    # ── Files Analyzed ────────────────────────────────────────────────────────
    if files:
        lines += [
            "## Files Analyzed",
            "",
            "| File | Type | Steps | Approvals | Scripts | High Risk |",
            "|------|------|-------|-----------|---------|-----------|",
        ]
        for f in files:
            lines.append(
                f"| `{f.get('file','?')}` | {f.get('type','?')} | "
                f"{f.get('steps',0)} | {f.get('approvals',0)} | "
                f"{f.get('scripts',0)} | {f.get('high_risk_items',0)} |"
            )
        lines += ["", "---", ""]

    # ── Inventory Summary ─────────────────────────────────────────────────────
    lines += [
        "## Inventory Summary",
        "",
        "| Item | Count | JSM Equivalent | API Migratable? |",
        "|------|-------|----------------|-----------------|",
        f"| Flows / Processes | {s.get('total_flows',0)} | JSM Automation Rules | ⚠️ Partial |",
        f"| Total Steps | {s.get('total_steps',0)} | Automation Rule Actions | ⚠️ Partial |",
        f"| Approval Stages | {s.get('total_approvals',0)} | JSM Workflow Approvals | ❌ UI Only |",
        f"| Notifications | {s.get('total_notifications',0)} | Automation: Send Email | ✅ Yes |",
        f"| Custom Scripts | {s.get('total_scripts',0)} | Jira Automation / Forge | ❌ Must Rewrite |",
        f"| Business Rules | {s.get('total_business_rules',0)} | Jira Automation Rules | ❌ Must Rewrite |",
        f"| Client Scripts | {s.get('total_client_scripts',0)} | ProForma / Forge UI Kit | ❌ No Equivalent |",
        f"| ACLs / Security Rules | {s.get('total_acls',0)} | Issue Security Schemes | ❌ UI Only |",
        f"| UI Policies | {s.get('total_ui_policies',0)} | ProForma Conditional Logic | ⚠️ Limited |",
        f"| Catalog Items | {s.get('total_catalog_items',0)} | JSM Request Types | ✅ Yes (API) |",
        f"| Custom Fields | {s.get('total_custom_fields',0)} | Jira Custom Fields | ✅ Yes (API) |",
        f"| SLA Definitions | {s.get('total_sla_definitions',0)} | JSM SLA Policies | ❌ UI Only |",
        f"| Workflows | {s.get('total_workflows',0)} | JSM Workflows | ❌ UI Only |",
        f"| CMDB CI Records | {s.get('total_ci_records',0)} | Atlassian Assets (Insight) | ⚠️ Separate Product |",
        f"| Knowledge Base Articles | {s.get('total_kb_articles',0)} | Confluence + JSM KB | ❌ Manual Migration |",
        "",
        "---",
        "",
    ]

    # ── Migration Readiness ───────────────────────────────────────────────────
    lines += [
        "## Migration Readiness",
        "",
    ]
    if total_items > 0:
        api_count = s.get("api_migratable_count", 0)
        ui_count = s.get("ui_only_count", 0)
        gap_count = s.get("no_equivalent_count", 0)
        lines += [
            f"```",
            f"API-Migratable  {_pct_bar(api_count, total_items)}  {api_count} items",
            f"UI-Only         {_pct_bar(ui_count,  total_items)}  {ui_count} items",
            f"No Equivalent   {_pct_bar(gap_count, total_items)}  {gap_count} items",
            f"```",
            "",
            "| Category | Count | What This Means |",
            "|----------|-------|-----------------|",
            f"| ✅ **API-Migratable** | {api_count} | Can be created automatically using `jsm-workflow-builder` |",
            f"| 🖥️ **UI-Only** | {ui_count} | Must be configured manually in JSM project settings |",
            f"| ❌ **No Direct Equivalent** | {gap_count} | Requires redesign or alternative Atlassian product |",
            "",
        ]
    lines += ["---", ""]

    # ── Complexity Score Breakdown ─────────────────────────────────────────────
    if breakdown:
        lines += [
            "## Complexity Score Breakdown",
            "",
            f"**Overall Score: {score}/100 — {risk_icon} {risk}**",
            "",
            "| Factor | Count | Severity | Score Contribution |",
            "|--------|-------|----------|-------------------|",
        ]
        for b in breakdown:
            sev_icon = "🔴" if b["severity"] == "HIGH" else ("🟡" if b["severity"] == "MEDIUM" else "🟢")
            lines.append(
                f"| {b['factor']} | {b['count']} | {sev_icon} {b['severity']} | +{b['score_contribution']:.1f} |"
            )
        lines += ["", "---", ""]

    # ── Migration Blockers ────────────────────────────────────────────────────
    if blockers:
        lines += [
            "## Migration Blockers",
            "",
            "> These items require manual remediation and cannot be automatically migrated.",
            "",
        ]
        high = [b for b in blockers if b["severity"] == "HIGH"]
        medium = [b for b in blockers if b["severity"] == "MEDIUM"]
        low = [b for b in blockers if b["severity"] == "LOW"]

        for severity, items, icon in [
            ("HIGH", high, "🚨"),
            ("MEDIUM", medium, "⚠️"),
            ("LOW", low, "ℹ️"),
        ]:
            if not items:
                continue
            lines.append(f"### {icon} {severity} Severity")
            lines.append("")
            for b in items:
                lines += [
                    f"**{b['blocker']}**",
                    f"> {b['action']}",
                    "",
                ]
        lines += ["---", ""]

    # ── Recommended JSM Project Types ─────────────────────────────────────────
    if project_types:
        lines += [
            "## Recommended JSM Project Types",
            "",
        ]
        PROJECT_NOTES = {
            "IT Service Management":    "Use the ITSM template — covers incidents, requests, problems, and changes.",
            "IT Change Management":     "Use the Change Management template with CAB approval workflow.",
            "IT Incident Management":   "Use the Incident Management template with on-call and escalation.",
            "IT Problem Management":    "Use the Problem Management template with RCA tracking.",
            "HR Service Management":    "Use the HR template — add department-specific request types.",
            "Legal / Contract Management": "Use General Service Management template with approval workflows.",
            "Assets (Atlassian Insight)": "Use Atlassian Assets — requires separate schema design from CMDB classes.",
            "Confluence Knowledge Base": "Create a Confluence space linked to JSM for KB articles.",
        }
        for pt in project_types:
            note = PROJECT_NOTES.get(pt, "Configure a JSM project with appropriate request types and workflows.")
            lines += [f"- **{pt}**: {note}"]
        lines += ["", "---", ""]

    # ── ServiceNow → JSM Concept Map ──────────────────────────────────────────
    lines += [
        "## ServiceNow → JSM Concept Mapping",
        "",
        "| ServiceNow Concept | JSM / Atlassian Equivalent | Notes |",
        "|-------------------|---------------------------|-------|",
        "| Catalog Item | Request Type | API: `POST /rest/servicedeskapi/servicedesk/{id}/requesttype` |",
        "| Service Category | Portal Group | UI only — configure in Customer Portal settings |",
        "| Catalog Variable | Custom Field | API: `POST /rest/api/3/field` ✅ |",
        "| Flow Designer Flow | Automation Rule | ⚠️ Map trigger + actions manually |",
        "| Workflow | JSM Workflow | ❌ UI only — workflow editor in project settings |",
        "| Approval | JSM Approval Step | ❌ UI only — add to workflow transition |",
        "| Business Rule | Automation Rule | ❌ Must rewrite logic (no Groovy on Cloud) |",
        "| Client Script | ProForma / Forge | ❌ No direct equivalent |",
        "| UI Policy | ProForma Conditional | ⚠️ Limited — show/hide via form logic |",
        "| ACL | Issue Security Scheme | ❌ UI only — permission scheme configuration |",
        "| SLA Definition | JSM SLA Policy | ❌ UI only — project settings → SLAs |",
        "| Email Notification | Automation: Send Email | ✅ API via automation rule |",
        "| Scheduled Job | Scheduled Automation | ✅ API — use scheduled trigger |",
        "| Subflow | Outgoing Webhook | ⚠️ Chain automation rules via webhook |",
        "| REST Message | Outgoing Webhook | ✅ API — `outgoing.webhook` action |",
        "| CMDB CI | Atlassian Assets Object | ❌ Separate product — schema + CSV/API import |",
        "| Knowledge Article | Confluence Page | ❌ Manual migration to Confluence space |",
        "| Knowledge Category | Confluence Space/Label | Manual mapping required |",
        "| User / Group | Atlassian Account / Group | ⚠️ Email-based invite + SCIM for bulk |",
        "",
        "---",
        "",
    ]

    # ── What CAN Be Done via API (using jsm-workflow-builder) ────────────────
    lines += [
        "## What Can Be Migrated via API",
        "",
        "Use the `jsm-workflow-builder` Rovo skill to automate the following:",
        "",
        "| Item | API Endpoint | Script |",
        "|------|-------------|--------|",
        "| Custom Fields | `POST /rest/api/3/field` | `jsm_creator.py --skip-rt --skip-auto` |",
        "| Request Types | `POST /rest/servicedeskapi/servicedesk/{id}/requesttype` | `jsm_creator.py --skip-fields --skip-auto` |",
        "| Automation Rules (JSON) | Import via Project Settings UI | `jsm_creator.py` generates JSON files |",
        "| JSM Project Creation | `POST /rest/api/3/project` | Manual or via API |",
        "| Email Notifications | Automation rule with `send_email` action | Built into automation JSON |",
        "| Scheduled Triggers | Automation rule with `scheduled` trigger | Built into automation JSON |",
        "",
        "```bash",
        "# Step 1: Parse and assess",
        "python3 scripts/sn_assessor.py --input export.xml --report assessment.md",
        "",
        "# Step 2: Run migration for automatable items",
        "python3 ../jsm-workflow-builder/scripts/sn_to_jsm.py \\",
        "    --input export.xml \\",
        "    --site https://your-instance.atlassian.net \\",
        "    --email you@example.com --token YOUR_TOKEN \\",
        "    --project YOUR_PROJECT_KEY",
        "```",
        "",
        "---",
        "",
    ]

    # ── What Requires UI ──────────────────────────────────────────────────────
    lines += [
        "## What Requires Manual UI Configuration",
        "",
        "The following must be configured manually in JSM — generate a step-by-step guide with:",
        "```bash",
        "python3 ../jsm-workflow-builder/scripts/sn_to_jsm.py --input export.xml --workflow-guide guide.md",
        "```",
        "",
        "### Workflows",
        "1. Go to **Project Settings → Workflows**",
        "2. Create a new workflow matching your SN states",
        "3. Add statuses: match the states in the Inventory Summary above",
        "4. Configure transitions between statuses",
        "",
        "### Approvals",
        "1. Go to **Project Settings → Workflows → Edit**",
        "2. Click on a transition (e.g. `Submit → In Review`)",
        "3. Add **Approvers** — select user or group",
        "4. Repeat for each approval stage found in this assessment",
        "",
        "### SLA Policies",
        "1. Go to **Project Settings → SLAs**",
        "2. Click **Create SLA**",
        "3. Set goal (duration from SLA definitions above)",
        "4. Set start/stop/pause conditions to match SN SLA conditions",
        "",
        "### Issue Security (ACLs)",
        "1. Go to **Project Settings → Issue Security**",
        "2. Create security levels matching your SN ACL roles",
        "3. Assign groups/users to each level",
        "",
        "---",
        "",
    ]

    # ── Recommended Next Steps ────────────────────────────────────────────────
    lines += [
        "## Recommended Next Steps",
        "",
        "### Phase 1 — Pre-Migration Prep (Week 1–2)",
        "- [ ] Share this assessment report with your JSM admin and project stakeholders",
        "- [ ] Identify owners for each HIGH severity blocker",
        "- [ ] Audit all Marketplace apps in ServiceNow — check for Atlassian equivalents",
        "- [ ] Set up a JSM sandbox/dev environment for testing",
        "- [ ] Pre-create Atlassian user accounts (email invites or SCIM)",
        "",
        "### Phase 2 — Automated Migration (Week 2–3)",
        "- [ ] Run `jsm-workflow-builder` to create custom fields and request types",
        "- [ ] Import automation rules JSON via Project Settings → Automation",
        "- [ ] Validate field names and types in JSM",
        "",
        "### Phase 3 — Manual Configuration (Week 3–5)",
        "- [ ] Create JSM workflows (statuses + transitions) in UI",
        "- [ ] Add approval steps to workflow transitions",
        "- [ ] Configure SLA policies",
        "- [ ] Set up issue security schemes (from ACL analysis)",
        "- [ ] Rebuild client scripts using ProForma or Forge",
        "",
        "### Phase 4 — Data & Content Migration",
    ]

    if s.get("total_ci_records", 0) > 0:
        lines += [
            f"- [ ] **CMDB ({s['total_ci_records']} CIs):** Design Atlassian Assets schema → import via CSV or Assets API",
        ]
    if s.get("total_kb_articles", 0) > 0:
        lines += [
            f"- [ ] **Knowledge Base ({s['total_kb_articles']} articles):** Migrate to Confluence manually or via bulk page create API",
        ]
    if s.get("total_scripts", 0) > 0:
        lines += [
            f"- [ ] **Scripts ({s['total_scripts']} scripts):** Rewrite as Jira Automation rules or Forge apps",
        ]
    if s.get("total_business_rules", 0) > 0:
        lines += [
            f"- [ ] **Business Rules ({s['total_business_rules']} rules):** Rewrite as Jira Automation rules",
        ]

    lines += [
        "",
        "### Phase 5 — Validation & Cutover",
        "- [ ] End-to-end test each request type in JSM sandbox",
        "- [ ] Validate automation rules fire correctly",
        "- [ ] Validate SLA timers start/stop as expected",
        "- [ ] Run parallel operation (SN + JSM) during transition period",
        "- [ ] Plan cutover date with stakeholders — communicate data freeze window",
        "- [ ] Post-cutover: disable SN flows, redirect users to JSM portal",
        "",
        "---",
        "",
    ]

    # ── GovCloud Note ─────────────────────────────────────────────────────────
    lines += [
        "## GovCloud / FedRAMP Note",
        "",
        "If migrating to **Atlassian Government Cloud** (FedRAMP Moderate):",
        "",
        "- Site URL: `https://<instance>.atlassian-us-gov-mod.net`",
        "- Automation rule import via JSON is supported but some trigger types are restricted",
        "- Forge apps require separate FedRAMP review before deployment",
        "- Assets (Insight) is available on GovCloud",
        "- Confirm all Marketplace apps are GovCloud-certified before migrating",
        "- See the `jsm-govcloud` Rovo skill for GovCloud-specific guidance",
        "",
        "---",
        "",
    ]

    # ── Footer ────────────────────────────────────────────────────────────────
    lines += [
        "## Related Rovo Skills",
        "",
        "| Skill | When to Use |",
        "|-------|-------------|",
        "| `jsm-workflow-builder` | Migrate automatable items (fields, request types, automation rules) |",
        "| `jsm-workflow-builder-dev` | Full pre-production JSM instance setup + SN XML migration |",
        "| `jsm-approval-workflows` | Configure multi-level approval workflows in JSM |",
        "| `jsm-sla-escalation` | Configure SLA policies and escalation rules |",
        "| `jsm-assets-configurator` | Set up Atlassian Assets schema (from CMDB) |",
        "| `jsm-govcloud` | GovCloud / FedRAMP-specific configuration guidance |",
        "| `jsm-portal-branding` | Customize JSM customer portal (replaces SN Service Portal) |",
        "",
        "---",
        "",
        f"*Report generated by Rovo Dev `sn-assessment` skill — {generated_at}*",
    ]

    report_text = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(report_text, encoding="utf-8")

    return report_text


# ── Standalone CLI ────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Generate markdown report from sn_assessor.py JSON output")
    p.add_argument("--input", "-i", required=True, help="assessment.json from sn_assessor.py")
    p.add_argument("--output", "-o", required=True, help="Output markdown file (e.g. report.md)")
    args = p.parse_args()

    assessment = json.loads(Path(args.input).read_text())
    text = generate_report(assessment, args.output)
    print(f"✅ Report saved: {args.output} ({len(text)} chars)")


if __name__ == "__main__":
    main()
