# RESTE À FAIRE — Genesis / Cheffer

> Mis à jour le **2026-08-24** (fin de session). Détail complet dans STATE.md,
> qui porte 13 blocs pour cette seule journée.

## Lot 1 — Pool dans PostgreSQL : CLOS (2026-08-23)

| Volet | État |
|---|---|
| Miroir aligné (enrichissement, verdict Mailnjoy) | ✅ |
| Acquisition + compteurs lus dans PostgreSQL | ✅ |
| Contacts perdus par le verrou : rattrapés et filet posé | ✅ |
| Journaux d'envoi hors `god_mode.duckdb` | ✅ |

**Ce que ça a débloqué, chiffré :**
- **1 077 contacts** étaient `etat = 'ok'` mais écartés de toute campagne : leur verdict
  Mailnjoy n'avait jamais été recopié dans PostgreSQL (il ne l'était qu'à l'insertion).
- **530 contacts** vérifiés et payés dormaient dans `god_mode.scrappe` sans jamais atteindre
  le pool — la double écriture du scraper tombait sur le verrou DuckDB (712 erreurs en
  journal). Récupérés. 446 adresses de rôle et 3 064 rejets délibérés ont été écartés à
  bon droit.
- Total : le pool passe de 10 027 à **10 557 contacts**, dont **7 920 contactables**
  (contre 7 392).
- Acquisition, Vision, le tableau de bord et les valeurs de filtre ne touchent plus le
  fichier que le scraping verrouille. Repli DuckDB automatique si PostgreSQL tombe.

**Les journaux d'envoi sont passés sur PostgreSQL.** Cause racine du comptage double
trouvée et corrigée : le filet de fin de lot de `campaign_engine` re-marquait TOUS les
contacts au lieu des seuls dont le marquage avait échoué — 316 lignes de journal pour 160
emails réellement partis le 22/08. Personne n'a reçu deux fois le message. Au passage :
1 738 ouvertures et 998 clics Sweego versés au journal (ils n'y étaient pas), table
`mass_sends` créée, BAT enfin journalisés, et la barrière anti-renvoi couvre désormais
tous les canaux au lieu du seul Maildoso. Neuf lectures portées, repli DuckDB partout,
`tests/test_pg_journal.py` vert.

**Une commande reste à lancer par Camille** (le classifier refuse la suppression) :
`python3 scripts/journal_dedoublonner.py --apply` — retire les 159 lignes en double déjà
en base et pose l'index unique. Les lectures sont déjà justes sans, c'est un nettoyage
d'historique plus une ceinture.

## Lot 4 — Automatisation des campagnes : CLOS (2026-08-23)

| Brique | État |
|---|---|
| Garde-fou variables de gabarit (7 formes, refus avant SMTP) | ✅ |
| Affinité expéditeur : 1 contact = 1 adresse, à vie | ✅ 963 attribués, 441 confirmés |
| Surveillance domaine (SPF/DKIM/DMARC/listes noires), cron 7h45 | ✅ |
| Alerte ouverture < 5 %, rebond > 3 %, plainte > 0,1 % | ✅ branchée sur `alertes.py` |
| Montée en charge branchée sur les vrais signaux | ✅ |
| Cadence 140 emails/jour d'ici vendredi 28/08 | ✅ posée et vérifiée |
| Une adresse expéditrice par secteur | ⛔ abandonné — remplacé par l'affinité par contact |
| File d'envoi qui ne se vide jamais (`programmation.py`, cron 7h50) | ✅ |
| Refroidissement 48 h après plainte (`refroidissement.py`) | ✅ |
| Contrôle anti-spam bloquant avant le lot | ✅ |
| Routage multi-canal respectant l'affinité (`routage.py`) | ✅ |

**État du domaine ce soir :** SPF `~all`, DKIM `selector1` valide, DMARC `p=reject`,
ouverture **39,1 %** sur 7 jours (33 à 46 % selon la boîte), 0 rebond, 0 plainte, 0 alerte.

**Cadence posée** sur « Agent immobilier, loi cazenave » : lun 80 · mar 100 · mer 120 ·
jeu 130 · **ven 140** · sam 121.
La campagne atteint sa cible samedi : **lundi 31/08 la file serait vide**. Le cron de
7h50 la prolonge désormais tout seul tant que le vivier suit (2 785 contacts immobilier
piochables), et alerte si le vivier ne suit plus — créer une campagne reste une décision
humaine (message + ciblage), la machine ne l'invente pas.

## À reprendre à froid — écarté le 2026-08-24, sciemment

Deux chantiers justes, identifiés par la revue de simplification, **volontairement non
faits** parce qu'ils touchent le chemin d'envoi des campagnes un jour où il tournait :

1. **Unifier les trois fenêtres horaires.** `deliverability_agent.within_send_window()`
   (campagnes, 08:01–17:59), `mozart.fenetre_ouverte()` (scénarios, 09:01–18:30) et
   `maildoso_backend._cadence()` écrivent trois fois la même mécanique. Une seule fonction
   paramétrée par profil, appelée depuis `send_email`, fermerait la porte : aujourd'hui,
   **ni `send_email` ni `send_batch` ne contrôlent l'heure** — ce sont les appelants qui le
   font, donc un nouveau chemin d'appel enverrait à 3 h du matin.
   ⚠️ Décision en attente de Camille au passage : faut-il **aligner** les deux fenêtres ?
   Elles diffèrent d'une heure de chaque côté.

2. **Sortir la cadence par boîte de la mémoire du process.** `_DERNIER_ENVOI` est un
   dictionnaire en RAM : l'écart de 4 minutes tient à l'intérieur d'un lot, jamais ENTRE le
   dispatch des campagnes et le tick Mozart, qui ne tournent pas dans le même process.
   L'horodatage devrait se lire dans `email_events`, comme le compteur du jour.

## Décision de Camille en attente — les plafonds d'envoi

Les 4 boîtes ont été créées le 2026-07-07 et portent **40/jour depuis l'origine** : la
montée en charge n'a jamais rien fait monter, elle a seulement confirmé un plafond déjà au
maximum. Depuis le 24/08 un **plafond de progression** (+50 % de la moyenne des 7 derniers
jours actifs) limite le saut d'un jour sur l'autre — plafonds effectifs à 22-24 aujourd'hui.
Reste à trancher : redescendre les plafonds pour une vraie chauffe, ou assumer 40 sur des
boîtes de sept semaines. Santé actuelle : **46 % d'ouverture sur 30 jours, 0 plainte,
0 rebond récent** — le profil est sain, le risque était le RYTHME, pas le volume.

## Mozart — scénarios d'automatisation (2026-08-24)

Éditeur visuel sur React Flow, menu Campagnes → **Mozart**. Quatre types de nœuds :
déclencheur, délai, email, condition (ouvert / cliqué). Le graphe affiché est celui qui
s'exécute. Contrôle à l'activation, simulation à sec, statistiques sur les nœuds, édition
du message sans quitter le scénario.

**Canaux : Maildoso et Sweego uniquement** (décision Camille du 24/08). Emelia travaille
par campagne entière, pas contact par contact — incompatible avec un scénario. Sur un nœud
email : le canal, puis l'expéditeur si le canal en propose plusieurs (Maildoso a 4 boîtes,
Sweego une adresse unique). **L'affinité l'emporte toujours** : un contact qui a ouvert ou
cliqué garde son adresse, quel que soit le réglage du nœud.

Le moteur n'a **aucun privilège** : chaque email passe par les protections des campagnes
(120 jours, variables, affinité d'expéditeur, plafonds, boîtes au repos). Cron horaire.

⚠️ **En BÊTA FERMÉE : réservé au compte `camille`.** L'entrée s'affiche pour tout le monde
dans la sidebar, étiquetée « bêta » et grisée ; seul le compte autorisé peut l'ouvrir, et
la barrière est côté serveur. Pour ouvrir à quelqu'un d'autre : ajouter son identifiant à
`PAGES_BETA_TESTEURS` dans `.env`. Pour sortir de la bêta : retirer `beta: True` de la page
`mozart` dans `roles_backend.PAGES`.
Un scénario d'exemple attend en brouillon : *relance immobilier J+1 / J+4*.

## Fait cette session (21→23/08) — tout déployé
Sécurité complète (Cloudflare + verrou origine + 127.0.0.1 + force brute), Basile par
département + 7 secteurs, liste noire adresses de rôle, page Statistiques, agent Stéphane,
matrice des droits par rôle, fiche d'appel (script/RDV/blacklist/Signature+confettis),
Opportunités + Ventes, Mon activité commercial, refonte Scraping/tableau de bord/login+Cheffer.
Pannes réglées : pg_reconcile (log root) + corruption %20 (extraction web).

## Reste — attend le feu vert de Camille
- Argumentaires `restaurant` et `tourisme` — **en attente, décision Camille du 23/08** : on reste sur l'immobilier seul pour l'instant.
- Refonte plaquette PDF (désactivée par défaut, case opt-in en place).
- Mineurs sécurité : hachage SHA-256 hérité, énumération par timing du login.

---

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
- **Lot 1 — Pool dans PostgreSQL** — ✅ CLOS le 2026-08-23. Acquisition, Vision, le
  tableau de bord, les compteurs ET les journaux d'envoi lisent PostgreSQL ; les écritures
  qui portent une règle métier y vont en premier. `god_mode.duckdb` n'est plus lu que par
  le relevé technique. Détail en tête de fichier.
- **Lot 2 — Page des secteurs** — ✅ CLOS le 2026-08-21. Vérifié en base le 23/08 :
  `sector_policy` porte 7 prioritaires, 12 secondaires et 9 interdits, sur lcr ET mkd.
- **Lot 3 — Autoscrape continu** — ✅ CLOS. 24 h/24 depuis le 2026-08-20 et le plafond de
  cibles est passé de 3/nuit à `SCRAPE_MAX_CIBLES_JOUR=30` (vérifié dans `.env` le 23/08).
- **Lot 4 — Automatisation des campagnes** — ✅ CLOS le 2026-08-23. Affinité expéditeur
  par contact (et non par secteur), volume par boîte piloté par la délivrabilité, contrôle
  anti-spam bloquant, routage respectant l'affinité, refroidissement 48 h après plainte,
  et file d'envoi qui se prolonge seule. Détail en tête de fichier.
  *Le plafond de 160/jour reste celui des 4 boîtes : le dépasser demande d'en ouvrir
  d'autres, pas de changer le code.*
- **Lot 5 — Alertes** — ✅ CLOS le 2026-08-21. `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`
  renseignés, `alertes.py` sonne au CHANGEMENT d'état (un rappel par jour, pas davantage).
  Dix tâches surveillées depuis le 23/08, contre quatre auparavant.

> **Les six lots sont clos.** Ce qui suit n'est plus un plan, c'est un inventaire de dettes
> et de décisions.

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

## Entrées retirées le 2026-08-23 après vérification

- **« Bouton appel passé »** — l'entrée était FAUSSE. Le chemin d'enregistrement existe
  déjà (`followup_backend`, ligne ~694 : `est_un_appel` journalise un événement `appel`
  avec statut, issue, note et date de relance), et `ActionsAppel` porte déjà les gestes de
  l'appel. Ce qui manque n'est pas un bouton : `followup_events` contient **2 appels
  consignés en quatre jours** pour un objectif de 10 par commercial et par jour. Personne
  ne consigne. Et même consigné, le chiffre reste **purement déclaratif** — rien ne compose
  depuis Cheffer, aucune téléphonie n'est branchée : il mesure ce que quelqu'un a tapé, pas
  ce qui s'est passé. Ajouter un bouton n'y change rien. Retirée sur remarque de Camille,
  qui avait raison de la contester.
- **`contact@cheffer.email`** — corrigé dans `scripts/plaquette.py`. Le domaine
  `cheffer.email` n'a AUCUN MX (vérifié) et ne sert qu'à l'API. L'adresse de contact est
  `contact@leclientroi.com`, dont le MX (`smtp.google.com`) reçoit bien.

## Petites dettes

- Segment « Ile de france 75 » créé avant le correctif du sélecteur géographique :
  aucune zone enregistrée, à rouvrir et recibler.
- Le message de démarrage d'un scrape mentionne encore les butoirs de nuit (cosmétique).
- 3 tests en échec dans `test_mailnjoy_check.py`, antérieurs à ce chantier.
- Le plafond de pression marketing se règle dans `.env`, pas à l'écran.
- Refonte UI phases 4-5 : 8 `catch` vides sur Campagnes, 22 `confirm()` natifs,
  11 tableaux sans défilement, 50 largeurs figées.
- Écrans Articles et Versions : encore un « Chargement… » texte, sans indicateur.
- `pg_sync.promote_contact` : le volet PostgreSQL est réglé (pool partagé, 2026-08-23),
  il reste l'ouverture DuckDB par contact.
- CRM legacy `crm/{site}.duckdb` encore écrite par 5 producteurs, plus lue par aucun écran.
- `dept_code` : 663 contacts récupérés depuis leur ville le 2026-08-23 (2 166 → 1 503).
  Les 1 503 restants sont l'import Sweego du 20/08, **sans ville ni code postal** : rien à
  en tirer sans les recollecter. Cause corrigée à la source — `pool_rattrapage` résout
  désormais le département depuis la ville, comme le fait le scraper ; `god_mode.scrappe`
  ne le stockait que sur la voie Basile (17 lignes sur 7 971 côté Serper).

## Ordre recommandé (mis à jour le 2026-08-23)

Les six lots étant clos, il ne reste que des décisions et des dettes. Par ordre d'effet :

1. Les dettes techniques ci-dessus, aucune bloquante.

**Clos le 2026-08-24, ne pas rouvrir :**
- *Test 4G du pare-feu* — inutile : la chaîne `CF_LOCK` est active sur les ports 80 et 443,
  ce qui se lit directement dans `iptables -L INPUT`. Rien à confirmer par téléphone.
- *Dédoublonnage du journal* — sans objet depuis que la CAUSE est corrigée (le filet de
  fin de lot ne re-marque plus tout le monde) et que tous les comptages portent sur des
  ENVOIS distincts et non sur des lignes. Les 159 lignes historiques sont inertes.
- *Voie « dirigeants nommés »* — lancée, passée en cron nocturne (30 crédits/nuit).

Décidé le 2026-08-23 : on reste à **4 boîtes** (160 emails/jour de capacité), et les
argumentaires restaurant/tourisme attendent.
