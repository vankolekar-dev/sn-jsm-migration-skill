# FedRAMP / GovCloud Engagement Guide

## Overview
This guide covers how to use the SN → JSM Migration Skill safely in FedRAMP customer engagements where:
- ServiceNow is on GovCloud
- JSM is on Atlassian Government Cloud (AGC / atlassian-us-gov-mod.net)
- Rovo Dev / RoHub is running on the PS consultant's commercial machine

## Architecture
```
PS Consultant Mac (commercial)
  └── RoHub / Rovo CLI
       ├── Parses SN XML locally (never leaves consultant's machine)
       └── Calls AGC REST APIs via HTTPS
            └── JSM (atlassian-us-gov-mod.net)
```

## Pre-Engagement Checklist
- [ ] Confirm customer's JSM instance URL (atlassian-us-gov-mod.net)
- [ ] Request a time-limited Admin API token scoped to migration project only
- [ ] Confirm SN XML does NOT contain CUI/PII (sanitize if needed)
- [ ] Document token creation date and planned revocation date
- [ ] Get customer written approval for tool usage during migration

## Token Scopes Required
Minimum scopes for the migration API token:
- `write:servicedesk-request` — create request types
- `write:jira-work` — create custom fields
- `read:jira-work` — read existing configuration
- `read:servicedesk-request` — read existing request types

## Post-Migration Cleanup Checklist
- [ ] Revoke the migration API token in customer's Atlassian admin
- [ ] Verify no credentials stored in script outputs or log files
- [ ] Confirm all automation rules are DISABLED until customer reviews
- [ ] Hand off workflow guide to customer admin for final workflow creation
- [ ] Document what was created (save the script output report)

## Data Handling
- SN XML is parsed **in memory only** — not stored by Rovo Dev
- API calls are **outbound only** from consultant's machine to AGC
- No customer data passes through Atlassian commercial cloud
- Script outputs (JSON, guides) should be **deleted after migration**

## Approved Use Pattern
This tool is approved for use as **migration tooling** (not production tooling):
- Time-limited (duration of PS engagement only)  
- Consultant-operated (not customer self-service)
- Token revoked immediately after migration completes
- Equivalent to: Jira Cloud Migration Assistant, CSV importers, ScriptRunner

## NOT Approved For
- Ongoing/production automation of customer JSM instances
- Storing customer API tokens in any persistent config
- Running unattended on customer infrastructure
