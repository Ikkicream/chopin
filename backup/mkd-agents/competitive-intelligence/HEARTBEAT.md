# HEARTBEAT.md — Competitive Intelligence Agent

Run this checklist on every heartbeat.

## 1. Identity and Context

- `GET /api/agents/me` — confirm id, companyId, budget.
- Check env: `PAPERCLIP_TASK_ID`, `PAPERCLIP_WAKE_REASON`, `PAPERCLIP_WAKE_COMMENT_ID`.

## 2. Get Assignments

- `GET /api/agents/me/inbox-lite`
- Prioritize `in_progress` first, then `todo`. Skip `blocked` if no new context (dedup rule).
- If `PAPERCLIP_TASK_ID` is set and assigned to you, prioritize that task.

## 3. Checkout and Work

- Always checkout before working: `POST /api/issues/{id}/checkout`
- Never retry a 409 — move to next task.

## 4. RSS Intelligence Work

For each assigned task (typically weekly CI scan):

1. **Fetch the 5 RSS feeds** (WebFetch each URL).
2. **Filter new articles** published since your last run (check `$AGENT_HOME/memory/` for last run date).
3. **Score each article** 0–10 for SEO relevance to mkdgroupe.com:
   - Theme: marketing / CRM / email / SMS / data
   - Estimated search volume
   - Competitive difficulty
4. **Deduplicate** against `site:mkdgroupe.com [keyword]` for articles scoring ≥7.
5. **Post results** as a comment on the assigned task — even if no qualifying articles found, post a summary.
6. **Mark task done** with a closing comment listing findings.

## 5. No Qualifying Content

If 0 articles reach score ≥7:
- Post a comment on the task explaining what was found and why nothing qualifies.
- Mark the task `done`.
- Do NOT leave the task as `todo` or `in_progress` without a comment.

## 6. Exit

- Always comment on in_progress work before exiting.
- Update `$AGENT_HOME/memory/YYYY-MM-DD.md` with run summary.
