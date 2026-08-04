# JSM Automation REST API Reference

## Base URL
```
https://{site}.atlassian.net/rest/cb-automation/latest
```

## Authentication
All requests use Basic Auth:
```
Authorization: Basic base64({email}:{api_token})
Content-Type: application/json
```

---

## List Automation Rules
```
GET /projects/{projectKey}/rules
```

---

## Create Automation Rule
```
POST /projects/{projectKey}/rules
```

### Full Payload Schema
```json
{
  "name": "Rule Name",
  "description": "Optional description",
  "state": "ENABLED",
  "trigger": {
    "component": {
      "schemaVersion": 1,
      "type": "TRIGGER_TYPE"
    }
  },
  "conditions": {
    "component": {
      "schemaVersion": 1,
      "type": "CONDITION_BLOCK",
      "value": {
        "conditionMatchType": "ALL",
        "conditions": []
      }
    }
  },
  "actions": []
}
```

---

## Common Trigger Types

### Issue Created
```json
{
  "type": "jira.issue.created"
}
```

### Issue Transitioned
```json
{
  "type": "jira.issue.transitioned",
  "value": {
    "toStatus": { "name": "In Progress" }
  }
}
```

### Approval Required
```json
{
  "type": "jira.issue.approval.required"
}
```

### Approval Completed (Approved)
```json
{
  "type": "jira.issue.approval.approved"
}
```

### Approval Rejected
```json
{
  "type": "jira.issue.approval.rejected"
}
```

### Scheduled
```json
{
  "type": "scheduled",
  "value": {
    "cronExpression": "0 9 * * MON",
    "timeZone": "America/Chicago"
  }
}
```

### Incoming Webhook
```json
{
  "type": "incoming.webhook"
}
```

---

## Common Condition Types

### Issue Matches JQL
```json
{
  "type": "jira.issue.condition.jql",
  "value": {
    "jql": "project = IT AND status = 'Pending Approval'"
  }
}
```

### Field Condition
```json
{
  "type": "jira.issue.condition.field.changed",
  "value": {
    "field": { "type": "STATUS" }
  }
}
```

---

## Common Action Types

### Transition Issue
```json
{
  "type": "jira.issue.transition",
  "value": {
    "transitionId": "21",
    "transition": { "name": "Approve" }
  }
}
```

### Assign Issue
```json
{
  "type": "jira.issue.assign",
  "value": {
    "assignee": { "accountId": "USER_ACCOUNT_ID" }
  }
}
```

### Add Comment
```json
{
  "type": "jira.issue.comment",
  "value": {
    "comment": {
      "version": 1,
      "type": "doc",
      "content": [{
        "type": "paragraph",
        "content": [{ "type": "text", "text": "Your request has been approved." }]
      }]
    }
  }
}
```

### Send Email
```json
{
  "type": "jira.issue.outgoing.email",
  "value": {
    "to": ["{{issue.reporter.email}}"],
    "subject": "Your request {{issue.key}} has been approved",
    "body": "Hello {{issue.reporter.displayName}},\n\nYour request has been approved."
  }
}
```

### Send Slack Notification
```json
{
  "type": "slack.message",
  "value": {
    "channel": "#it-approvals",
    "message": "Request {{issue.key}} requires approval: {{issue.url}}"
  }
}
```

### Edit Issue Field
```json
{
  "type": "jira.issue.field.edit",
  "value": {
    "field": { "type": "PRIORITY" },
    "value": { "name": "High" }
  }
}
```

### Call Webhook
```json
{
  "type": "outgoing.webhook",
  "value": {
    "url": "https://your-endpoint.com/webhook",
    "method": "POST",
    "body": "{\"issueKey\": \"{{issue.key}}\", \"status\": \"approved\"}"
  }
}
```

---

## Full Example: Approval Notification Rule

```json
{
  "name": "Notify reporter on approval decision",
  "state": "ENABLED",
  "trigger": {
    "component": {
      "schemaVersion": 1,
      "type": "jira.issue.approval.approved"
    }
  },
  "actions": [
    {
      "component": {
        "schemaVersion": 1,
        "type": "jira.issue.comment",
        "value": {
          "comment": {
            "version": 1,
            "type": "doc",
            "content": [{
              "type": "paragraph",
              "content": [{ "type": "text", "text": "✅ Your request has been approved and will be processed shortly." }]
            }]
          }
        }
      }
    },
    {
      "component": {
        "schemaVersion": 1,
        "type": "jira.issue.transition",
        "value": {
          "transition": { "name": "Start Progress" }
        }
      }
    }
  ]
}
```
