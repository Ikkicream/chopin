# Acquisition de contacts — 2 outils, 1 pool (Serper + Basile)

> Vue d'ensemble du système d'acquisition de Genesis : comment **Serper** (existant) et
> **Basile** (nouveau, `scripts/basile_backend.py`) collectent des contacts vers le **même pool**,
> quand utiliser quoi, l'UX proposée, et le mode opératoire pour le mettre en service.
> Détails API Basile : `docs/basile-api.md`. Ciblage par site : `context/<site>/acquisition-context.md`.

## 1. Pourquoi 2 outils

| | **Serper** (`god_mode_agents.serper_places`) | **Basile** (`basile_backend.run_segment`) |
|---|---|---|
| Source | Google Places (commerces avec site web) | Registre légal INSEE + LinkedIn + GMB |
| Maille | secteur × **ville** (lent, fin) | NAF/activity × **département** (rapide, volume) |
| Contact | email générique scrapé du site | société + **dirigeant nommé** (prénom/nom/role) + email générique |
| Enrichissement | non | **Emelia** → email nominatif + portable (opt-in) |
| Coût | crédits Serper | quota export Basile (20 000/export, 250 000/mois sur plan API) |
| Quand | couverture commerce-local quand le NAF est trop large/absent | cold-email personnalisé, volume par secteur, décideur identifié |

Les deux sont **complémentaires**, pas redondants : Basile apporte le **nom du décideur** et le
volume ; Serper la **finesse commerce-local** ville par ville. La dédup par email les fusionne.

## 2. Architecture de fusion (le point clé)

Les deux écrivent dans **les mêmes 2 destinations**, avec un `source`/`primary_source` distinct :

```
 Serper  ─┐                                        ┌─ scrappe_pending (god_mode.duckdb)
          ├─►  prospect normalisé  ─► validate_and_score ─┤      │  (file → Mailnjoy drain)
 Basile  ─┘   (schéma identique)                    └─ contacts (contacts.duckdb, pool mutualisé)
                                                              dédup par EMAIL (clé)
```

- **Schéma `prospect` identique** : `company_name, contact_name, email, phone, sector, city,
  postal_code, website, source, search_query, raw_data, email_score, email_validation_reasons,
  region_code, dept_code, status`. Basile remplit en plus `prenom/nom/job_title` côté pool.
- **Même validateur** : `email_validator.validate_and_score()` (6 étages) → `scrappe_pending`
  → drain Mailnjoy (`genesis-mailnjoy-drain`) → `scrappe` + pool.
- **Dédup par email** dans `contacts_pool_backend.create_in_pool()` : enrichit les champs NULL
  seulement, n'écrase jamais. Donc un contact vu par Serper PUIS par Basile fusionne — Basile
  ajoute le prénom/nom du gérant sans casser la donnée Serper.
- **`primary_source`** : `"serper"` ou `"basile"` → traçabilité du canal d'acquisition.
- **RGPD** : `global_blacklisted` reste terminal et inter-sites, quel que soit le canal.

## 3. Règles de volume (dures, demande user)

- **Compter avant d'extraire** (gratuit) — toujours.
- **Jamais > 20 000** sur un segment → sinon **segmenter** (le connecteur renvoie `action:"segment"`).
- **Passes de 1 000** contacts, throttle 1,5 s, reprise auto 429.
- **1 segment = 1 secteur × 1 département** par défaut → lots petits, propres, sans doublon.

## 3bis. Stratégie retenue (LCR, décidée 2026-06-17)

Tests live : sociétés Basile ~15 % avec email générique (~2 % net), **dirigeants = 0 email**. Donc
le canal « emails génériques Basile » ferait surtout doublon avec Serper. **Choix : flux DIRIGEANTS
+ Emelia.**

```
companies/find (NAF/activity + géo)  →  people/find par SIREN (nom du dirigeant)  →
Emelia find-email (prenom.nom@société)  →  validate_and_score  →  scrappe_pending + pool (source=basile)
```
- **Free** (Basile) : société + **dirigeant nommé** + SIREN. ~58 % des sociétés ont ≥1 dirigeant.
- **Payant** (Emelia) : 1 crédit / dirigeant pour l'email nominatif → cold-email « Bonjour Marie ».
  Le `website` (souvent dans `x_gmb`) améliore le taux Emelia.
- **Garde-fou coût** : dry-run estime le nb d'appels Emelia AVANT de dépenser ; `--emelia --live`
  requis pour réellement appeler. Annoncer le coût + valider chaque lot (sauf opt-out).
- Fonction : `run_dirigeant_segment()` ; CLI `dirigeants`.

## 4. Comment utiliser le connecteur Basile (CLI)

```bash
# FLUX RETENU — dirigeants nommés → Emelia. D'abord DRY-RUN (gratuit, estime le coût Emelia) :
python3 scripts/basile_backend.py dirigeants \
  '{"naf_code":{"include":["56.10A"]},"company_ceased":false,"headquarters_postal_code":{"include":["69001","69002"]}}' \
  --site lcr --sector restaurant --dept 69 --max 1000
#   → companies_scanned / dirigeants_found / emelia_needed (= crédits) / samples

# LIVE avec Emelia (PAYANT, 1 crédit/dirigeant) — écrit dans scrappe_pending + pool :
python3 scripts/basile_backend.py dirigeants '<filters companies>' \
  --site lcr --sector restaurant --dept 69 --emelia --live
```


```bash
# 1) Compter (gratuit) — toujours en premier
python3 scripts/basile_backend.py count companies \
  '{"naf_code":{"include":["56.10A","56.10C"]},"company_ceased":false,"headquarters_department_code":{"include":["69"]}}'

# 2) Dry-run d'un segment (compte + normalise 3 échantillons, AUCUNE écriture DB)
python3 scripts/basile_backend.py segment people \
  '{"siren":{"include":["552100554","..."]},"result_is_current":true,"hide_legal_entities":true}' \
  --site lcr --sector restaurant --dept 69

# 3) Live — écrit 1 passe de 1 000 dans scrappe_pending + pool contacts
python3 scripts/basile_backend.py segment people '<filters>' \
  --site lcr --sector restaurant --dept 69 --live
```

Fonctions Python réutilisables : `count()`, `find()`, `lead_to_prospect()`,
`enforce_volume_rules()`, `run_segment()`. Les 2 premières fonctions pures sont testables sans clé.

## 5. UX proposée (dashboard)

Aujourd'hui le scrapper Serper a une page « secteur + région → autoscrape continu ». Proposition
pour intégrer Basile **sans casser** l'existant :

### Option retenue : un onglet « Source » dans le même écran de scrape
```
┌─ Scrapper ────────────────────────────────────────────────┐
│  Source : ( ● Serper )  ( ○ Basile )  ( ○ Les deux )       │
│                                                            │
│  Secteur :  [ Restaurants ▼ ]   Région : [ Île-de-France ▼ ]│
│  (Basile) Cible : ( ● Dirigeants nommés ) ( ○ Sociétés )   │
│                                                            │
│  [ Compter ]  → « 14 230 résultats — 15 passes de 1 000 »  │
│  [ Lancer la collecte ]   (désactivé tant que pas compté)  │
│                                                            │
│  ── Activité ───────────────────────────────────────────  │
│  Basile · restaurant · 69 · passe 3/15 · 1 000 collectés   │
└────────────────────────────────────────────────────────────┘
```
Principes UX :
- **Compter d'abord, toujours** : le bouton « Lancer » reste grisé tant que le total n'est pas
  affiché. On montre le nombre de passes (factuel, jamais alarmiste).
- **> 20 000 → message clair** : « Ça dépasse une passe d'export. On segmente par département ? »
  + bouton qui éclate automatiquement le segment par dept.
- **Cible Basile** (dirigeants nommés vs sociétés) = un toggle, traduit en workflow 1 ou 2 étapes.
- **Activité unifiée** : la table d'activité existante affiche aussi les passes Basile (réutilise
  le `scope`/`message` déjà en place pour Serper).
- **Enrichissement Emelia** : bouton « Enrichir (emails nominatifs / portables) » sur une sélection,
  avec **coût annoncé + confirmation** avant chaque lot.

### Endpoint backend à ajouter (miroir de l'autoscrape Serper)
- `POST /api/sites/{site}/basile/count` → `{ total, rule }`
- `POST /api/sites/{site}/basile/segment` → lance `run_segment` (détaché, comme l'autoscrape)
- `GET  /api/sites/{site}/basile/status` → progress (réutilise le pattern `*-region-progress.json`)

## 6. Mode opératoire — jour du retour de Basile (app.basile.cc)

> app.basile.cc et l'API étaient DOWN à la rédaction. À faire dès que c'est rétabli, dans l'ordre :

1. **Récupérer la clé API** sur https://app.basile.cc/ (plan API requis) →
   `echo "BASILE_KEY=sk_live_xxx" >> /home/autoblog/genesis/.env`
2. **Smoke test `count`** (gratuit) sur un petit segment LCR (cf. `docs/basile-api.md §13`).
3. **Confirmer le FIELD MAP** : `find` brut → inspecter `leads[0].data` → ajuster
   `lead_to_prospect()` (noms réels des champs email/prenom/nom/role/siren).
4. **Dry-run d'un segment** (samples + rule) → puis **live d'une passe de 1 000**.
5. **Vérifier la double écriture** : `scrappe_pending` (god_mode.duckdb) ET `contacts`
   (contacts.duckdb, `primary_source='basile'`), puis le drain Mailnjoy.
6. **Valider `activity`** : pour chaque secteur LCR, `GET /companies/activity-suggest?q=…` →
   compléter la colonne `activity` de `context/lcr/acquisition-context.md`.
7. **Crosscheck** `docs/basile-api.md` contre docs.basile.cc (limites/filtres à jour).
8. **Brancher l'UX** (§5) + endpoints, puis éventuellement un cron de segments (1 secteur×dept/jour).
9. **Contextes des autres sites** : dupliquer `acquisition-context.md` pour MKD puis les suivants.

## 7. Fichiers livrés (cette session)

| Fichier | Rôle | Statut |
|---|---|---|
| `skills/basile-b2b-search/` | skill Basile (SKILL.md + refs + scripts) | installé |
| `scripts/basile_backend.py` | connecteur (count/find/normalise/segment + garde-fous) | écrit, **non testé live** |
| `docs/basile-api.md` | doc API complète + go-live | écrit |
| `docs/contact-acquisition.md` | ce fichier (fusion + UX + opératoire) | écrit |
| `context/lcr/acquisition-context.md` | ciblage LCR → filtres Serper/Basile | écrit |

**Reste (bloqué sur le retour de Basile)** : clé `.env`, validation FIELD MAP, tests live, endpoints
+ UX, contextes MKD/autres sites.
