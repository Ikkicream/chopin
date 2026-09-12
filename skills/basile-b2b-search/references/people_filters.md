# Filtres `POST /people/find`

Body : `{ "filters": { ... }, "limit": 100, "paginationToken": "..." }`

Chaque filtre texte = `{ "include": [...], "exclude": [...] }`.
Chaque filtre numérique = `{ ">=": n, "<=": n }` (opérateurs `>`, `>=`, `<`, `<=`).
Plusieurs filtres différents = **ET**. `include` = OR ; `exclude` = NOT.

Deux sources : **Legal** (registre, dirigeants) et **LKI** (LinkedIn). Certains
filtres restreignent à une source (colonne "Source").

## ⛔ IMPORTANT — Pas de filtre "secteur / type d'entreprise" côté personnes

Il **n'existe PAS** de filtre fiable « secteur d'activité », « industrie » ou
« type d'entreprise » dans la recherche de personnes. Les données LinkedIn
d'industrie/type côté contacts sont **lacunaires et peu fiables** → ne te base
JAMAIS dessus, et **ne demande pas** « dans quel secteur ? / quel type
d'entreprise ? » comme si c'était un filtre direct de personnes.

👉 **Pour cibler des personnes par secteur / activité / catégorie d'entreprise, il
faut OBLIGATOIREMENT un workflow en 2 étapes** (voir section dédiée plus bas) :
chercher d'abord les **entreprises** (filtres `activity`/`naf_code`, fiables car
issus du registre), puis réinjecter ces sociétés dans la recherche de personnes.

Les seuls critères « métier » fiables directement sur une personne sont son **rôle/
intitulé de poste** (`result_role`) et sa **séniorité/fonction LinkedIn**
(`current_seniority`, `current_job_functions`) — PAS le secteur de sa boîte.

## Filtres communs (cherchent dans les 2 sources)

| Filtre | Ce que ça fait | Matching | Source |
|---|---|---|---|
| `keyword` | Recherche large (nom + rôle + ville + description…) | full-text + contains | les 2 |
| `result_full_name` | Nom complet de la personne | nom (chaque mot doit matcher) | les 2 |
| `result_last_name` | Nom de famille | contains | les 2 |
| `result_first_name` | Prénom | contains | les 2 |
| `result_role` | **Intitulé de poste** (CEO, Directeur…). Texte → mettre toutes les variantes (voir job_titles_synonyms.json) | contains (Legal) / multi-champs (LKI) | les 2 |
| `result_city` | Ville de la personne | contains | les 2 |
| `result_country` | Pays (libellé) | exact | les 2 |
| `result_country_code` | Code pays (ex. `FR`) | exact | les 2 |
| `employer` | Entreprise/employeur actuel | contains | les 2 |

## Filtres Legal uniquement (activer = exclut LinkedIn)

| Filtre | Ce que ça fait | Matching |
|---|---|---|
| `mandate_role` | Rôle légal normalisé. Valeurs : `gerant`, `president`, `dg`, `dgd`, `administrateur`, `commissaire_comptes`, `associe`, `directeur_non_dg`, `autre` | codes |
| `result_used_first_name` | Prénom usuel | contains |
| `result_postal_code` | Code postal de la personne | exact |
| `siren` | SIREN de la société liée | exact |
| `legal_name` | Raison sociale de la société liée | contains |
| `legal_form` | Forme juridique | exact |
| `nationality` | Nationalité (libellé) | exact |
| `nationality_code` | Code nationalité | exact |
| `result_is_legal_entity` | `true`/`false` : la "personne" est une personne morale | booléen |
| `result_is_current` | `true` : mandat actuel seulement | booléen |
| `result_age` | Âge (range) ex. `{ ">=":40, "<=":55 }` | range |
| `result_total_companies_count` | Nb de sociétés dirigées (range) | range |

## Filtres LinkedIn uniquement (activer = exclut Legal)

| Filtre | Ce que ça fait | Matching |
|---|---|---|
| `current_seniority` | Séniorité LinkedIn. Valeurs courantes : `C-Level`, `Director`, `VP`, `Head`, `Manager`, `Senior`, `Partner`, `Owner`, `Founder`, `Entry`, `Training`, `Unpaid` | exact |
| `current_job_functions` | Fonction (ex. `Sales`, `Marketing`, `Engineering`) | contains |
| `skills` | Compétences (ex. `Sales` ramène "B2B Sales"…) | contains |
| `languages` | Langues parlées | contains |
| `education` | École OU diplôme | contains |
| `past_title` | Intitulé d'un poste PASSÉ | contains |
| `past_employer` | Employeur PASSÉ (alumni) | contains |
| `tenure_bucket` | Ancienneté dans le poste actuel (buckets) | range dates |
| `past_tenure_bucket` | Durée d'un poste passé (buckets) | range |
| `connection_count` | Nb de connexions LinkedIn (range) | range |

## Filtres de pilotage de source

| Filtre | Valeur | Effet |
|---|---|---|
| `source` | `"Legal"` ou `"LKI"` | force une seule source |
| `with_legal_data` | `true` | registre seulement |
| `with_linkedin_profile` | `true` | LinkedIn seulement |
| `hide_legal_entities` | `true` (recommandé) | masque les personnes morales (sociétés listées comme contacts), sans exclure LinkedIn. **À activer par défaut** pour ne lister que de vraies personnes |

## 🔁 Workflow OBLIGATOIRE : personnes par secteur/type d'entreprise (2 étapes)

Quand l'utilisateur veut des personnes **dans un secteur / une activité / un type
d'entreprise précis** (ex. « des dirigeants dans le BTP », « des DAF dans
l'agroalimentaire », « des commerciaux dans des restaurants ») :

**Étape 1 — chercher les ENTREPRISES** (réf. `companies_filters.md`), avec les
filtres FIABLES : `activity` (concept) ou `naf_code`, + géo/taille/`company_ceased:false`.
Récupérer dans les résultats le **`siren`** et le **nom** de chaque société.

**Étape 2 — chercher les PERSONNES** en réinjectant ces sociétés. Deux méthodes :

- **Par SIREN (précis, recommandé pour les DIRIGEANTS)** : passer les SIREN des
  entreprises dans `siren.include`. Exact match, fiable. ⚠️ Legal-only → ne ramène
  que les dirigeants du registre (pas les profils LinkedIn salariés).
  ```json
  { "filters": { "siren": { "include": ["552100554","443061841", "..."] },
                 "result_is_current": true } }
  ```
- **Par nom d'employeur (pour les SALARIÉS / profils LinkedIn)** : passer les noms
  des sociétés dans `employer.include` (matche legal_name ET le nom/URL LinkedIn de
  l'employeur, les 2 sources, en "contains").
  ```json
  { "filters": { "employer": { "include": ["ACME","Restaurant Le Gourmet"] },
                 "result_role": { "include": ["Directeur","Gérant"] } } }
  ```

Conseils pratiques :
- **Compter d'abord** les entreprises (étape 1, `limit:1` → `total`). Si trop
  nombreuses (> quelques centaines), affiner avant de réinjecter.
- On peut passer beaucoup de SIREN d'un coup (le body accepte jusqu'à ~1 Mo).
  Préférer le SIREN au nom quand on vise les dirigeants : c'est exact et sans
  faux positifs.
- Pour les profils LinkedIn d'une entreprise précise, le nom (`employer`) est la
  seule voie (les profils LKI n'ont pas de SIREN).

## Bonnes pratiques

- **Secteur / type d'entreprise → JAMAIS un filtre de personne** : passer par le
  workflow 2 étapes ci-dessus (entreprises d'abord).
- **Pour cibler un rôle (CEO, DAF…)** : utiliser `result_role.include` avec TOUTES
  les variantes du groupe dans `job_titles_synonyms.json` (la recherche est en
  texte). Optionnellement croiser avec `current_seniority` (C-Level/Director) pour
  affiner côté LinkedIn.
- **Pour ne lister que des humains** : ajouter `"hide_legal_entities": true`.
- **France seulement** : `result_country_code: { "include": ["FR"] }`.
- **Dirigeants actifs uniquement** (Legal) : `result_is_current: true`.

## Routes de suggestion (autocomplete) — GET

- `/people/cities/suggest?q=`
- `/people/companies/suggest?q=` (employeurs)
- `/people/roles/suggest?q=`
- `/people/skills/suggest?q=`
- `/people/languages/suggest?q=`
- `/people/education/suggest?q=`
- `/people/names/suggest?q=`
- `/people/nationalities/suggest?q=`
- `/people/age/bounds`, `/people/mandate-count/bounds`
- `/people/seniorities`, `/people/tenure-buckets`

## Fiche complète d'une personne

`GET /people/:id/full` → toutes les colonnes enrichies (identité + société
LinkedIn + légal + GMB + contacts) — même schéma que l'export CSV.
