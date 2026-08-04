#!/usr/bin/env python3
"""
sn_xml_parser.py — Parse a ServiceNow XML export and produce a structured
JSON migration plan for Rovo Dev to use when creating JSM equivalents.

Usage:
    python3 scripts/sn_xml_parser.py --input export.xml [--output summary.json] [--verbose]
"""

import argparse, json, sys, xml.etree.ElementTree as ET
from pathlib import Path

SN_TO_JSM_STATUS = {
    "draft": "To Do", "waiting for approval": "Waiting for Approval",
    "approved": "Approved", "rejected": "Rejected", "open": "Open",
    "in progress": "In Progress", "resolved": "Resolved", "closed": "Closed",
    "cancelled": "Cancelled", "expired": "Expired", "review": "Under Review",
    "assess": "Under Review", "authorize": "Waiting for Approval",
    "scheduled": "Scheduled", "implement": "In Progress", "new": "Open",
    "on hold": "On Hold",
}

SN_TRIGGER_TO_JSM = {
    "record_created": "Issue created", "record_updated": "Issue updated",
    "record_created_or_updated": "Issue created or updated",
    "scheduled": "Scheduled", "inbound_email": "Issue created via email",
    "manual": "Manual trigger",
}

SN_ACTION_TO_JSM = {
    "set_field_value": "Edit issue fields", "create_record": "Create sub-task",
    "update_record": "Edit issue fields", "send_email": "Send email",
    "create_catalog_task": "Create sub-task", "approval": "Require approval",
    "script": "Run web request / Jira expression", "wait_for_condition": "Condition branch",
    "if": "Condition branch", "log": "Add comment",
}

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

def _txt(el, tag, default=""):
    child = el.find(tag)
    return (child.text or "").strip() if child is not None else default

def detect_type(root):
    tags = {el.tag for el in root.iter()}
    if "sys_hub_flow" in tags or "sys_hub_action_instance" in tags:
        return "flow"
    if "sys_remote_update_set" in tags or "sys_update_set" in tags:
        return "update_set"
    if "sc_cat_item" in tags or "item_option_new" in tags:
        return "catalog"
    if "wf_workflow" in tags or "wf_activity" in tags:
        return "workflow"
    return "unknown"

def parse_flow_designer(root):
    result = {"source_type": "flow", "name": "", "description": "",
               "trigger": {}, "variables": [], "steps": [],
               "approvals": [], "notifications": [], "transitions": [], "catalog_items": []}
    flow_el = root.find(".//sys_hub_flow") or root.find(".//flow") or root
    result["name"] = _txt(flow_el, "name") or root.get("name", "Unnamed Flow")
    result["description"] = _txt(flow_el, "description") or _txt(flow_el, "sys_description")
    trigger_el = root.find(".//sys_hub_trigger") or root.find(".//trigger")
    if trigger_el is not None:
        t = _txt(trigger_el, "type") or _txt(trigger_el, "trigger_type") or "record_created"
        result["trigger"] = {
            "type": t,
            "jsm_equivalent": SN_TRIGGER_TO_JSM.get(t.lower().replace(" ","_"), "Issue created"),
            "table": _txt(trigger_el, "table") or _txt(trigger_el, "sys_class_name", ""),
            "condition": _txt(trigger_el, "condition") or _txt(trigger_el, "filter_condition", ""),
        }
    for var_el in root.findall(".//sys_hub_flow_var") + root.findall(".//flow_variable"):
        result["variables"].append({
            "name": _txt(var_el, "name") or var_el.get("name",""),
            "type": _txt(var_el, "type", "string"),
            "default": _txt(var_el, "default_value",""),
        })
    step_order = 1
    for action_el in (root.findall(".//sys_hub_action_instance") +
                      root.findall(".//sys_hub_step") + root.findall(".//action")):
        atype = (_txt(action_el,"action_type") or _txt(action_el,"type") or "").lower()
        label = _txt(action_el,"name") or _txt(action_el,"label") or f"Step {step_order}"
        if "approval" in atype or "approve" in label.lower():
            step_type = "approval"
            approver = _txt(action_el,"approver") or _txt(action_el,"assigned_to") or "Manager"
            result["approvals"].append({
                "stage": label, "approver_type": "user",
                "approver": approver, "jsm_equivalent": "JSM Approval step on workflow transition"
            })
        elif "if" in atype or "condition" in atype:
            step_type = "condition"
        elif "notify" in atype or "email" in atype:
            step_type = "notification"
            result["notifications"].append({
                "trigger": label,
                "recipients": _txt(action_el,"recipients") or "Requester",
                "jsm_equivalent": "Send email / Add comment automation action"
            })
        elif "script" in atype:
            step_type = "script"
        elif "subflow" in atype:
            step_type = "subflow"
        else:
            step_type = "action"
        result["steps"].append({
            "order": step_order, "type": step_type, "label": label,
            "sn_action_type": atype,
            "jsm_equivalent": SN_ACTION_TO_JSM.get(atype, "Edit issue fields"),
            "details": {"field": _txt(action_el,"field"), "value": _txt(action_el,"value"),
                        "condition": _txt(action_el,"condition")},
        })
        step_order += 1
    return result

def parse_update_set(root):
    result = {"source_type": "update_set", "name": "", "description": "",
               "trigger": {"type":"record_created","jsm_equivalent":"Issue created"},
               "variables": [], "steps": [], "approvals": [], "notifications": [],
               "transitions": [], "catalog_items": [], "workflows": [], "business_rules": []}
    us_el = root.find(".//sys_remote_update_set") or root.find(".//sys_update_set")
    if us_el is not None:
        result["name"] = _txt(us_el,"name") or "Update Set"
        result["description"] = _txt(us_el,"description")
    for ci_el in root.findall(".//sc_cat_item"):
        result["catalog_items"].append({
            "name": _txt(ci_el,"name"), "category": _txt(ci_el,"category"),
            "description": _txt(ci_el,"description"), "variables": [],
        })
    for var_el in root.findall(".//item_option_new"):
        result["variables"].append({
            "name": _txt(var_el,"name"),
            "label": _txt(var_el,"question_text") or _txt(var_el,"name"),
            "type": _txt(var_el,"type","string"),
            "mandatory": _txt(var_el,"mandatory","false"),
            "jsm_equivalent": "Custom field on JSM request type form",
        })
    for wf_el in root.findall(".//wf_workflow"):
        result["workflows"].append({
            "name": _txt(wf_el,"name"), "table": _txt(wf_el,"table"),
            "description": _txt(wf_el,"description"),
        })
    for act_el in root.findall(".//wf_activity"):
        atype = _txt(act_el,"type") or ""
        label = _txt(act_el,"name")
        stype = "approval" if "approval" in atype.lower() else (
            "notification" if "notification" in atype.lower() else "action")
        result["steps"].append({
            "order": len(result["steps"])+1, "type": stype, "label": label,
            "sn_action_type": atype,
            "jsm_equivalent": SN_ACTION_TO_JSM.get(atype.lower(),"Edit issue fields"),
            "details": {"workflow": _txt(act_el,"workflow")},
        })
    for br_el in root.findall(".//sys_script"):
        result["business_rules"].append({
            "name": _txt(br_el,"name"), "table": _txt(br_el,"collection"),
            "when": _txt(br_el,"when"), "condition": _txt(br_el,"condition"),
            "script_snippet": (_txt(br_el,"script") or "")[:300],
            "jsm_equivalent": "Jira Automation rule (Issue created/updated trigger)",
        })
    for apr_el in root.findall(".//sysapproval_approver") + root.findall(".//approval_definition"):
        result["approvals"].append({
            "stage": _txt(apr_el,"state") or "Approval",
            "approver_type": "group" if _txt(apr_el,"group") else "user",
            "approver": _txt(apr_el,"group") or _txt(apr_el,"approver"),
            "jsm_equivalent": "JSM Approval step on workflow transition",
        })
    for n_el in root.findall(".//sysevent_email_action"):
        result["notifications"].append({
            "trigger": _txt(n_el,"event_name"),
            "recipients": _txt(n_el,"recipient") or _txt(n_el,"to"),
            "template": _txt(n_el,"name"),
            "jsm_equivalent": "Send email / Add comment automation action",
        })
    return result

def parse_generic(root):
    result = {"source_type":"unknown","name":"Imported from ServiceNow","description":"",
               "trigger":{"type":"record_created","jsm_equivalent":"Issue created"},
               "variables":[],"steps":[],"approvals":[],"notifications":[],"transitions":[],"catalog_items":[]}
    for el in root.iter():
        tag = el.tag.lower()
        if "approval" in tag:
            result["approvals"].append({
                "stage": el.get("name", el.tag), "approver_type":"user",
                "approver": el.get("approver","Manager"),
                "jsm_equivalent":"JSM Approval step on workflow transition"
            })
        if "notification" in tag or "email_action" in tag:
            result["notifications"].append({
                "trigger": el.get("name",""), "recipients":"Requester",
                "jsm_equivalent":"Send email automation action"
            })
    return result

def generate_jsm_mapping(parsed):
    mapping = {"recommended_project_type":"ITSM","request_types":[],
               "workflow_statuses":[],"automation_rules":[],
               "approval_stages":[],"custom_fields":[]}
    name_lower = (parsed.get("name","") + parsed.get("description","")).lower()
    if any(w in name_lower for w in ["contract","legal","nda","agreement"]):
        mapping["recommended_project_type"] = "Legal / Contract Management"
    elif any(w in name_lower for w in ["hr","onboard","employee","people"]):
        mapping["recommended_project_type"] = "HR Service Management"
    elif any(w in name_lower for w in ["change","cab","deploy","release"]):
        mapping["recommended_project_type"] = "IT Change Management"
    elif any(w in name_lower for w in ["incident","outage","p1","critical"]):
        mapping["recommended_project_type"] = "IT Incident Management"
    status_set = {"Open","In Progress","Waiting for Approval","Resolved","Closed"}
    for step in parsed.get("steps",[]):
        label = step.get("label","")
        if label:
            status_set.add(SN_TO_JSM_STATUS.get(label.lower(), label))
    mapping["workflow_statuses"] = sorted(status_set)
    for apr in parsed.get("approvals",[]):
        mapping["approval_stages"].append({
            "stage": apr.get("stage","Approval"),
            "approver": apr.get("approver","Manager"),
            "jsm_config":"Add approval step to workflow transition in JSM project settings",
        })
    trigger = parsed.get("trigger",{})
    jsm_trigger = trigger.get("jsm_equivalent","Issue created")
    conditions, actions = [], []
    for step in parsed.get("steps",[]):
        if step["type"] == "condition": conditions.append(step["label"])
        elif step["type"] == "action": actions.append(f"→ {step.get('jsm_equivalent',step['label'])}")
        elif step["type"] == "notification": actions.append("→ Send email / Add comment")
    mapping["automation_rules"].append({
        "name": f"[Migrated] {parsed.get('name','SN Flow')}",
        "trigger": jsm_trigger, "conditions": conditions[:5], "actions": actions[:8],
        "note":"Review and enable this rule in JSM Project Settings → Automation",
    })
    for var in parsed.get("variables",[]):
        fname = var.get("label") or var.get("name","")
        if fname:
            sn_type = var.get("type","string").lower()
            jsm_type = ("Date picker" if "date" in sn_type else
                        "Select list" if sn_type in ("select_box","choice","reference") else
                        "Number" if sn_type in ("integer","decimal","currency") else
                        "Checkbox" if sn_type in ("boolean","checkbox") else
                        "Text field (multi-line)" if sn_type in ("journal","html","large_text") else
                        "Text field (single line)")
            mapping["custom_fields"].append({
                "name": fname, "jsm_field_type": jsm_type,
                "mandatory": var.get("mandatory","false") == "true",
                "jsm_field_type_key": FIELD_TYPE_MAP.get(jsm_type, FIELD_TYPE_MAP["Text field (single line)"]),
            })
    for ci in parsed.get("catalog_items",[]):
        if ci.get("name"):
            mapping["request_types"].append({
                "name": ci["name"], "description": ci.get("description",""),
                "jsm_api": "POST /rest/servicedeskapi/servicedesk/{id}/requesttype",
            })
    return mapping

def main():
    parser = argparse.ArgumentParser(description="Parse ServiceNow XML export → JSM migration JSON")
    parser.add_argument("--input","-i",required=True,help="ServiceNow XML file path")
    parser.add_argument("--output","-o",help="Output JSON file (default: stdout)")
    parser.add_argument("--verbose","-v",action="store_true")
    args = parser.parse_args()
    xml_path = Path(args.input)
    if not xml_path.exists():
        print(f"ERROR: File not found: {xml_path}", file=sys.stderr); sys.exit(1)
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as e:
        print(f"ERROR: Invalid XML — {e}", file=sys.stderr); sys.exit(1)
    export_type = detect_type(root)
    if export_type == "flow":
        parsed = parse_flow_designer(root)
    elif export_type in ("update_set","catalog","workflow"):
        parsed = parse_update_set(root)
    else:
        parsed = parse_generic(root)
        parsed["source_type"] = export_type
    parsed["jsm_mapping"] = generate_jsm_mapping(parsed)
    output = json.dumps(parsed, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(output)
        print(f"✅ Parsed '{parsed['name']}' ({export_type}) → {args.output}")
    else:
        print(output)
    if args.verbose:
        m = parsed["jsm_mapping"]
        print(f"\n{'='*55}", file=sys.stderr)
        print(f"📋 {parsed['name']} ({export_type})", file=sys.stderr)
        print(f"   Trigger: {parsed.get('trigger',{}).get('jsm_equivalent','—')}", file=sys.stderr)
        print(f"   Steps: {len(parsed['steps'])} | Approvals: {len(parsed['approvals'])} | Notifications: {len(parsed['notifications'])}", file=sys.stderr)
        print(f"   JSM Project Type: {m['recommended_project_type']}", file=sys.stderr)
        print(f"   Custom Fields: {len(m['custom_fields'])} | Request Types: {len(m['request_types'])}", file=sys.stderr)
        print(f"{'='*55}", file=sys.stderr)

if __name__ == "__main__":
    main()
