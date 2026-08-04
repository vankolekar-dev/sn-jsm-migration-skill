# JSM Workflow API Reference

## Create Workflow
POST /rest/api/3/workflow
```json
{
  "name": "IT Service Request Workflow",
  "description": "Workflow for IT service requests with approvals",
  "statuses": [
    { "id": "1", "name": "Open" },
    { "id": "3", "name": "In Progress" },
    { "id": "10001", "name": "Pending Approval" },
    { "id": "10002", "name": "Approved" },
    { "id": "10003", "name": "Rejected" },
    { "id": "5", "name": "Resolved" },
    { "id": "6", "name": "Closed" }
  ],
  "transitions": [
    {
      "name": "Start Progress",
      "from": [{ "id": "1" }],
      "to": { "id": "3" },
      "type": "DIRECTED"
    },
    {
      "name": "Send for Approval",
      "from": [{ "id": "3" }],
      "to": { "id": "10001" },
      "type": "DIRECTED"
    },
    {
      "name": "Approve",
      "from": [{ "id": "10001" }],
      "to": { "id": "10002" },
      "type": "DIRECTED",
      "rules": {
        "postFunctions": [],
        "validators": [],
        "conditions": {
          "operator": "AND",
          "conditions": []
        }
      }
    },
    {
      "name": "Reject",
      "from": [{ "id": "10001" }],
      "to": { "id": "10003" },
      "type": "DIRECTED"
    },
    {
      "name": "Resolve",
      "from": [{ "id": "10002" }, { "id": "3" }],
      "to": { "id": "5" },
      "type": "DIRECTED"
    },
    {
      "name": "Close",
      "from": [{ "id": "5" }, { "id": "10003" }],
      "to": { "id": "6" },
      "type": "DIRECTED"
    }
  ]
}
```

## Get Workflow
GET /rest/api/3/workflow/search?workflowName={name}

## Assign Workflow to Project
POST /rest/api/3/workflowscheme
