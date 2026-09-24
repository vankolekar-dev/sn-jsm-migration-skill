#!/usr/bin/env python3
"""
sn_complexity_scorer.py — Risk & Complexity Scoring Engine for ServiceNow → JSM Migration

Scores a list of parsed ServiceNow exports and returns an overall
migration complexity rating (LOW / MEDIUM / HIGH / CRITICAL) with
a breakdown of contributing factors.

Used by sn_assessor.py — can also be run standalone:
    python3 scripts/sn_complexity_scorer.py --input assessment.json
"""

import argparse, json, sys
from pathlib import Path

# ── Scoring Weights ───────────────────────────────────────────────────────────
# Each factor contributes points to the overall score (0–100).
# Higher score = higher complexity / risk.

SCORING_FACTORS = {
    # HIGH RISK items (blockers)
    "scripts":          {"weight": 8,  "label": "Custom scripts",          "severity": "HIGH"},
    "business_rules":   {"weight": 7,  "label": "Business rules",          "severity": "HIGH"},
    "client_scripts":   {"weight": 7,  "label": "Client-side scripts",     "severity": "HIGH"},
    "acls":             {"weight": 6,  "label": "ACL / Security rules",    "severity": "HIGH"},
    "subflows":         {"weight": 5,  "label": "Nested subflows",         "severity": "HIGH"},
    "ci_records":       {"weight": 4,  "label": "CMDB CI records",         "severity": "HIGH"},
    # MEDIUM RISK items (need UI work)
    "ui_policies":      {"weight": 4,  "label": "UI policies",             "severity": "MEDIUM"},
    "sla_definitions":  {"weight": 3,  "label": "SLA definitions",         "severity": "MEDIUM"},
    "workflows":        {"weight": 3,  "label": "Custom workflows",        "severity": "MEDIUM"},
    "kb_articles":      {"weight": 2,  "label": "Knowledge base articles", "severity": "MEDIUM"},
    "approvals":        {"weight": 2,  "label": "Approval stages",         "severity": "MEDIUM"},
    # LOW RISK items (automatable)
    "steps":            {"weight": 0.5, "label": "Total flow steps",       "severity": "LOW"},
    "notifications":    {"weight": 0.5, "label": "Notifications",          "severity": "LOW"},
    "catalog_items":    {"weight": 0.3, "label": "Catalog items",          "severity": "LOW"},
    "custom_fields":    {"weight": 0.2, "label": "Custom fields",          "severity": "LOW"},
}

# Thresholds for overall score → risk label
RISK_LEVELS = [
    (0,  20,  "LOW",      "🟢", "Migration is straightforward. Most items can be automated."),
    (20, 40,  "MEDIUM",   "🟡", "Migration requires planning. Some manual UI steps needed."),
    (40, 65,  "HIGH",     "🔴", "Complex migration. Significant manual remediation required."),
    (65, 100, "CRITICAL", "🚨", "Very complex migration. Requires expert Atlassian partner involvement."),
]

# Per-file complexity cap (so one huge file doesn't dominate unfairly)
PER_FILE_SCORE_CAP = 60


def score_single(parsed):
    """Score a single parsed export. Returns a dict with score and breakdown."""
    score = 0
    breakdown = []

    s = parsed.get("summary_counts", {})

    # Build counts from parsed data
    counts = {
        "scripts":         len(parsed.get("scripts", [])),
        "business_rules":  len(parsed.get("business_rules", [])),
        "client_scripts":  len(parsed.get("client_scripts", [])),
        "acls":            len(parsed.get("acls", [])),
        "subflows":        len(parsed.get("subflows", [])),
        "ci_records":      len(parsed.get("ci_records", [])),
        "ui_policies":     len(parsed.get("ui_policies", [])),
        "sla_definitions": len(parsed.get("sla_definitions", [])),
        "workflows":       len(parsed.get("workflows", [])),
        "kb_articles":     len(parsed.get("articles", [])),
        "approvals":       len(parsed.get("approvals", [])),
        "steps":           len(parsed.get("steps", [])),
        "notifications":   len(parsed.get("notifications", [])),
        "catalog_items":   len(parsed.get("catalog_items", [])),
        "custom_fields":   len(parsed.get("jsm_mapping", {}).get("custom_fields", [])),
    }

    for key, factor in SCORING_FACTORS.items():
        count = counts.get(key, 0)
        if count == 0:
            continue
        # Diminishing returns: log-like scaling so 100 scripts ≠ 100x 1 script
        scaled = min(count, 10) * factor["weight"] + max(0, count - 10) * factor["weight"] * 0.3
        contribution = round(min(scaled, factor["weight"] * 12), 1)
        score += contribution
        breakdown.append({
            "factor": factor["label"],
            "count": count,
            "severity": factor["severity"],
            "score_contribution": contribution,
        })

    score = min(round(score, 1), PER_FILE_SCORE_CAP)
    breakdown.sort(key=lambda x: -x["score_contribution"])

    return {
        "name": parsed.get("name", "?"),
        "source_type": parsed.get("source_type", "?"),
        "score": score,
        "counts": counts,
        "breakdown": breakdown,
    }


def score_complexity(parsed_list):
    """
    Score a list of parsed ServiceNow exports.
    Returns overall complexity assessment dict.
    """
    if not parsed_list:
        return {"overall_risk": "UNKNOWN", "score": 0, "label": "No files to assess", "items": []}

    scored_items = []
    total_score = 0

    for parsed in parsed_list:
        if parsed is None:
            continue
        item_score = score_single(parsed)
        scored_items.append(item_score)
        total_score += item_score["score"]

    # Aggregate score: sum with a ceiling
    # Multiple files add complexity but with diminishing returns
    n = len(scored_items)
    if n == 1:
        agg_score = scored_items[0]["score"]
    else:
        # Base is the max single score, plus a fraction for additional complexity
        max_score = max(s["score"] for s in scored_items)
        additional = sum(s["score"] for s in scored_items if s != max(scored_items, key=lambda x: x["score"]))
        agg_score = min(max_score + additional * 0.4, 100)

    agg_score = round(agg_score, 1)

    # Map score → risk level
    overall_risk = "UNKNOWN"
    risk_icon = "⚪"
    risk_description = ""
    for lo, hi, level, icon, desc in RISK_LEVELS:
        if lo <= agg_score < hi:
            overall_risk = level
            risk_icon = icon
            risk_description = desc
            break
    if agg_score >= 65:
        overall_risk = "CRITICAL"
        risk_icon = "🚨"
        risk_description = RISK_LEVELS[-1][4]

    # Aggregate breakdown
    factor_totals = {}
    for item in scored_items:
        for b in item["breakdown"]:
            f = b["factor"]
            if f not in factor_totals:
                factor_totals[f] = {"factor": f, "severity": b["severity"], "count": 0, "score_contribution": 0}
            factor_totals[f]["count"] += b["count"]
            factor_totals[f]["score_contribution"] += b["score_contribution"]

    aggregated_breakdown = sorted(factor_totals.values(), key=lambda x: -x["score_contribution"])

    # Timeline estimate
    if agg_score < 20:
        timeline = "2–4 weeks (small team, 1–2 engineers)"
    elif agg_score < 40:
        timeline = "4–8 weeks (1–2 engineers + JSM admin)"
    elif agg_score < 65:
        timeline = "2–3 months (dedicated migration team + Atlassian partner recommended)"
    else:
        timeline = "3–6 months (Atlassian certified partner strongly recommended)"

    # Partner recommendation
    partner_needed = agg_score >= 40
    partner_note = (
        "Atlassian certified migration partner strongly recommended for this complexity level."
        if partner_needed else
        "Migration can be self-managed using the jsm-workflow-builder skill and this assessment."
    )

    return {
        "overall_risk": overall_risk,
        "risk_icon": risk_icon,
        "score": agg_score,
        "label": risk_description,
        "estimated_timeline": timeline,
        "partner_recommended": partner_needed,
        "partner_note": partner_note,
        "total_files_scored": n,
        "aggregated_breakdown": aggregated_breakdown,
        "items": scored_items,
    }


# ── Standalone CLI ────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Score migration complexity from assessment JSON")
    p.add_argument("--input", "-i", required=True, help="assessment.json from sn_assessor.py")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    data = json.loads(Path(args.input).read_text())
    parsed_list = data.get("parsed_details", [])
    if not parsed_list:
        print("ERROR: No parsed_details in assessment JSON. Run sn_assessor.py first.", file=sys.stderr)
        sys.exit(1)

    result = score_complexity(parsed_list)
    print(json.dumps(result, indent=2))

    if args.verbose:
        print(f"\n{result['risk_icon']} Overall Risk: {result['overall_risk']} (Score: {result['score']}/100)")
        print(f"   {result['label']}")
        print(f"   Timeline: {result['estimated_timeline']}")
        print(f"\n📊 Score Breakdown:")
        for b in result["aggregated_breakdown"]:
            bar = "█" * int(b["score_contribution"] / 2)
            print(f"  {b['factor']:<35} {b['count']:>4}x  +{b['score_contribution']:>5.1f}  {bar}")


if __name__ == "__main__":
    main()
