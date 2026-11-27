# Weekly Competitive Intelligence Scan — Standard Operating Procedure

**Last Updated:** 2026-04-19
**Schedule:** Every Saturday, 10:00 AM
**Duration:** ~30 minutes

## Objective

Monitor 5 competitor RSS feeds weekly, score articles for SEO relevance to mkdgroupe.com (0-10), identify editorial gaps, and escalate articles scoring ≥7/10 to CEO.

---

## Weekly Workflow (Step by Step)

### Step 1: Fetch RSS Feeds (5 min)

Use `WebFetch` on these 5 URLs:

```
1. https://rss.app/feeds/aeiR14C99xJAFyor.xml       (MediasFlow)
2. https://rss.app/feed/rzWJuoSkGnaLEVxr            (RSS.app — INVALID)
3. https://rss.app/feeds/Kp1xGoR90Fm0ZSgv.xml      (WellPack)
4. https://rss.app/feeds/uo9P8Idf7rTsHV01.xml      (Sarbacane)
5. https://rss.app/feeds/_fxBzKedBRFAJ9Mzn.xml     (Mixed sources)
```

**Expected outcome:** Structured list of titles, URLs, publication dates.

---

### Step 2: Filter New Articles (5 min)

- **Load:** Most recent memory file from `$AGENT_HOME/memory/` (e.g., last week's run)
- **Compare:** Extract publication dates; filter for articles published AFTER last run
- **Deduplicate:** Check article URL against all prior reports (avoid re-reporting)

**Stop condition:** If 0 new articles, document "no new content" and proceed to Step 6.

---

### Step 3: Score SEO Relevance (10 min)

For each new article, assign score 0–10 based on:

| Criterion | Weight | Details |
|-----------|--------|---------|
| **Theme alignment** | 40% | Marketing, CRM, SMS, RCS, email, retail, data, SEO, compliance |
| **Search volume** | 30% | Estimated monthly searches; higher = higher score |
| **Competitive difficulty** | 20% | Can mkdgroupe.com realistically rank? Lower difficulty = higher score |
| **mkdgroupe audience relevance** | 10% | Does this solve a real problem for mkdgroupe customers? |

**Scoring rubric:**
- **9–10:** Exceptional — breakout trend, high volume, low competition, direct audience need
- **7–8:** High value — established topic, good volume, medium competition
- **5–6:** Medium value — useful but niche or oversaturated
- **3–4:** Low value — tangential or too niche
- **0–2:** No relevance — not related to mkdgroupe focus

---

### Step 4: Verify vs mkdgroupe.com (5 min)

For articles scoring ≥7:

- **Search:** `site:mkdgroupe.com [article topic/keyword]`
- **Check:** Does mkdgroupe.com already have content on this?
  - ✅ **Exists:** Note it as "duplicate" or "existing — consider refresh"
  - ❌ **Missing:** Flag as "true gap" or "new opportunity"

---

### Step 5: Escalate to CEO (3 min)

**Post to Paperclip:** Create comment on assigned task (MKD-XX) with:

```markdown
## Competitive Intelligence Report — YYYY-MM-DD

### 🎯 High-Priority Articles (≥7/10)

| Rank | Title | Source | Score | mkdgroupe Status | Action |
|------|-------|--------|-------|-----------------|--------|
| 1 | [Article Title](url) | Source | 8/10 | Missing | Create new article |
| 2 | ... | ... | 7/10 | ... | ... |

### 📊 Content Gaps Identified
- Gap 1: ...
- Gap 2: ...

### 🔧 Feed Health
- Feed X: [status]
- Feed Y: [status]

### ⏭️ Next Steps
- [ ] Editorial review articles ≥7/10
- [ ] Assign writing tasks for gaps
```

**If 0 qualifying articles:** Post summary explaining why and recommendation for next week.

---

### Step 6: Update Memory (2 min)

1. **Create daily note:** `$AGENT_HOME/memory/YYYY-MM-DD.md`
   - Summary of findings
   - Run number
   - Count of articles by score band

2. **Update index:** `$AGENT_HOME/MEMORY.md`
   - Add entry to Daily Notes section with link and one-liner

3. **Archive articles:** Log all seen URLs in YAML to prevent re-reporting

---

## Exit Criteria

✅ **Task complete when:**
- All 5 feeds fetched
- Articles filtered and scored
- mkdgroupe.com verification done
- Paperclip comment posted (or "no new articles" note)
- Memory updated

---

## Known Issues & Workarounds

| Issue | Status | Workaround |
|-------|--------|-----------|
| **Feed 2 (RSS.app) broken** | ❌ Ongoing | Returns HTML, not RSS. Replace URL if valid URL exists. |
| **Feed 1 (MediasFlow) inactive** | 🟡 Stalled since 2026-02-13 | Deprecate if no activity by 2026-05-15. |
| **Paperclip inbox access** | ⚠️ Limited | Use `paperclip inbox-lite` skill; manual task lookup if needed. |
| **mkdgroupe.com dynamic content** | ⚠️ Limitation | Site:search works; WebFetch may not capture all articles. Use manual verification if uncertain. |

---

## Metrics to Track

- **Articles found per week:** Current average ~5–10 qualifying
- **Feed reliability:** Which feeds consistently produce ≥7 content?
- **Duplication rate:** Should be <5% (low repost rate)
- **Time to report:** Target ≤2 hours from fetch to CEO notification

---

_Standard Operating Procedure — Review and update quarterly or when feeds change._
