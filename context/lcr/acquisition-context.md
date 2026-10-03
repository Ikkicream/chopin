# LCR — Contexte d'acquisition de contacts (Serper + Basile)

> Fichier de **ciblage** : qui on collecte pour LeClientROI, et comment le traduire en
> filtres concrets pour les 2 outils. Complète `context/lcr/goals.md` (goal #6 Cold Email PME)
> et `context/lcr/sector-angles.md`. Source de vérité du *qui*, pas du *comment technique*
> (ça, c'est `docs/contact-acquisition.md`).

## ICP LeClientROI

LCR vend du **SMS marketing local / drive-to-store** à des **PME et commerces de proximité**
qui ont une clientèle locale récurrente à fidéliser/relancer par SMS.

- **Cible** : commerçants, artisans, restaurateurs, agences immobilières, coiffeurs, garagistes,
  salles de sport, boulangers — TPE/PME françaises avec une boutique/établissement physique.
- **Décideur** : le **gérant / dirigeant** (souvent gérant unique en TPE). C'est lui qui décide
  d'envoyer des SMS à ses clients.
- **Géo** : France métropolitaine (Corse + DOM-TOM exclus, cf. `workflow_geo`).
- **Signaux de qualité** : établissement actif, présence en ligne (site/GMB), avis Google
  (preuve d'activité B2C locale).

## Répartition des 2 outils pour LCR

| Outil | Rôle pour LCR | Type de contact ramené |
|---|---|---|
| **Serper** (existant) | commerces locaux avec site web, ville par ville | email générique scrapé du site |
| **Basile** (nouveau) | volume registre + **dirigeant nommé**, par département/NAF | société + gérant (prénom/nom) + email générique, **enrichissable** (Emelia → email nominatif / portable) |

→ Basile est le meilleur canal pour le **cold-email personnalisé** (« Bonjour Marie, … »), Serper
pour la **couverture commerce-local fine** quand le NAF est trop large.

## Mapping secteurs LCR → filtres Basile

Codes NAF FR (registre, fiables) + concept `activity` (à confirmer via
`GET /companies/activity-suggest?q=…` au retour du site). Toujours `company_ceased: false`.

> ✅ **Formats CONFIRMÉS en live (2026-06-17)** :
> - `naf_code` : format **exact avec point + lettre** (`"56.10A"`). **Pas de wildcard `.x`**
>   (`"56.1"` → 0). Pour couvrir une classe, lister tous les codes.
> - `activity` : **préfixe `concept:` OBLIGATOIRE** (`concept:restaurant_table`). Trouver l'ID via
>   `GET /companies/activity-suggest?q=…` (renvoie `value:"concept:xxx"`).
> - **Géo entreprises** : PAS de champ département/région qui marche (`headquarters_department_code`
>   et `headquarters_region_code` → 0). Utiliser **`headquarters_postal_code`** (exact 5 chiffres,
>   pas de préfixe) ou **`headquarters_city`** (⚠️ **MAJUSCULES** : `"LYON"`, via `city-suggest`).
>   → Pour un département entier : lister ses codes postaux / villes (helper `workflow_geo`).

| Secteur LCR | `naf_code` (exact, lister tous les codes) | `activity` (concept confirmé) |
|---|---|---|
| Restaurants | `56.10A` (traditionnel), `56.10C` (rapide), `56.30Z` (débits boissons) | `concept:restaurant_table`, `concept:restauration_rapide` |
| Boulangerie / pâtisserie | `10.71C`, `47.24Z` | (suggest `boulang`) |
| Coiffure / beauté | `96.02A`, `96.02B` | (suggest `coiff`) |
| Garages / réparation auto | `45.20A`, `45.20B` | (suggest `garage`) |
| Agences immobilières | `68.31Z` | (suggest `immobil`) |
| Artisans bâtiment | `41.20A`, `43.x…` (lister) | (suggest `batiment`) |
| Commerce de détail | `47.xx` (lister) | (suggest `commerce`) |
| Salles de sport | `93.13Z` | (suggest `sport`) |

> ⚠️ `naf_code` est **fiable** (registre). `activity` (concept) est plus large. Ne pas utiliser
> `industry_main`/`company_type` (LinkedIn, lacunaires).
>
> 🔑 **Rendement email CONFIRMÉ faible** : ~15 % des sociétés Basile ont un email générique, ~2 %
> net après validation (le reste = pas d'email ou no_mx). Les **dirigeants (people via SIREN) n'ont
> AUCUN email/téléphone** chez Basile. → Basile n'est PAS une source d'emails directe : sa valeur =
> **liste structurée sociétés + nom du dirigeant + SIREN**, contactabilité via **Emelia** (email
> nominatif/portable). Voir la décision d'usage dans `docs/contact-acquisition.md §Stratégie`.

## Workflow recommandé pour LCR (dirigeant nommé)

Pour du cold-email personnalisé, **workflow 2 étapes** (obligatoire pour cibler des personnes
par secteur — pas de filtre secteur fiable côté personnes) :

1. **Entreprises** `POST /companies/find` :
   ```json
   { "filters": {
       "naf_code": { "include": ["56.10A","56.10C"] },
       "company_ceased": false,
       "headquarters_department_code": { "include": ["69"] }
   } }
   ```
   → compter d'abord (`limit:1`). Récupérer `siren` + `legal_name` de chaque société.
2. **Dirigeants** `POST /people/find` en réinjectant les SIREN :
   ```json
   { "filters": {
       "siren": { "include": ["552100554","443061841", "..."] },
       "result_is_current": true,
       "hide_legal_entities": true
   } }
   ```
   → ne ramène que les dirigeants actifs du registre (gérants/présidents). Exact, sans faux positif.

Alternative « emails génériques société » (plus proche de Serper, sans nom de décideur) :
`companies/find` direct + export — utile quand on veut juste du volume contact@.

## Règles de collecte (dures)

- **Compter avant d'extraire** (gratuit). Annoncer le `total` factuellement.
- **Jamais > 20 000** sur un segment → si dépassé, **segmenter par département** (puis par NAF si
  un seul dept dépasse encore). Le connecteur refuse et renvoie `action: "segment"`.
- **Passes de 1 000** contacts, throttle 1,5 s entre appels, reprise auto sur 429.
- **Segmentation LCR par défaut** : 1 segment = (1 secteur × 1 département). ~96 depts × 8 secteurs
  = lots petits et propres, jamais de gros export.
- **Enrichissement Emelia** (email nominatif / portable) : **opt-in, coût annoncé avant chaque lot**
  (clé `EMELIA_API_KEY` déjà en place). À réserver aux dirigeants nommés à fort potentiel.

## Garde-fous RGPD / qualité (réutilise l'existant Genesis)

- Tout email passe par `email_validator.validate_and_score` puis Mailnjoy (drain).
- Dédup par le pool `contacts.duckdb` (clé email) → un contact Serper et un contact Basile sur
  le même email fusionnent (Basile enrichit prénom/nom/job_title sans écraser).
- `global_blacklisted` (désabo RGPD) reste terminal et inter-sites.

## Priorité de déploiement LCR (quand Basile sera up)

1. Restaurants + coiffeurs + garages (fort usage SMS de rappel/relance) → départements densément
   peuplés d'abord (75, 69, 13, 33, 59, 31, 44, 06).
2. Puis immobilier + artisans + commerces.
3. Mesurer le taux de validation Mailnjoy par secteur → réallouer.
