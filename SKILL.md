---
name: jsm-workflow-builder
description: >-
  Create, configure, and migrate workflows in Jira Service Management (JSM) via
  REST API. Use when the user asks to create a JSM workflow, add approval steps,
  configure automation rules, set up SLAs, migrate from ServiceNow flows, or
  build any JSM process automation via API. Also use when the user uploads a
  ServiceNow XML export and wants Rovo Dev to understand the flow and recreate
  it in JSM.
rohub-labels:
  - jsm
  - workflow
  - automation
  - servicenow
  - migration
  - api
---
## ⚠️ CRITICAL: Jira Cloud Workflow Creation API Limitation

**Jira Cloud REST API does NOT support creating workflows programmatically.**

- `POST /rest/api/3/workflow` → HTTP 405 (endpoint removed)
- `POST /rest/api/3/workflows/create` → requires UUID-based `statusReference` values  
  that are NOT available on current Jira Cloud builds (tested build 100292,  
  both GovCloud `ps-se-demo.atlassian-us-gov-mod.net` and Commercial `vish-se-demo.atlassian.net`).

**What TO do when SN XML contains workflow/flow definitions:**
1. Run: `python3 scripts/sn_to_jsm.py --input <file.xml> --workflow-guide /tmp/guide.md`
2. The guide outputs exact statuses, transitions, categories, and post-functions needed
3. Admin follows the guide in: **Jira Settings → Issues → Workflows → Add Workflow**
4. Automations CAN still be created via API — always do those programmatically

**What CAN be done via API (fully working on both instances):**
- ✅ Automation rules (import JSON via Project Automation API)
- ✅ Request types (JSM Service Desk API)
- ✅ Custom fields (`/rest/api/3/field`)
- ✅ Read existing workflows (`/rest/api/3/workflow/search`)
- ✅ Workflow schemes (`/rest/api/3/workflowscheme`)
- ✅ Issue types, priorities, screens

## ⚠️ CRITICAL: Automation API Requires Browser Session Auth (Not API Token)

**The Jira Automation import/create API is NOT accessible via Basic Auth (API token).**

The automation endpoints (`/jira/rest/cb-automation/latest/pro/rest/...`) require
cookie-based browser session authentication — they return HTML when called with
Basic Auth. This applies to both GovCloud and Commercial instances.

**Confirmed working endpoints (return HTML, not JSON, with Basic Auth):**
- `GET /jira/rest/cb-automation/latest/pro/rest/CON/rules` → 200 (HTML)
- `POST /jira/rest/cb-automation/latest/pro/rest/CON/rule/import` → 200 (HTML, ignored)

**The correct approach for automations:**
1. Generate the automation JSON using `scripts/sn_to_jsm.py --input <file.xml>`
2. Save it as a file: `scripts/sn_to_jsm.py --input file.xml --save-json /tmp/rules.json`
3. Admin manually imports in Jira UI: **Project Settings → Automation → Import Rules**
4. Upload the generated JSON file — Jira imports all rules in one step

**What CAN be done via API token (confirmed working on GovCloud):**
- ✅ Request types: `POST /rest/servicedeskapi/servicedesk/{id}/requesttype` (needs X-ExperimentalApi: opt-in header)
- ✅ Custom fields: `/rest/api/3/field`
- ✅ Read workflows, statuses, projects, service desks
- ✅ Issue types, priorities, screens, permission schemes

**What requires UI or browser session:**
- ❌ Workflows (create) — UI only
- ❌ Automation rules (create/import) — UI import of generated JSON
- ❌ Portal customization — UI only




# JSM Workflow Builder

## When to Use
- User uploads or pastes a ServiceNow XML export and wants to migrate it to JSM
- User wants to create or update a JSM automation rule
- User wants to add approval steps to a JSM workflow
- User wants to configure SLAs, transitions, or notification rules in JSM
- User asks "can you recreate this ServiceNow flow in JSM?"
- User provides ServiceNow XML and wants a gap analysis or migration plan

## Quick Start — ServiceNow XML → JSM Migration

### Step 1: Analyze the XML (no credentials needed)
```
python3 scripts/sn_to_jsm.py --input /path/to/export.xml
```
This prints a full migration plan: trigger, steps, approvals, custom fields, request types, and what Rovo Dev can create vs. what needs the UI.

### Step 2: Dry run (preview API calls)
```
python3 scripts/sn_to_jsm.py --input /path/to/export.xml \
  --site https://ps-se-demo.atlassian-us-gov-mod.net \
  --email vankolekar@atlassian.com \
  --token YOUR_API_TOKEN_HERE_P-xqQqq-GpZJZ01JrMTPNp3QppVbSEwdIA4WkLZuA_8aQ48Ul5apb5eBxOpzB-f2Pvq0KiZeIRCXojevNY23QKE_97ThPnRyMXDXdkyHcGbAyc-nT2WTLMbSkGAKIIjCy6_d5ob1eSA=91DEEAF4 \
  --project ITO --dry-run
```

### Step 3: Create everything
```
python3 scripts/sn_to_jsm.py --input /path/to/export.xml \
  --site https://ps-se-demo.atlassian-us-gov-mod.net \
  --email vankolekar@atlassian.com \
  --token YOUR_API_TOKEN_HERE_P-xqQqq-GpZJZ01JrMTPNp3QppVbSEwdIA4WkLZuA_8aQ48Ul5apb5eBxOpzB-f2Pvq0KiZeIRCXojevNY23QKE_97ThPnRyMXDXdkyHcGbAyc-nT2WTLMbSkGAKIIjCy6_d5ob1eSA=91DEEAF4 \
  --project ITO
```

### Optional flags
| Flag | Effect |
|------|--------|
| `--save-json path.json` | Save parsed migration JSON for inspection |
| `--skip-fields` | Skip custom field creation |
| `--skip-rt` | Skip request type creation |
| `--skip-auto` | Skip automation rule creation (saves JSON files only) |
| `--verbose` | Show HTTP response details |

## Live Production Discovery

Use the live assessor for approved, read-only discovery of a customer ServiceNow instance. Store Basic-auth credentials in macOS Keychain; do not pass secrets as command arguments.

```bash
python3 scripts/sn_live_assessor.py \
    --instance https://customer.service-now.com \
    --auth basic-keychain \
    --deep-discovery \
    --include-script-source \
    --report deep-assessment.md \
    --output deep-assessment.json
```

`--deep-discovery` paginates the complete CMDB and `cmdb_rel_ci` inventory, yielding exact run-time CI/class/relationship counts. `--include-script-source` requires explicit customer approval: source bodies are analyzed only in process memory, while saved output contains only SHA-256 fingerprints, line/byte counts, and risk indicators—not script text. The live assessor stops on Table API failures during deep discovery instead of silently reporting incomplete results.

## Scripts Overview

| Script | Purpose |
|--------|---------|
| `scripts/sn_to_jsm.py` | **Main entry point** — orchestrates full migration |
| `scripts/sn_xml_parser.py` | Parses SN XML → structured migration JSON |
| `scripts/jsm_creator.py` | Reads migration JSON → creates JSM resources via API |

## What Each Script Does

### sn_xml_parser.py
- Auto-detects SN export type: Flow Designer, Update Set, Catalog, Workflow
- Extracts: trigger, steps (approval/condition/action/notification/script/subflow), variables, catalog items, business rules, notifications
- Maps every SN concept to its JSM equivalent
- Generates `jsm_mapping` with: recommended project type, workflow statuses, custom fields, request types, automation rules

### jsm_creator.py
- Creates **custom fields** (skips duplicates by name)
- Creates **request types** in the target service desk
- Builds **automation rule JSON files** for manual import (saves to /tmp/)
- Attempts automation API — gracefully falls back to file-based import on GovCloud

### sn_to_jsm.py
- Calls parser → prints analysis → calls creator
- Works in analyze-only mode (no credentials = analysis + JSON output only)

## ServiceNow → JSM Concept Mapping

| ServiceNow | JSM Equivalent |
|---|---|
| Flow Designer trigger | Automation trigger (Issue created/updated/scheduled) |
| Flow condition / IF block | Automation condition branch |
| Set Field Value action | Edit issue fields automation action |
| Approval action | JSM Approval step on workflow transition |
| Send Email action | Send email / Add comment automation action |
| Catalog variables | Custom fields on JSM request type form |
| Catalog item | JSM request type |
| Workflow states | JSM workflow statuses |
| Business rule | Jira Automation rule |
| SLA Timer | JSM SLA configuration |
| Assignment group | Support Group / Team custom field |
| State: Draft → Approved → Rejected | To Do → Waiting for Approval → Approved/Rejected |

## What Can Be Created via API vs. UI Only

### ✅ API (scripts do this automatically)
- Custom fields (Jira Settings → Custom Fields)
- Request types (JSM service desk API)
- Automation rule JSON files (importable via UI)
- Tickets / demo data

### ⚠️ UI Required
- Workflow status additions (Project Settings → Workflows → Edit)
- Approval step configuration on transitions
- Enabling imported automation rules
- Portal group assignments for request types
- SLA creation (JSM internal API, browser session only)
- Forms / ProForma fields

## GovCloud Instance Details
- **Site:** https://ps-se-demo.atlassian-us-gov-mod.net
- **Email:** vankolekar@atlassian.com
- **Token:** YOUR_API_TOKEN_HERE_P-xqQqq-GpZJZ01JrMTPNp3QppVbSEwdIA4WkLZuA_8aQ48Ul5apb5eBxOpzB-f2Pvq0KiZeIRCXojevNY23QKE_97ThPnRyMXDXdkyHcGbAyc-nT2WTLMbSkGAKIIjCy6_d5ob1eSA=91DEEAF4
- **Key projects:** IS, ITO, CON, CLSD, PMOI, ATH, SECOPS, FIN, FAC, PMO

## Prerequisites
1. Python 3.6+ (standard library only — no pip installs needed)
2. Atlassian API Token for the target JSM instance
3. ServiceNow XML export file (Flow Designer export, Update Set XML, or sys_hub_flow XML)

## How to Get a ServiceNow XML Export

### Method A — Flow Designer export
1. Go to ServiceNow → Flow Designer
2. Open the flow → hamburger menu → **Export XML**
3. Save the `.xml` file

### Method B — Update Set export
1. Go to `sys_remote_update_set_list.do`
2. Open the Update Set → **Export to XML**

### Method C — Direct URL (if you know the sys_id)
```
https://dev324647.service-now.com/sys_hub_flow_xml.do?sysparm_sys_id=YOUR_SYS_ID
```

## Using the MCP Server Tools (when available)
When the `jsm-workflow-builder` MCP server is active, use:
- `jsm_convert_servicenow_xml` — parse SN XML and return JSM-equivalent JSON
- `jsm_create_automation` — create a complete automation rule
- `jsm_create_workflow` — create a workflow with statuses and transitions
- `jsm_list_automations` — list existing rules in a project

Prefer MCP tools when available; fall back to scripts otherwise.

## References
- Full Automation API schema: references/automation-api.md
- Workflow API schema: references/workflow-api.md
- Approval configuration: references/approval-api.md
- SLA configuration: references/sla-api.md
- ServiceNow to JSM mapping guide: references/servicenow-mapping.md

## Assets
- Use assets/automation-template.json as a starting point for automation rules
- Use assets/workflow-template.json as a starting point for workflow creation
- Use assets/approval-template.json for approval step configuration
