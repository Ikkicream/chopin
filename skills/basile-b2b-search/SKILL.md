---
name: basile-b2b-search
description: >
  Recherche et extraction de contacts et d'entreprises B2B françaises via l'API
  Basile (api.basile.cc), PLUS enrichissement des coordonnées (emails nominatifs
  et téléphones portables) via l'API Emelia. Utilise cette skill dès que
  l'utilisateur veut trouver, compter, filtrer, exporter ou enrichir des
  prospects/sociétés : dirigeants, CEO/CFO/DAF, artisans, commerces, par métier
  (NAF/activité), par localisation (ville, département, région), par taille, par
  techno, avec email ou téléphone, etc. Déclencheurs : "trouve des", "cherche des
  entreprises", "liste de prospects", "des CEO dans", "des artisans à", "exporte",
  "combien de sociétés", "base B2B", "Basile", "trouve l'email de", "le numéro de",
  "enrichis ces contacts", "leurs coordonnées". Couvre la recherche PERSONNES, la
  recherche ENTREPRISES, le comptage avant extraction (pour ne pas gaspiller les
  crédits), l'export CSV, et l'enrichissement email/téléphone via Emelia.
---

# Basile — Recherche B2B (API)

Basile est une base de données B2B française : ~26 M sociétés (registre légal +
LinkedIn + Google My Business) et ~4,4 M contacts (dirigeants légaux + profils
LinkedIn). Cette skill permet de chercher, compter et exporter comme on le ferait
dans la plateforme, mais via l'API.

## Règle d'or : compter avant d'extraire (sans dramatiser)

**TOUJOURS compter avant d'exporter** — mais le but est que l'utilisateur extraie
sa data. Ne jamais dire « c'est énorme », « attention ça va cramer », etc. Un gros
volume est une **bonne** nouvelle : on l'extrait, simplement.

1. Construire la recherche (filtres).
2. Appeler `/find` avec `limit: 1` → lire `total`.
3. Annoncer le nombre **factuellement** et proposer l'extraction :
   - **`total` ≤ 20 000** (limite d'un export, plan API) : « Ça fait X résultats,
     c'est dans ta limite d'export. Je lance l'extraction ? » → un export suffit.
   - **`total` > 20 000** : « Ça fait X résultats. L'export se fait par tranches de
     20 000, donc il faudra N extractions — soit on les enchaîne, soit tu affines
     un critère. Je commence ? » → présenté comme une simple logistique, jamais
     comme un blocage.
4. Lancer `/export` après ce OK (léger). La vraie limite par export du user est
   renvoyée dans le header `X-Export-Max-Rows` ; `X-Export-Capped: true` indique
   qu'il reste des résultats au-delà.

> Limites par plan : **API = 20 000/export**, 250 000/mois. (D'autres plans
> peuvent différer ; fie-toi au header `X-Export-Max-Rows` pour la valeur réelle.)

### ⚙️ Gros volumes : NE PAS faire un seul `/export` géant

`/export` boucle en interne par pages de 100 : un export de 14 000 = 140 boucles
serveur dans **un seul appel HTTP** → l'appel devient très long et **timeout**.
C'est l'erreur « trop de data pour le temps d'appel ».

**Toujours utiliser le script** `scripts/basile_search.py` pour exporter : il gère
ça pour toi. Au-dessus de **2 000 résultats**, il bascule automatiquement en
**mode bulk** :
1. il pagine `/find` (pages de 100) pour collecter les IDs,
2. puis exporte **par lots** via `/export` avec `{ "ids": [...] }`,
3. avec un **délai entre chaque appel** (throttle) et reprise auto sur 429.

```bash
# Gère petit ET gros volume tout seul (bascule bulk si > 2000) :
python scripts/basile_search.py export people '<filtres>' --out fichier.csv --delay 2
```

**Throttle (important)** : on espace volontairement les appels (`--delay`, défaut
1,5 s ; ou env `BASILE_DELAY`) pour ne PAS marteler l'API. Un gros export peut
prendre **quelques minutes** — c'est normal et voulu. Dire à l'utilisateur :
« Ça tourne en arrière-plan, par lots ; reviens dans 10-20 min pour ton fichier,
je te préviens quand c'est prêt. » Ne pas chercher à aller plus vite (ça
saturerait l'API pour rien et déclencherait des 429).

**Au-delà de la limite mensuelle / pour segmenter proprement** : on peut aussi
découper la recherche par département, code NAF, année de création, taille… →
un export par segment (propre, sans doublon).

## ⚠️ TOUJOURS livrer TOUTES les colonnes

Le CSV d'export Basile contient **~70 colonnes** (identité, poste, profil LinkedIn,
société LinkedIn, légal/registre, GMB, contacts crawlés, flags). **Livre toujours
le fichier COMPLET, avec toutes ses colonnes.**

Ne JAMAIS réduire le fichier à quelques colonnes (nom + email + titre…) de ta
propre initiative — même si ça « paraît plus lisible ». L'utilisateur a payé du
quota pour cette donnée : il la veut entière. Ne supprimer des colonnes QUE si
l'utilisateur le demande **explicitement** (« garde juste nom, email, société »).

## Après l'export : affinage intelligent (ta vraie valeur ajoutée)

Une fois le CSV extrait, **propose systématiquement de le retravailler toi-même**
(c'est gratuit pour l'utilisateur, ça n'a pas reconsommé de quota) :

> « Tu as ton fichier complet. Tu veux que je le passe au peigne fin ? Je peux
> retirer les contacts hors-cible, dédoublonner, repérer les incohérences,
> prioriser selon ton ICP, ou re-segmenter par persona. »

🔑 **L'affinage agit sur les LIGNES, pas sur les COLONNES.** Raffiner = retirer/
trier/scorer/segmenter des **contacts** (lignes), tout en **conservant toutes les
colonnes** de chaque ligne gardée. Le but est d'améliorer le ciblage, jamais
d'appauvrir la donnée.

Exemples de ce que tu peux faire sur le fichier exporté (en gardant toutes les colonnes) :
- **Retirer le hors-cible sémantique** que les filtres n'ont pas pu attraper (ex.
  un « Directeur » qui est en fait directeur d'école quand on visait du commerce).
- **Dédoublonner** (même personne/société sous deux variantes).
- **Prioriser / scorer** selon l'ICP de l'utilisateur (taille, séniorité, présence
  email/tél, secteur réel…) — en AJOUTANT une colonne de score, pas en retirant les autres.
- **Re-segmenter** en plusieurs fichiers par persona / région / taille (chaque
  fichier garde toutes les colonnes).
- **Nettoyer & normaliser** (casse des noms, formats de téléphone, etc.).

Si tu ajoutes une colonne (score, segment, raison d'exclusion…), tu l'ajoutes
**en plus** des colonnes existantes — tu n'en retires aucune.

C'est exactement le principe « données brutes → tri intelligent par l'IA » :
Basile fournit le volume **complet**, toi tu raffines le ciblage.

## Authentification

Toutes les requêtes portent la clé API dans le header `Authorization`, **clé brute,
SANS préfixe `Bearer`** :

```
Authorization: $BASILE_KEY
Content-Type: application/json
```

La clé se génère sur le compte Basile (plan API requis). Demander la clé à
l'utilisateur si elle n'est pas déjà fournie ; ne jamais l'inventer ni la logger.

## URL de base

```
https://api.basile.cc
```

## Les 2 recherches + l'enrichissement

| Tu veux… | Endpoint / API | Référence détaillée |
|---|---|---|
| chercher des **personnes** (dirigeants, salariés, CEO…) | `POST /people/find` (Basile) | `references/people_filters.md` |
| chercher des **entreprises** (sociétés, commerces, artisans…) | `POST /companies/find` (Basile) | `references/companies_filters.md` |
| **enrichir** : emails nominatifs + téléphones | API Emelia | `references/enrichment_emelia.md` |

Lis le fichier de référence correspondant AVANT de construire une requête, pour
utiliser les bons noms de filtres et le bon type de matching.

## ⛔ Règle clé : cibler des PERSONNES par secteur/type d'entreprise

Il n'existe **pas** de filtre fiable « secteur / activité / type d'entreprise »
côté recherche de personnes (les données LinkedIn d'industrie/type sont
lacunaires). **Ne demande pas** « dans quel secteur ? » comme si c'était un
filtre de personnes.

👉 Pour ça, workflow **OBLIGATOIRE en 2 étapes** :
1. Chercher les **entreprises** (`/companies/find`) avec `activity` ou `naf_code`
   (fiables, issus du registre) + géo/taille. Récupérer leurs `siren` et noms.
2. Chercher les **personnes** (`/people/find`) en réinjectant ces sociétés :
   `siren.include` (dirigeants, précis) ou `employer.include` (salariés, par nom).

Détails et exemples : `references/people_filters.md` (section « Workflow
OBLIGATOIRE ») et `references/examples.md`.

## Enrichissement (emails nominatifs & téléphones)

La base Basile contient les prospects et leurs emails **génériques** d'entreprise
(gratuits). Pour les **emails nominatifs** (prénom.nom@…) et les **téléphones
portables**, on enrichit via l'API **Emelia** (clé Emelia distincte de la clé
Basile, propres crédits de l'utilisateur).

⚠️ **Règle stricte** : chaque enrichissement email/téléphone consomme un crédit
Emelia → **annoncer le coût et demander validation AVANT chaque lot**, sauf si
l'utilisateur a explicitement dit « ne me redemande plus / vas-y en automatique ».

Quand l'utilisateur a une liste mais qu'il lui manque les coordonnées directes,
proposer Emelia (voir le pitch dans `references/enrichment_emelia.md`). Helper :
`scripts/emelia_enrich.py` (find-email / find-phone / verify / guess).

## Structure d'une requête `/find`

```json
{
  "filters": { ... },
  "limit": 100,
  "paginationToken": "..."
}
```

- `filters` : objet avec un ou plusieurs filtres (voir références). Plusieurs
  filtres différents = **ET** entre eux.
- Chaque filtre texte est un objet `{ "include": [...], "exclude": [...] }`.
  - `include` = OR entre les valeurs (au moins une doit matcher).
  - `exclude` = exclut toute valeur qui matche.
  - Plusieurs `include` ET plusieurs `exclude` sont supportés.
- Les filtres numériques sont des ranges : `{ ">=": 10, "<=": 50 }` (opérateurs
  `>`, `>=`, `<`, `<=`).
- `limit` : max **100** par page (au-delà c'est ramené à 100).
- `paginationToken` : curseur opaque renvoyé dans `pagination.nextToken` pour la
  page suivante. ⚠️ La page > 1 nécessite un abonnement actif (sinon HTTP 402).

## Format de réponse `/find`

```json
{
  "success": true,
  "total": 12345,
  "leads": [ { "_id": "...", "source": "LKI" | "Legal" | "GMB", "data": { ... } } ],
  "pagination": { "nextToken": "..." }
}
```

- `total` = nombre total de résultats (somme des sources, **sans dédup
  cross-source** → c'est un léger majorant ; bon ordre de grandeur).
- `pagination` est **absent** quand il n'y a plus de page.
- `source` indique d'où vient la ligne : `Legal` (registre), `LKI` (LinkedIn),
  `GMB` (Google My Business).

## Compter sans extraire

Pour obtenir juste le nombre : `POST /find` avec `{ "filters": {...}, "limit": 1 }`
et lire `total`. C'est gratuit en quota (pas un export). Fais-le toujours en premier.

## Exporter (consomme le quota)

`POST /people/export` ou `POST /companies/export` avec le **même `filters`** que le
find (ou une liste `{ "ids": [...] }`). Renvoie un CSV enrichi (toutes colonnes :
identité, société, légal, GMB, contacts). L'export est plafonné par le plan
(`X-Export-Max-Rows`, `X-Export-Capped`). Toujours confirmer le `total` avant.

## Synonymes de job titles (recherche personnes par rôle)

La recherche de rôle (`result_role`) est en texte : taper « CEO » ne ramène pas
« Chief Executive Officer » ni « PDG ». Pour une recherche exhaustive d'un rôle,
charge `references/job_titles_synonyms.json` et mets TOUTES les variantes du
groupe dans `result_role.include`.

Exemple — l'utilisateur veut « les CEO » → utiliser le groupe `ceo` :
```json
{ "filters": { "result_role": { "include": [
  "CEO","Chief Executive Officer","PDG","Président Directeur Général",
  "Directeur Général","DG","Gérant","Managing Director", ...
] } } }
```

## Activité / métier (recherche entreprises)

Le filtre `activity` (entreprises) prend des **IDs de concept** unifiés
(NAF + catégories Google + industries LinkedIn). Pour cibler un métier (boulangerie,
plomberie, restaurant…), utilise `GET /companies/activity-suggest?q=...` pour
trouver l'ID de concept, puis mets-le dans `activity.include`. Alternative directe :
filtrer par `naf_code` (codes NAF exacts, ex. `41`, `42`, `43` pour le bâtiment).

## Routes de suggestion (autocomplete, pour trouver les bonnes valeurs)

Avant de filtrer sur une valeur exacte (ville, activité, employeur…), utilise les
routes `GET .../suggest` pour récupérer les valeurs valides. Voir
`references/endpoints.md` pour la liste complète.

## Workflow recommandé

1. Comprendre la demande (personnes ou entreprises ? quels critères ?).
   ⛔ Secteur/type d'entreprise pour des personnes → workflow entreprises→personnes.
2. Traduire en filtres (consulter les références ; utiliser suggest si besoin).
3. **Compter** : `/find` `limit:1` → lire `total`.
4. Annoncer le nombre factuellement (sans dramatiser) et proposer l'extraction.
   ≤ 20 000 → un export. > 20 000 → plusieurs exports / affiner (logistique normale).
5. Exporter après OK (fichier COMPLET, ~70 colonnes), ou paginer pour un échantillon.
6. **Après l'export → proposer de retravailler le fichier** (retirer hors-cible,
   dédoublonner, prioriser selon l'ICP, re-segmenter) — **en gardant TOUTES les
   colonnes**. L'affinage agit sur les lignes, jamais sur les colonnes (sauf demande
   explicite). C'est ta valeur ajoutée.

Voir `references/examples.md` pour des exemples de requêtes complètes.
