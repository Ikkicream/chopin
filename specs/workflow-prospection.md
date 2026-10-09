# Workflow — Prospection locale Serper → Emelia (ex « God Mode »)

> Spec produit + plan d'instrumentation. Validée par Camille le 2026-05-21.
> Source de vérité unique pour le module Workflow des sites **LCR** et **MKD**.

## 1. Cible business

Cible TPE/PME locales avec présence Google Places (= un site web et un email « contact@ »).
6 secteurs couverts, par ordre de priorité d'acquisition :

| Secteur | Emoji | Priorité (bonus score) | Justification |
|---|---|---|---|
| immobilier   | 🏠 | +30 | Volumes campagnes SMS élevés, budget marketing récurrent |
| retail       | 🛍️ | +30 | Boutiques physiques, besoin de fidélisation + promo |
| restaurant   | 🍕 | +25 | Promos / réservations / fidélité — usage RCS-friendly |
| coiffeur     | 💇 | +20 | Rappels RDV, vraie demande, panier moyen faible |
| garagiste    | 🚗 | +20 | Rappels révisions / contrôle technique |
| artisan      | 🔧 | +15 | Plus dur à convertir, mais volumes nationaux |

Codé dans `scripts/god_mode_backend.py:25` (SECTORS_GOD_MODE) et `scripts/god_mode_agents.py:145` (PRIO_SECTORS).

## 2. Logique géographique — Région → Département → Villes

**Règle métier** : on prospecte les villes, **jamais les villages**.
Seuil de filtrage par défaut : commune ≥ **10 000 habitants** (INSEE 2024) → reste ~470 villes éligibles en France métropolitaine.

### Hiérarchie de scraping

```
France
└── 13 régions métropole (+ DOM)
    └── 96 départements
        └── N villes ≥ 10k hab (CP, lat/lon, population)
            └── 6 secteurs (Serper places query par secteur × ville)
```

À chaque scrape, on choisit **une région OU un département OU une ville** comme racine puis on descend.
Stratégie par défaut du cron quotidien : tirer aléatoirement un département pondéré par population, descendre sur ses villes ≥ 10k hab, scraper les 6 secteurs.

### Sources de données utilisées

| Champ | Source | Stockage Genesis |
|---|---|---|
| Code département | INSEE codes officiels | `data/geo/departments.json` |
| Code postal commune | API découpage-administratif (laposte.fr) | `data/geo/cities-fr.json` |
| Population commune | INSEE recensement 2024 | idem |
| Région | INSEE | `data/geo/regions.json` |

Les 3 fichiers sont **statiques** (régénérés ~1×/an). Pas d'appel runtime, pas de coût.

## 3. Pipeline complet (par run)

```
[1] Choix territoire  ──>  [2] Liste villes ≥10k hab  ──>  [3] Serper.dev /places
                                                                  │
                                                                  ▼
[4] Extraction website + phone + place_id  <─────────────  pour chaque secteur × ville
                                                                  │
                                                                  ▼
[5] fetch_email_from_site(website)  ──>  email valide ? ──> non = drop
                                                                  │ oui
                                                                  ▼
[6] score_prospect rule-based (0-100)  +  qualifier DeepSeek (acheteur potentiel ? oui/non + raison)
                                                                  │
                                                                  ▼
[7] Insert table `scrappe` (god_mode.duckdb)  status=validated
                                                                  │
                                                                  ▼
[8] Segmentation Emelia : {site}-{dept_code}-{sector} → segment_id auto-créé/réutilisé
                                                                  │
                                                                  ▼
[9] Push contact dans le segment Emelia + déclenche template cold email validé pour ce secteur
                                                                  │
                                                                  ▼
[10] update scrappe.contacted_at + log_action
```

Code existant pour chaque étape :

- [1]/[2] : à créer (`scripts/workflow_geo.py`)
- [3] : `god_mode_agents.py:51` (serper_places)
- [4] : extracted depuis `places[]` Serper directement
- [5] : `god_mode_agents.py:104` (fetch_email_from_site)
- [6] rule : `god_mode_agents.py:148` (score_prospect)
- [6] DeepSeek qualifier : **à créer** (`workflow_qualifier.py`, voir §5)
- [7] : `god_mode_backend.add_prospect(site, prospect)`
- [8]/[9] : **à créer** (push Emelia segmenté), aujourd'hui le scrape s'arrête à la DB
- [10] : `god_mode_backend.log_action`

## 4. Schéma des données

### Table `scrappe` (existante, `data/god_mode.duckdb`)
```
id, site_code, company_name, contact_name, email, phone, sector,
city, postal_code, website, source, search_query, score, status,
raw_data (JSON), created_at, validated_at, contacted_at, rejection_reason
```
**Champs à ajouter** :
- `region_code` (VARCHAR) — code INSEE région (ex : "11" pour Île-de-France)
- `dept_code` (VARCHAR) — code INSEE département (ex : "75", "13")
- `population` (INTEGER) — population de la commune (pour reporting)
- `qualifier_buyer` (BOOLEAN) — verdict DeepSeek "potentiel acheteur"
- `qualifier_reason` (VARCHAR) — raison courte (ex : "site pro actif, hors franchise grande chaîne")
- `emelia_segment_id` (VARCHAR) — id segment Emelia auquel le contact a été ajouté
- `emelia_contact_id` (VARCHAR) — id contact dans Emelia (pour suivi)

### Nouveau fichier `data/geo/cities-fr.json`
```json
[
  {"insee": "75056", "name": "Paris", "cp": ["75001", ..., "75020"], "dept": "75", "region": "11", "pop": 2102650, "lat": 48.8566, "lng": 2.3522},
  {"insee": "13055", "name": "Marseille", "cp": ["13001", ..., "13016"], "dept": "13", "region": "93", "pop": 871923, "lat": 43.2965, "lng": 5.3698},
  …
]
```

## 5. Agent qualifieur DeepSeek (nouveau)

Fonction `qualify_prospect(prospect: dict) -> dict` dans `scripts/workflow_qualifier.py`.

Prompt :
> Tu reçois un prospect TPE/PME français. Décide s'il est **potentiel acheteur** d'une solution SMS marketing / RCS / location de données B2B.
> Critères positifs : site web actif, présence Google Places, secteur à fort besoin marketing direct, taille TPE/PME indépendante.
> Critères négatifs : franchise nationale (McDo, Carrefour…), administration, site indisponible, secteur sans besoin SMS (notaire, médecin libéral isolé).
> Renvoie JSON `{"buyer": true|false, "reason": "max 100 chars"}`

Routage : `call_llm_json(prompt, model="deepseek-chat", module="workflow", action="qualify", site=site)`.
Coût attendu : ~150 input + 30 output tokens = ~0.00006 € par prospect → 100 prospects/jour = **0.006 €/jour**, négligeable.

## 6. Push Emelia segmenté (nouveau)

### Convention de nommage des segments
`workflow-{site}-{dept}-{sector}`
ex : `workflow-lcr-13-restaurant`, `workflow-mkd-75-immobilier`

### Code à créer : `scripts/workflow_emelia_push.py`
1. `get_or_create_segment(api_key, name)` — GET /api/contacts/lists puis POST si absent
2. `push_contact(api_key, segment_id, email, first_name, last_name, custom_fields)`
3. `assign_campaign(api_key, segment_id, campaign_template_id)` — campagne pré-validée par secteur

API doc Emelia : https://developers.emelia.io/

### Champs personnalisés Emelia poussés
- `{{company_name}}` — pour mention dans l'email
- `{{city}}` — pour localisation
- `{{sector}}` — pour fallback variants
- `{{website}}` — pour referer dans email

### Garde-fous
- Quota global LCR + MKD : **50 contacts/jour max poussés vers Emelia** (règle CLAUDE.md)
- Anti-doublon : check `emelia_contact_id` non null dans `scrappe` avant push
- Anti-spam même domaine : max 1 contact par root domain / 30 jours

## 7. Cron quotidien

```cron
# /var/spool/cron/crontabs/autoblog
30 6 * * 1-5  cd /home/autoblog/genesis && python3 scripts/workflow_runner.py >> /home/autoblog/genesis/logs/workflow.log 2>&1
```

Logique de `workflow_runner.py` :
1. Pour chaque site (lcr, mkd) où `god_mode_state.enabled = TRUE`
2. Lire `daily_quota` (table god_mode_settings, défaut 20 par site)
3. Tirer 1 département pondéré population, sélectionner 3-5 villes ≥ 10k hab
4. Pour chaque secteur priorisé : scraper jusqu'à `daily_quota / 6` prospects
5. Qualifier DeepSeek sur les validés
6. Push Emelia (par dept × secteur) sur les `buyer=true`
7. Telegram récap : "Workflow LCR — 12 prospects ajoutés (13-restaurant: 4, 13-coiffeur: 3, …)"

## 8. UI — Pages à reprendre

Routes UI actuelles sous `/site/[code]/god-mode/` (à renommer en `workflow/`) :

| Page | Statut | Action |
|---|---|---|
| `page.tsx` (overview)        | ✅ existe, fixée aujourd'hui | RAS — affiche crédits Serper + stats + graph |
| `perimetre/page.tsx`         | ✅ existe (quota, provider)  | Ajouter **sélecteur région/département/villes** |
| `prospects/page.tsx`         | ✅ existe                    | Ajouter colonnes : dept, qualifier_buyer, emelia_segment_id |
| `templates/page.tsx`         | ✅ existe                    | RAS — un template DeepSeek par secteur, lockable |
| `campaigns/page.tsx`         | ✅ existe                    | Lier au segment Emelia, statut envoi/réponse |
| `logs/page.tsx`              | ✅ existe                    | Filtrable par action (scrape, qualify, push_emelia) |

**Renommage URL** : `/god-mode/` → `/workflow/` côté Next + redirect 301 + tous les liens sidebar.
Renommage déjà fait dans la sidebar (label "Workflow") mais le **slug d'URL** est resté `god-mode`.

## 9. Récap — Ce qui existe vs ce qui manque

### ✅ Existe (fonctionnel, juste à brancher)
- Auth/permissions superadmin (fix appliqué aujourd'hui — `god_mode_backend.py:65`)
- Endpoints API `/api/god-mode/{site}/*` (20+ routes)
- Connecteur Serper.dev (clé en place, balance 2476 crédits dispo)
- 6 secteurs définis avec scoring rule-based
- Templates DeepSeek par secteur (génération + lock)
- Table `scrappe` + logs + state + settings
- Pages UI overview/perimetre/prospects/templates/campaigns/logs

### ❌ À créer
1. **`data/geo/`** : `regions.json`, `departments.json`, `cities-fr.json` (~470 villes ≥ 10k hab)
2. **`scripts/workflow_geo.py`** : sélection territoire pondérée + résolution région→dept→villes
3. **`scripts/workflow_qualifier.py`** : agent DeepSeek "potentiel acheteur ? oui/non"
4. **`scripts/workflow_emelia_push.py`** : segmentation auto `{site}-{dept}-{sector}` + push
5. **`scripts/workflow_runner.py`** : runner quotidien orchestrant le pipeline
6. **Migration DB** : ajout colonnes `region_code`, `dept_code`, `population`, `qualifier_*`, `emelia_*` à `scrappe`
7. **UI `perimetre`** : sélecteur région→dept→villes avec preview du compte de villes éligibles
8. **Renommage URL** `/god-mode/` → `/workflow/` + redirect
9. **Cron** : ligne ajoutée au crontab autoblog

### ✅ Décisions validées par Camille (2026-05-21)
- **Quota Emelia** : 50/site/jour = 100/jour total (LCR+MKD). Le vrai plafond est la deliverability IP : **1 000 messages/jour max après warmup** — on reste 10× en dessous, sécurité garantie.
- **Templates** : 1 template Emelia **par secteur** = 6 templates pré-validés. Le workflow déclenche le bon selon le segment.
- **Crédits Serper** : 50 000/mois = ~1 666/jour, ce n'est pas la contrainte limitante. Pas de quota Serper strict, on calibre par le quota Emelia en aval.
- **URL** : renommage `/god-mode/` → `/workflow/` + redirect 301.
- **Pop min ville** : 10 000 hab par défaut (~470 villes). Calibrable par la suite via UI perimetre.
- **Clés Emelia** : par site (`EMELIA_API_KEY_LCR` / `EMELIA_API_KEY_MKD`), fallback `EMELIA_API_KEY` global si manquante.

## 10. Coûts estimés

- **Serper.dev** : 1 crédit par requête /places, ~3 requêtes par ville × 6 secteurs = 18 crédits/ville. Si 5 villes/jour = 90 crédits/jour, soit ~2 700/mois → **bien sous les 2 500 actuels mensuels** (à recharger si on push fort).
- **DeepSeek qualifier** : ~0.006 €/jour par site = 0.40 €/mois total. Négligeable.
- **Emelia** : forfait existant, pas de coût marginal API.
- **Total estimé module Workflow** : <**1 €/mois** hors abonnement Emelia.

## 11. Validation

Si tu valides cette spec, je commence dans cet ordre :
1. Migration DB (5 min)
2. `data/geo/*.json` (15 min — génération via API INSEE/laposte ou fichier figé)
3. `workflow_geo.py` + `workflow_qualifier.py` (1 h)
4. `workflow_emelia_push.py` (1 h, avec doublon-protection)
5. `workflow_runner.py` + cron (30 min)
6. Renommage URL `/god-mode/` → `/workflow/` (15 min)
7. UI sélecteur perimetre (1 h)

**Total** : ~4 h de codage si pas d'imprévu, livré avec un dry-run d'1 département test (ex : 75 Paris) avant d'activer le cron.


---

## 12. Email Validator + Mailnjoy (ajouté 2026-05-22)

### Pipeline complet actualisé

```
Serper /places
    ↓ scrape (extract email + phone + website)
[email_validator.validate_and_score()]         ← scripts/email_validator.py
    ↓ 6 étages (normalisation, regex, hard rejects honeypot/forbidden_tld/role/disposable,
                 MX check, RGPD, scoring 0-100)
    ↓ decision == drop  → NEVER inserted in DB
    ↓ decision == queue → INSERT scrappe_pending (passera quand même par Mailnjoy)
    ↓ decision == push  → INSERT scrappe_pending

[Idempotence guard]                            ← god_mode_backend.email_recently_validated()
    ↓ skip si email validé Mailnjoy < 30j
    ↓ skip si email déjà dans scrappe_pending

[scrappe_pending] (table temporaire)           ← status = "mailnjoy_pending"

[mailnjoy_check.check_pending_queue()]         ← scripts/mailnjoy_check.py
    ↓ POST /v2/unitary?type=simple (séquentiel, 200ms entre 2 appels)
    ↓ classify_response() → valid | risky | invalid | error
    ├─ valid   → move_pending_to_scrappe()  → scrappe (status="mailnjoy_valid")
    ├─ risky   → delete_pending()           → log + KILL
    ├─ invalid → delete_pending()           → log + KILL
    └─ error   → bump_pending_error()       → retry max 5x

[workflow_qualifier.qualify_prospect()]        ← DeepSeek (sur scrappe.mailnjoy_valid)
    ↓ qualifier_buyer = True/False
    ↓ True → push Emelia, False → reste en scrappe (qualifier_reason loggé)

[workflow_emelia_push.push_prospect()]
    ↓ status = "pushed_emelia", emelia_contact_id rempli
```

### États du champ `status` (state machine v2)

| Status | Table | Quand |
|---|---|---|
| `mailnjoy_pending` | scrappe_pending | Inséré par scrape_sector après passage validator |
| `manual_review` | scrappe | Decision validator = queue (score 40-59), inséré directement pour review humaine |
| `rejected` | scrappe | Decision validator = drop (légacy entries pré-Mailnjoy) |
| `scored` | scrappe | LEGACY — entries pré-Mailnjoy déjà validées par syntaxe (avant 2026-05-22) |
| `mailnjoy_valid` | scrappe | Mailnjoy a confirmé délivrabilité — prêt pour DeepSeek qualifier + Emelia |
| `pushed_emelia` | scrappe | Effectivement poussé dans une campagne Emelia |

États transitoires (jamais persistés) :
- `mailnjoy_risky` / `mailnjoy_invalid` : ligne supprimée de pending, jamais dans scrappe (décision user 2026-05-22 : risky = kill au même titre qu'invalid)
- `mailnjoy_error` : conservé en pending avec `mailnjoy_attempts > 0`, retry au prochain drain (max 5)

### Modules livrés (2026-05-22)

| Fichier | Rôle |
|---|---|
| `scripts/email_validator.py` | 6 étages de validation + scoring 0-100 |
| `data/email_jetable.csv` | 304 domaines disposable (extensible) |
| `scripts/mailnjoy_check.py` | Appel Mailnjoy, classification, drain queue, retry exp backoff |
| `scripts/god_mode_backend.py` | Helpers `add_prospect_pending()`, `list_pending()`, `move_pending_to_scrappe()`, `delete_pending()`, `bump_pending_error()`, `email_recently_validated()`, `email_in_pending()` |
| `data/god_mode.duckdb` | Table `scrappe_pending` créée, colonne `scrappe.mailnjoy_check` ajoutée, colonnes `scrappe.email_score` + `email_validation_reasons` ajoutées |
| `logs/mailnjoy_deletions.log` | Audit des suppressions Mailnjoy (risky/invalid) |

### Idempotence

- **Au scrape** : `email_recently_validated(email, days=30)` empêche de re-scraper un email déjà confirmé Mailnjoy il y a moins de 30 jours
- **Au scrape** : `email_in_pending(email)` empêche le doublon dans la queue
- **Au drain** : `mailnjoy_attempts < 5` empêche le retry infini sur les erreurs réseau

### Budget Mailnjoy

- Forfait dispo : 1 199 105 unités (état 2026-05-22)
- Coût : ~1 crédit par check email (`/v2/unitary?type=simple`)
- Endpoint crédit `/v1/credit` est gratuit (utilisé pour le monitoring)
- Garde-fou : drain s'arrête si crédit < 100u

### Credentials

Fichier `.env` :
```
MAILNJOY_ID=...
MAILNJOY_SECRET=...
```

⚠️ La clé doit avoir **"lecture seule = non"** ET **"autorisation d'achat = oui"** (option dans le panel https://developer.mailnjoy.com). Sinon → `401 Read only API user cannot perform this action`.

### Réponse Mailnjoy v2 — particularité

La réponse `/v2/unitary` est wrappée :
```json
{
  "unitaryCheck": {
    "email": "...",
    "status": "VALID",
    "category": "SAFE",
    "attributs": {...}
  }
}
```

Toujours unwrap via `raw.get("unitaryCheck", raw)` avant lecture de `status` / `category` / `attributs`.
