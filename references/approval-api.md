# JSM Approval Configuration API Reference

## How Approvals Work in JSM
Approvals are configured on workflow transitions and tied to specific roles or users.
When an issue reaches a status that requires approval, JSM prompts the approver.

## Add Approval to a Service Desk Request Type
POST /rest/servicedeskapi/servicedesk/{serviceDeskId}/requesttype/{requestTypeId}/approval

```json
{
  "approvers": [
    {
      "type": "role",
      "roleId": "ROLE_ID"
    }
  ],
  "condition": {
    "type": "approver-count",
    "count": 1
  }
}
```

## Get Approvals for an Issue
GET /rest/servicedeskapi/request/{issueIdOrKey}/approval

## Answer an Approval (Approve/Reject)
POST /rest/servicedeskapi/request/{issueIdOrKey}/approval/{approvalId}
```json
{
  "decision": "approve"
}
```
or
```json
{
  "decision": "decline"
}
```

## Automation Rules for Approvals

### Trigger: Approval Required
```json
{ "type": "jira.issue.approval.required" }
```

### Trigger: Request Approved
```json
{ "type": "jira.issue.approval.approved" }
```

### Trigger: Request Rejected
```json
{ "type": "jira.issue.approval.rejected" }
```

### Action: Auto-transition after approval
```json
{
  "type": "jira.issue.transition",
  "value": { "transition": { "name": "Start Progress" } }
}
```

### Action: Notify approver (send email)
```json
{
  "type": "jira.issue.outgoing.email",
  "value": {
    "to": ["{{issue.approvers.email}}"],
    "subject": "Approval required: {{issue.summary}}",
    "body": "Please review and approve request {{issue.key}}: {{issue.url}}"
  }
}
```

## Full Approval Reminder Automation Example
Trigger: Scheduled (daily)
Condition: issue has pending approval > 2 days
Action: send reminder email to approvers

```json
{
  "name": "Approval Reminder - Escalation",
  "state": "ENABLED",
  "trigger": {
    "component": {
      "schemaVersion": 1,
      "type": "scheduled",
      "value": { "cronExpression": "0 9 * * *", "timeZone": "America/Chicago" }
    }
  },
  "conditions": {
    "component": {
      "schemaVersion": 1,
      "type": "jira.issue.condition.jql",
      "value": {
        "jql": "status = 'Pending Approval' AND updated <= -2d"
      }
    }
  },
  "actions": [
    {
      "component": {
        "schemaVersion": 1,
        "type": "jira.issue.outgoing.email",
        "value": {
          "to": ["{{issue.approvers.email}}"],
          "subject": "REMINDER: Approval pending for {{issue.key}}",
          "body": "This request has been waiting for your approval for over 2 days.\n\nPlease review: {{issue.url}}"
        }
      }
    }
  ]
}
```
