# RESTE À FAIRE — Genesis / Cheffer

> Fichier de reprise créé le 2026-08-20 après une fermeture de session anormale.
> Contient le plan par lots (défini le 2026-08-20 au matin) + l'état vérifié en direct.
> À tenir à jour à chaque fin de session, en même temps que `STATE.md`.

## État vérifié le 2026-08-20 à 13h20 (Paris)

| Indicateur | Valeur |
|---|---|
| Contacts PostgreSQL | 8 202 (2 008 créés aujourd'hui, réconciliation incluse) |
| Scrape du jour (dept 33) | 228 retenus · 801 examinés · **202 Serper / 26 Basile** |
| Crédits Serper restants | 38 712 |
| Emails partis aujourd'hui | 52 (campagne « Agent immobilier, loi Cazenave », 8h30 → 9h05) |
| Services PM2 | `genesis-ui`, `genesis-dashboard`, `genesis-mailnjoy-drain` en ligne |

## ✅ Les trois anomalies : corrigées le 2026-08-20 à 13h50

1. **Le dispatch de 8h30.** Diagnostic affiné : les compteurs de campagne sont dans
   **PostgreSQL** et étaient justes (124/1000, journée du 20 marquée) — c'est le miroir
   DuckDB `campaigns_unified`, plus lu par aucun écran, qui était resté en arrière. Le
   vrai dégât était ailleurs et unique : **`david.daries@gers-immobilier.fr` a reçu son
   email sans qu'aucune ligne de repoussoir soit posée**, le marquage ayant échoué sur le
   verrou — il était renvoyable. Réparé (journal PostgreSQL + cooldown du pool, gelé
   jusqu'au 2026-12-18) et le message d'erreur périmé de la campagne a été effacé.
   Cause structurelle corrigée : `mark_pushed_to_emelia` écrit désormais le journal
   PostgreSQL — qui PORTE la règle des 120 jours — **avant** d'ouvrir DuckDB.
2. **Le scraping.** Le plafond de 3 cibles, taillé pour une nuit, s'applique désormais
   par jour et vaut 12 en mode continu ; le vrai frein reste le quota de 1 000 contacts.
   Deux créneaux sont réservés, pendant lesquels aucune passe ne démarre :
   **06:20-07:20** (enrichissement + réconciliation) et **08:20-10:00** (dispatch).
   Collecte relancée dans la foulée sur le dept 64.
3. **`pg_reconcile`.** A tourné pour la première fois : PostgreSQL est passé de 8 216 à
   **8 170 contacts**, aligné sur le pool. `pg_gate._duck()` attend maintenant jusqu'à
   dix minutes que le pool se libère au lieu d'abandonner au deuxième essai — c'est ce
   qui l'empêchait de tourner en 24 h/24. Garde-fou `[NON-DIFFUSIBLE]` vérifié par test.

## Le détail des anomalies (constat initial)

1. **Le dispatch de 8h30 s'est arrêté sur un verrou DuckDB après 52 envois.**
   `god_mode.duckdb` et `contacts.duckdb` étaient pris par le scraping. Les emails sont
   bien partis (`maildoso_sent` = 52, statut `sent`) et les compteurs PostgreSQL — la
   source — étaient justes ; seul le miroir DuckDB `campaigns_unified` était en retard
   (première lecture trompeuse, il n'est plus lu par aucun écran). Le dégât réel :
   **un contact sur 52 n'a pas eu sa ligne de repoussoir**, donc restait renvoyable.
2. **Le scraping est à l'arrêt depuis 11h12** alors qu'il est censé tourner 24 h/24 :
   `autoscrape_daily` répond « quota de la nuit atteint (3/3 cibles) ». Le plafond de
   3 cibles hérité de la fenêtre nocturne n'a pas été levé en même temps que l'horaire.
3. **`datagouv_enrich` puis `pg_reconcile` n'ont pas encore été validés** depuis le
   correctif de ce matin (`[NON-DIFFUSIBLE]` + cron passé de `&&` à `;`). Le garde-fou
   est bien dans le code ; `logs/pg_reconcile.log` **n'existe toujours pas**.
   Premier vrai test demain 6h30 UTC.

## Journée du 2026-08-21

- ✅ **Classement des secteurs enregistré** (`sector_policy`, lcr + mkd) — `artisan`
  collecté mais secondaire, 376 cibles interdites retirées. **Le Lot 2 est clos.**
- ✅ **Liste noire des adresses de rôle** — `contact@`, `info@`, `compta@`, gabarits :
  rejetés à la collecte. Les 1 943 déjà en base sont conservés (décision Camille : voir
  d'abord s'ils répondent).
- ✅ **Page Statistiques** `/site/{code}/statistiques` + table `campaign_recipients` +
  cron horaire de reconstruction. **Ce n'était dans aucun lot** — c'est l'outil de mesure
  qui manquait pour arbitrer tout le reste.
- ✅ Alertes réparées (le fichier d'état appartenait à `root`, le cron tourne en
  `autoblog` : il plantait toutes les heures depuis le 20/08 13h53). **Le Lot 5 est clos.**
- ✅ **Correctifs Basile appliqués le 21/08** : collecte par département (gain mesuré ×2,6 à
  ×6 selon le secteur) et les 7 secteurs inertes câblés via le catalogue. Doc corrigée.
- ⛔ **Reste la voie « dirigeants nommés »** (Emelia, 1 crédit/dirigeant, PAYANT) — devenue
  la seule source de volume nominatif depuis la liste noire des adresses de rôle. Attend
  l'arbitrage de Camille sur le coût.
- ⛔ **Contention DuckDB** : le dispatch et le scraping se disputent `god_mode.duckdb`.
  Gêne sans bloquer ; disparaîtra avec la fin du Lot 1.

## Le plan par lots

- **Lot 0 — Relevé technique `/admin/etat-technique`** — ✅ livré le 2026-08-20.
- **Lot 1 — Pool dans PostgreSQL** — 🟡 en cours. PostgreSQL accueille tous les
  contacts (la porte est devenue un drapeau `etat`). Restent : Acquisition et les
  compteurs de cible lisent encore le pool DuckDB · le scraper y écrit toujours
  (dual-write, qui échoue sous verrou) · les journaux d'envoi (`maildoso_sent`,
  `mass_campaigns`, `sweego_events`) sont encore dans `god_mode.duckdb`.
  Fin du lot = le fichier de 1 Go disparaît et le verrou avec lui.
- **Lot 2 — Page des secteurs (prioritaire / secondaire / interdit)** — ⛔ pas commencé,
  **attend l'arbitrage de Camille** sur la répartition proposée. Trois colonnes en
  glisser-déposer, stockage en base, et surtout : le classement pilote réellement la
  file `autoscrape_targets` (1 504 cibles en attente) et les filtres Basile (NAF ↔ secteur).
  *C'est le lot qui corrige le déséquilibre 26 Basile / 202 Serper — donc le budget Serper.*
- **Lot 3 — Autoscrape continu** — 🟡 quasi fait (24 h/24 ouvert le 2026-08-20), sauf le
  plafond de 3 cibles/nuit décrit en anomalie n°2.
- **Lot 4 — Automatisation des campagnes** — ⛔ pas commencé. Une adresse expéditrice
  par secteur · moteur de 8 h qui calcule le volume envoyable par boîte · contrôle
  anti-spam · routage automatique · refroidissement 48 h en cas de plaintes.
  *C'est lui qui fait passer de 160 à 1 000 emails/jour : 4 boîtes × 40 plafonnent tout.*
- **Lot 5 — Alertes** — ⛔ pas commencé. Le relevé technique existe, il manque la
  sonnerie Telegram quand une tâche n'a pas tourné.

## Décisions en attente (Camille)

- **Répartition des secteurs** (proposition du 2026-08-20 : prioritaires `retail`,
  `restaurant`, `coiffeur`, `garagiste`, `fleuriste`, `boulanger`, `tourisme`,
  `immobilier`, `education-formation` ; interdits : concurrents SMS, démarchage
  réglementé, santé).
- **Plafond de scraping** : rester à 1 000/jour (7 crédits Serper par contact →
  la réserve tient ~5 jours au rythme actuel) ou redescendre en attendant le Lot 2.
- `/onboarding` (570 lignes, aucun lien entrant) : garder ou supprimer ?
- Fusionner « Vision » dans le tableau de bord ?
- Règle de promotion PRM sur le flux `campaign=default` (pollué par les proxys antispam).
- `phone_enrich_backend` : 0 numéro sur 56 tentatives → le débrancher au profit d'une
  requête Serper Places sur les 622 contacts « société sans téléphone ».
- `/code-review ultra` sur le mini-CRM : déclenchable par Camille uniquement.

## Petites dettes

- Segment « Ile de france 75 » créé avant le correctif du sélecteur géographique :
  aucune zone enregistrée, à rouvrir et recibler.
- Le message de démarrage d'un scrape mentionne encore les butoirs de nuit (cosmétique).
- 3 tests en échec dans `test_mailnjoy_check.py`, antérieurs à ce chantier.
- Le plafond de pression marketing se règle dans `.env`, pas à l'écran.
- Refonte UI phases 4-5 : 8 `catch` vides sur Campagnes, 22 `confirm()` natifs,
  11 tableaux sans défilement, 50 largeurs figées.
- Écrans Articles et Versions : encore un « Chargement… » texte, sans indicateur.
- `pg_sync.promote_contact` lent en masse (1 connexion PG + 1 DuckDB par contact).
- CRM legacy `crm/{site}.duckdb` encore écrite par 5 producteurs, plus lue par aucun écran.
- 1 573 des 1 996 contacts d'août sans `dept_code` → invisibles au ciblage géo.

## Ordre recommandé

1. Les trois anomalies ci-dessus (une demi-journée, elles faussent les chiffres).
2. **Lot 2** — coûte le moins, débloque le plus (Basile → volume → budget Serper).
3. **Lot 4** — sans lui, le volume scrapé ne part pas.
4. Fin de la migration PostgreSQL (Lot 1) — gêne, ne bloque pas.
5. **Lot 5** — alertes.
