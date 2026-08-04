# ServiceNow Flow Designer → JSM Automation Mapping Guide

## Trigger Mapping
| ServiceNow Trigger | JSM Automation Trigger |
|---|---|
| Record Created | jira.issue.created |
| Record Updated | jira.issue.updated |
| Field Changed | jira.issue.field.changed |
| Approval Requested | jira.issue.approval.required |
| Approval Approved | jira.issue.approval.approved |
| Approval Rejected | jira.issue.approval.rejected |
| Scheduled (interval) | scheduled (cron) |
| Subflow called | incoming.webhook |
| SLA Breached | jira.issue.sla.breached |

## Condition Mapping
| ServiceNow | JSM Condition |
|---|---|
| Field is | jira.issue.condition.field.changed |
| Record matches filter | jira.issue.condition.jql |
| User is member of group | jira.issue.condition.user.in.group |
| AND / OR blocks | conditionMatchType: ALL / ANY |

## Action Mapping
| ServiceNow Action | JSM Action |
|---|---|
| Set field value | jira.issue.field.edit |
| Assign to user | jira.issue.assign |
| Add comment | jira.issue.comment |
| Send notification | jira.issue.outgoing.email |
| Send Slack message | slack.message |
| Call REST API | outgoing.webhook |
| Change state | jira.issue.transition |
| Create record | jira.issue.create |
| Run subflow | outgoing.webhook (chain) |
| Log | jira.issue.comment (internal) |

## Parsing ServiceNow XML
When given ServiceNow Flow XML:
1. Find `<sys_hub_flow>` — root flow element
2. Find `<sys_hub_trigger_instance>` — extract trigger type
3. Find `<sys_hub_action_instance>` elements — extract actions in order
4. Find `<sys_hub_flow_logic>` — extract conditions/branching
5. Look for `<sys_hub_step_ext>` with approval type — map to JSM approval trigger
6. Find notification actions (`send_notification`) — map to jira.issue.outgoing.email

## Common ServiceNow XML Patterns
```xml
<!-- Approval Step -->
<sys_hub_step_ext>
  <action_type>approval</action_type>
  <approver_source>role</approver_source>
</sys_hub_step_ext>

<!-- Notification -->
<sys_hub_step_ext>
  <action_type>send_notification</action_type>
  <notification>EMAIL_TEMPLATE_ID</notification>
</sys_hub_step_ext>

<!-- State transition -->
<sys_hub_step_ext>
  <action_type>update_record</action_type>
  <field_name>state</field_name>
  <field_value>approved</field_value>
</sys_hub_step_ext>
```
