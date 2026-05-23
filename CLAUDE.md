# Genesis — Plateforme SaaS multi-sites (LCR + MKD + futurs)

> **⚠️ AVANT TOUTE CHOSE : lire `STATE.md` à la racine du projet.**
> Source de vérité "où on en est". À mettre à jour AVANT chaque fin de session.
> Ne jamais répondre à un 'on reprend' / 'salut' / 'hello' sans l'avoir lu d'abord.

> **Doc archi complète** : `ARCHITECTURE.md` à la racine. Pool contacts mutualisé, dual-write, sectors centralisés, sécu AES — tout y est.

---

## Ce projet
Plateforme SaaS automatisant la **prospection cold email B2B** pour plusieurs sites cibles (LCR, MKD, futurs). Pipeline complet : Serper → email_validator → Mailnjoy → DeepSeek qualifier → Emelia (push + webhook retours) → CRM (pool mutualisé).

Stack : FastAPI + DuckDB côté serveur, Next.js 16 + shadcn v4 + Tailwind v4 côté UI.

---

## Les 2 sites actuels
- **LCR** — leclientroi.com (Emdash CMS) — SMS marketing local
- **MKD** — mkdgroupe.com (WordPress) — B2B data marketing, RGPD, RCS

Onboarding 16 steps prêt pour ajouter d'autres sites (`/onboarding`).

---

## Architecture data — POOL MUTUALISÉ

**Source de vérité contacts** : `data/contacts.duckdb` (2 tables) :
- `contacts` (master, PK email unique, 72 contacts actuellement)
- `contact_site_history` (relation N-N par site, état + history)

**Cooldowns** : 30j cross-site / 7j re-push même site. Blacklist globale (UNSUBSCRIBE/BOUNCE depuis n'importe quel site = bloqué partout).

**Dual-write actif** sur 5 maillons (toute écriture alimente pool + legacy en parallèle) : webhook Emelia + push Emelia + Tally sync + emelia_to_crm cron + scrape Serper.

DBs annexes :
- `data/god_mode.duckdb` : scrappe_pending, email_senders, emelia_events, god_mode_settings/state/logs/templates, accounts, site_credentials (AES Fernet)
- `data/auth.duckdb` : users, sessions, login_logs
- `data/contacts.duckdb` : pool mutualisé
- `data/crm/{lcr,mkd}.duckdb` : LEGACY, RO 30j puis drop

---

## Sécurité credentials

Clés API site-specific chiffrées AES Fernet dans `site_credentials`. Master key : `data/.master_key` (chmod 600 autoblog).

Disaster recovery : copie locale Mac à `~/.ssh/genesis-master-key` + README. Backup cron quotidien dans `backups/.master_key.bak`.

---

## Pages UI (sidebar Genesis)

| Section | Page | URL |
|---|---|---|
| Stratégie | Analyse SEO, Stratégie SEO, Agents IA | /site/[code]/seo /seo-strategy /agents |
| Contenu | Articles | /site/[code]/articles |
| **Commercial** | Vision (KPI+funnel+warmup) | /site/[code]/vision |
| | Scrapper (Serper multi-sect+région→ville) | /site/[code]/scrapper |
| | Acquisition (pool, Source+Secteur) | /site/[code]/acquisition |
| | Templates (vars Emelia natives) | /site/[code]/templates |
| | Campagnes (wizard 4 steps) | /site/[code]/campaigns |
| Admin | Setup & API | /site/[code]/setup |
| Global admin | Vue, Coûts, Logs système, Sécurité | /view /costs /admin/logs /security |
| | Onboarding 16 steps | /onboarding |

---

## Listes centralisées (1 source de vérité)

**Secteurs (16)** :
- Python : `scripts/god_mode_backend.py:SECTORS_GOD_MODE`
- UI : `genesis-ui/src/lib/sectors.ts`
- → pour ajouter un secteur : 2 lignes à modifier

**Honeypot RGPD/legal** : `scripts/email_validator.py:HONEYPOT_TERMS` (drop avant scrappe_pending). +21 substrings RGPD/CNIL/legal/compliance.

**Variables templates Emelia** (utiliser ces vars natives, JAMAIS les vieilles versions snake_case) :
- `{{firstName}}`, `{{lastName}}` (pas `{{first_name}}`/`{{last_name}}`)
- `{{field1}}` = société (pas `{{company}}`)
- `{{field2}}` = ville (pas `{{city}}`)
- `{{field3}}` = dept, `{{field4}}` = website
- `{{UNSUBSCRIBE_LINK}}` injecté auto par Emelia

---

## Crons actifs

```
30 6 * * 1-5    workflow_runner.py            # scrape + push prospects
 0 6 * * *      ahrefs_daily.py               # metrics
 0 6 1 * *      ahrefs_monthly_audit.py       # audit complet
 0 7 * * 1      seo_strategy_agent.py
 0 8 * * 1,4    brief_agent.py
 0 10 * * 3     content_agent.py --site lcr
 0 10 * * 4     content_agent.py --site mkd
 0 10 * * *     linkedin_agent.py
 0 19 * * *     emelia_to_crm.py
 0 6 * * 1      weekly_report.py
10 * * * *      tally_to_prm.py
 0 21 * * *     backup.sh
```

---

## Règles dev

- **Toujours** mettre à jour STATE.md en fin de session
- **Toujours** logger les coûts via `cost_tracker.track()`
- **Budget Ahrefs** : gate dans `ahrefs_daily.py` (warn 70%, block 90%, reserve 500u)
- **Warmup sender** obligatoire : config dans `email_senders`, garde-fou dans `push_prospect()`. Plan A par défaut (10→100/30j conservateur)
- **Templates** : éditer via UI `/site/[code]/templates` (lecture seule depuis Emelia côté API)
- **Cooldowns** respectés automatiquement par `pick_for_campaign()`
- **Aucun code SQL direct** dans api.py — passer par les backends (acquisition_backend, contacts_pool_backend, etc.)
- **Tailwind 4** : utiliser les selectors `data-[attribute=value]` (PAS `data-attribute`)

---

## Spécifications (`specs/`)

- `contacts-model.md` — schéma pool mutualisé + règles métier
- `onboarding-checklist.md` — 16 steps détaillés
- `campaigns-spec.md` — wizard 4 steps + algo pioche SQL
- `warmup-plan.md` — Plan A conservateur (10→100) vs Plan B agressif (36→10000)
- `workflow-prospection.md` — pipeline Serper→Mailnjoy→Emelia
- `seo-playbook.md` — Ahrefs tiers + budget gate

---

## Commandes utiles

```bash
# Services PM2
sudo -u autoblog pm2 list
sudo -u autoblog pm2 restart genesis-dashboard genesis-ui

# Backup manuel
sudo -u autoblog bash /home/autoblog/genesis/scripts/backup.sh

# Pool stats live
duckdb data/contacts.duckdb "SELECT primary_source, COUNT(*) FROM contacts GROUP BY 1"

# Logs scrapes
duckdb data/god_mode.duckdb "SELECT created_at, action, resource_id, success FROM god_mode_logs ORDER BY created_at DESC LIMIT 20"

# Master key disaster recovery
scp ~/.ssh/genesis-master-key genesis:/home/autoblog/genesis/data/.master_key
```

---

## Domaines / endpoints

- UI production : https://api.cheffer.email/
- API FastAPI : port 8080 (PM2 `genesis-dashboard`)
- UI Next.js : port 3100 (PM2 `genesis-ui`)
- Webhook Emelia : `https://api.cheffer.email/api/emelia/webhook?token=...`
- SSH : `ssh genesis` (alias dans `~/.ssh/config`)

---

## Budgets opérationnels

- Anthropic (Claude) : ~$10/semaine max
- Ahrefs : 10k unités/mois (audit complet ~700u/site, daily ~100u total)
- Serper : illimité tant que crédits restent (vérif live via UI Scrapper)
- Mailnjoy : 1 crédit/check, à recharger via UI
- DeepSeek : usage rédaction articles + qualifier sectoriel
