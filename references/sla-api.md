# JSM SLA Configuration API Reference

## List SLAs for a Service Desk
GET /rest/servicedeskapi/servicedesk/{serviceDeskId}/sla

## Get SLA for a Specific Issue
GET /rest/servicedeskapi/request/{issueIdOrKey}/sla

## Create SLA via Jira REST API (v3)
POST /rest/api/3/slametric

```json
{
  "name": "Time to first response",
  "description": "Time from issue creation to first agent comment",
  "goals": [
    {
      "jqlQuery": "priority = High",
      "duration": { "hours": 4 },
      "calendarId": "CALENDAR_ID"
    },
    {
      "jqlQuery": "priority = Medium",
      "duration": { "hours": 8 },
      "calendarId": "CALENDAR_ID"
    },
    {
      "jqlQuery": "priority = Low",
      "duration": { "hours": 24 },
      "calendarId": "CALENDAR_ID"
    }
  ],
  "startConditions": [
    { "factoryClass": "com.atlassian.servicedesk.internal.sla.factory.IssueCreatedSLAConditionFactory" }
  ],
  "stopConditions": [
    { "factoryClass": "com.atlassian.servicedesk.internal.sla.factory.FirstResponseSLAConditionFactory" }
  ],
  "pauseConditions": []
}
```

## Common SLA Start/Stop Conditions
- Issue created: IssueCreatedSLAConditionFactory
- First response: FirstResponseSLAConditionFactory  
- Issue resolved: IssueResolvedSLAConditionFactory
- Status change: StatusChangeSLAConditionFactory
- Comment added: CommentAddedSLAConditionFactory

## SLA Breach Automation
Trigger: SLA breached
Action: escalate priority + notify manager
```json
{
  "name": "Escalate on SLA Breach",
  "trigger": { "component": { "type": "jira.issue.sla.breached" } },
  "actions": [
    {
      "component": {
        "type": "jira.issue.field.edit",
        "value": { "field": { "type": "PRIORITY" }, "value": { "name": "High" } }
      }
    }
  ]
}
```
