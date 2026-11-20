# SEO Playbook — Genesis

> Source de vérité pour l'usage Ahrefs + stratégie SEO. Rédigé 2026-05-22 après audit complet.
> Tout ajout/retrait d'endpoint Ahrefs doit être documenté ICI.

## 1. Goal du module SEO

**Analyser l'URL du site client → identifier les corrections prioritaires → améliorer le SEO.**

Ce n'est PAS un dashboard de métriques générique. C'est un outil d'audit + action.

## 2. Budget Ahrefs

| Paramètre | Valeur | Justification |
|---|---|---|
| Forfait | **10 000 unités / mois** | API key actuelle |
| Reset | Le 17 de chaque mois | Cycle de facturation Ahrefs |
| Cible mensuelle | **~7 000 unités** (70%) | Marge 30% pour ad-hoc |
| Gate dans `cost_tracker.py` | `check_ahrefs_budget()` | Voir section 5 |

### Conso prévue selon le nouveau plan

| Bloc | Endpoints | Fréquence | Coût mensuel estimé |
|---|---|---|---:|
| Daily tracking | `site-explorer/metrics` × 2 sites | quotidien (6h UTC) | ~3 000 |
| Audit mensuel | `site-audit/issues` + `domain-rating` + `organic-keywords` + `pages-by-traffic` + `broken-backlinks` + `organic-competitors` × 2 sites | 1×/mois (1er 6h UTC) | ~1 400 |
| Recherche kw à la demande | `keywords-explorer/*` + `serp-overview` | déclenchement manuel | ~2 500 |
| Réserve | | | ~3 100 |

## 3. Classement des endpoints par tier

### Tier 1 — Essentiel (`critical=True`)

| Endpoint | Fréquence | Apport |
|---|---|---|
| `site-explorer/metrics` | **Daily** | Trafic, kw, valeur — KPI de trajectoire — **BYPASS gate budget** (toujours autorisé, jamais bloqué, décision 2026-05-22) |
| `site-explorer/domain-rating` | **Monthly** | Autorité (bouge lentement) |
| `site-explorer/organic-keywords` | **Monthly** | Identifie positions 4–20 = corrections rentables |
| `site-explorer/pages-by-traffic` (≡ top-pages) | **Monthly** | Pages qui rapportent — où concentrer l'effort |
| `site-audit/issues` ⭐ | **Monthly** | **LE module des corrections techniques** |

### Tier 2 — Action directe (`critical=True`)

| Endpoint | Fréquence | Apport |
|---|---|---|
| `site-explorer/broken-backlinks` | **Monthly** | Backlinks → 404 à récupérer par redirect 301 |
| `site-explorer/best-by-int-links` | **Trimestriel** | Audit maillage interne |
| `site-explorer/anchors` | **Trimestriel** | Détecter sur-optimisation (risque Google) |
| `site-explorer/organic-competitors` | **Monthly** | Qui imiter/dépasser |

### Tier 3 — Recherche (`critical=False`)

| Endpoint | Fréquence | Apport |
|---|---|---|
| `keywords-explorer/overview` | À la demande | Métriques d'un kw avant rédaction |
| `keywords-explorer/matching-terms` | À la demande | Variantes longue traîne sur 1 seed |
| `keywords-explorer/related-terms` | À la demande | Enrichir un cluster sémantique |
| `keywords-explorer/search-suggestions` | À la demande | Idées contenu autour d'un kw |
| `serp-overview` | À la demande | Top 10 Google pour un kw |

### Tier 4 — Banni (ne plus utiliser)

| Endpoint | Raison |
|---|---|
| `keywords-explorer/volume-history` | Inutile sauf marché saisonnier |
| `site-explorer/metrics-by-country` | Inutile pour stratégie FR mono-pays |
| `site-explorer/best-by-ext-links` | Redondant avec top-pages + backlinks-stats |
| `site-explorer/outlinks-stats` | Informatif mais jamais actionnable |
| `site-explorer/backlinks-stats` | Agrégat peu actionnable |

## 4. Scripts en place

| Script | Rôle | Cron |
|---|---|---|
| `scripts/ahrefs_daily.py` | Daily metrics minimaliste (100u/jour) | `0 6 * * *` |
| `scripts/ahrefs_monthly_audit.py` | Audit Tier 1+2 + Site Audit | `0 6 1 * *` |
| `scripts/seo.py` | Run on-demand (gate intégrée dans `ahrefs_get`) | Manuel via UI |
| `scripts/seo_strategy_agent.py` | Génère des recommandations à partir des audits (DeepSeek) | `0 7 * * 1` |
| `scripts/cost_tracker.py` | Logging + budget gate `check_ahrefs_budget()` | — |

## 5. Budget Gate — `check_ahrefs_budget()`

**Tout appel à Ahrefs DOIT passer par la gate.** Implémenté dans `scripts/cost_tracker.py`.

```python
from cost_tracker import check_ahrefs_budget

ok, info = check_ahrefs_budget(cost_estimate=200, critical=True)
if not ok:
    print(f"Bloqué : {info['reason']}")
    return
```

Variables `.env` (optionnelles) :
- `AHREFS_BUDGET_WARN_PCT` (défaut 70) — seuil d'alerte
- `AHREFS_BUDGET_BLOCK_PCT` (défaut 90) — seuil de blocage des Tier 3/4
- `AHREFS_BUDGET_RESERVE` (défaut 500) — unités minimum à garder dispo

Décisions :
- `OK` : conso < 70% → tous les appels passent
- `WARN` : 70% ≤ conso < 90% → Tier 1/2 passent, Tier 3/4 bloqués
- `BLOCK` : conso > 90% ou > limite → tout bloqué sauf si `critical=True` ET reste sous limite

## 6. Site Audit projects Ahrefs

| Site | Domain | project_id | Status |
|---|---|---|---|
| LCR | leclientroi.com | **8344256** | ✅ Configuré (`Leclientroi`, health=100, 97 warnings, 95 notices) |
| MKD | mkdgroupe.com | **À CRÉER** | ⚠️ Pas de projet — créer dans [app.ahrefs.com/site-audit](https://app.ahrefs.com/site-audit) |

Quand un nouveau projet est créé :
1. Récupérer le `project_id` via `GET /v3/site-audit/projects`
2. Mettre à jour la table `SITES` dans `scripts/ahrefs_monthly_audit.py`

## 7. Rôle du SEO Strategist (agent)

`scripts/seo_strategy_agent.py` — runs lundi 7h UTC.

**Responsabilité** : transformer les audits Ahrefs (caches JSON dans `memory/seo/`) en **recommandations actionnables** via DeepSeek, sauvegardées dans `memory/seo/recommendations.json`.

**Inputs** :
- `memory/seo/{site}-audit-latest.json` (monthly audit)
- `memory/seo/{site}-metrics-latest.json` (daily metrics)

**Output attendu** : `recommendations.json` avec liste typée `[{site, priority, type, title, action, ahrefs_data}]`.

**Ce qu'il n'a PAS fait jusqu'à présent (cause de l'audit du 2026-05-22)** :
- Pas de surveillance de la conso Ahrefs
- Pas de classement par tier des endpoints
- Pas d'alerte quand dépassement de budget
- → à corriger dans une prochaine itération de l'agent (ajouter une étape "audit budget" qui produit une reco quand le quota est dépassé ou prévu de l'être)

## 8. Historique des décisions

- **2026-05-22** : Audit complet conso Ahrefs (159% du quota). Refonte :
  - `cost_tracker.py` : ajout `check_ahrefs_budget()`
  - `ahrefs_daily.py` : refactor minimaliste (metrics only) — ancienne version → `ahrefs_daily.py.bak-2026-05-22`
  - `ahrefs_monthly_audit.py` : nouveau script Tier 1+2
  - `seo.py` : gate ajoutée dans `ahrefs_get()`
  - Cron mensuel ajouté (`0 6 1 * *`)

- **2026-05-22 (additif)** :
  - `seo.py --report full` **DÉSACTIVÉ** (sys.exit dans main()). Trop coûteux (~3 100u/run/site). Remplacé par `ahrefs_monthly_audit.py`.
  - `seo.py --report keywords --kw "..."` → **max 1× tous les 2 mois** (vs autre fois). Coût ~2 000u/lookup.
  - `site-explorer/metrics` (Tier 1, daily) → **bypass gate budget** : jamais bloqué même en dépassement. C'est le seul endpoint en bypass.
- **2026-06-17** : Prochain reset budget — vérifier que les nouveaux scripts tournent correctement.

## 9. Endpoints Ahrefs API qu'on pourrait utiliser en plus

Disponibles mais non utilisés :
- `gsc/keywords`, `gsc/pages`, `gsc/ctr-by-position` — vraies données Google Search Console (gratuit côté Ahrefs si GSC connecté) — **mis en pause par décision user 2026-05-22**
- `rank-tracker/overview`, `rank-tracker/competitors-overview` — suivi positions kw cibles + comparaison concurrents (~50u/run)
- `web-analytics/*` — si Ahrefs Web Analytics activé

À reconsidérer dans 1–2 mois si le budget le permet.
