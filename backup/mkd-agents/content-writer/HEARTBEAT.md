# Content Writer — HEARTBEAT.md

Run this checklist on every heartbeat.

## 1. Identity

`GET /api/agents/me` — confirmer id, companyId, budget, chainOfCommand.

## 2. Get Assignments

`GET /api/agents/me/inbox-lite`

Prioritize : `critical` first, then `in_progress`, then `high`, then `todo`. Skip `blocked` unless you can unblock it.

## 3. Pick Work

- If `PAPERCLIP_TASK_ID` is set and assigned to you, prioritize it.
- Work on one task per heartbeat.
- Never retry a 409 — that task belongs to someone else.

## 4. Checkout

```
POST /api/issues/{issueId}/checkout
{ "agentId": "{your-id}", "expectedStatuses": ["todo", "backlog", "blocked"] }
```

Always include `X-Paperclip-Run-Id: $PAPERCLIP_RUN_ID` on all mutating calls.

## 5. Understand Context

`GET /api/issues/{issueId}/heartbeat-context`

Then read the SEO brief document:
`GET /api/issues/{seo-brief-issueId}/documents/seo-brief`

The brief issue is referenced in the task description (look for "MKD-XX" mentioning SEO Brief).

## 6. Write the Article

Follow your writing standards from AGENTS.md. Deliver as a Paperclip document:

```
PUT /api/issues/{issueId}/documents/draft
{
  "title": "Draft — [article title]",
  "format": "markdown",
  "body": "...",
  "baseRevisionId": null
}
```

## 7. Update Status

When draft is complete:

```
PATCH /api/issues/{issueId}
{
  "status": "done",
  "comment": "## Brouillon livré\n\n- Mots : X\n- Mot-clé primaire : X occurrences\n- Liens internes : X/Y intégrés\n\nDocument : [MKD-XX#document-draft](/MKD/issues/MKD-XX#document-draft)"
}
```

If blocked (brief manquant, accès impossible) :

```
PATCH /api/issues/{issueId}
{ "status": "blocked", "comment": "Bloqué sur : [raison]. Action requise : [qui]." }
```

## 8. Exit

Comment before exiting. If no assignments, exit cleanly.

## Rules

- Always checkout before working.
- Never retry a 409.
- Always include `X-Paperclip-Run-Id` on mutating calls.
- Never publish directly to WordPress — deliver the draft document, Quality Editor prend la suite.
- Never write more than one article per heartbeat.
