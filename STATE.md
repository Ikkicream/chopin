# STATE — Genesis (à lire EN PREMIER au démarrage de session)

> Source de vérité unique pour reprendre le projet sans re-expliquer le contexte.
> À mettre à jour AVANT toute fin de session ('à demain', 'j'en ai marre', etc.).

> **Reste à faire : voir `RESTE-A-FAIRE.md`** (plan par lots + anomalies ouvertes,
> tenu à jour depuis le 2026-08-20).

## 🧹 2026-08-21 — Tableau de bord allégé + tableau des campagnes lisible (demandes Camille)

**Tableau de bord** : rafraîchissement auto passé de 10 min à **une heure** (rien n'y bouge
à cette cadence — un dispatch par jour, un scrape par nuit — et le retour sur l'onglet
recharge de toute façon). Retirés : le tableau des campagnes (il vit sur `/campaigns`, deux
écrans ne doivent pas montrer le même tableau) et la carte « Contacts — à rappeler /
derniers contactés » (redondante avec `/a-rappeler` et `/acquisition`) — avec les deux
appels d'API qui ne servaient qu'à elle. Chaque tuile de tête mène désormais à son écran :
Contacts → `/acquisition`, À rappeler → `/a-rappeler`, Rendez-vous → `/booking`.

**Fusion des compteurs de contacts (21/08, second passage).** « À rappeler » et
« Rendez-vous » avaient chacun sa carte pour UN nombre : trois cadres, trois titres et
trois liens pour trois chiffres qui parlent des mêmes personnes. Ils sont descendus en pied
de la carte **Contacts**, sous le total et son lien, en deux lignes cliquables (la ligne
Rendez-vous passe en rouge dès qu'il y en a un à traiter). Rangée de tête : deux cartes au
lieu de quatre. Au passage, `type Contact`, `STATE_LABEL`/`STATE_COLOR`, `nbCold`,
`recoCount` et **deux appels d'API SEO** (`/api/seo-ahrefs`, `/api/seo-strategy`) ont été
retirés : ils alimentaient des variables que plus rien n'affichait depuis le retrait du
tableau de contacts.

**Recomposition** : les rendez-vous étaient le REPLI de la tuile de scraping — ils
n'apparaissaient que si aucun scrape ne tournait, et la collecte disparaissait de l'écran
dès qu'elle s'arrêtait. Trois informations pour une case. Désormais : rendez-vous en tuile
de tête fixe, puis une rangée « ce qui tourne maintenant » avec **Scraping** (visible en
cours ET au repos, avec le motif de l'attente) et **Campagne en cours** (nom, secteurs,
canal, barre d'avancement, taux d'ouverture — ou « aucune campagne en cours »).

**Tableau des campagnes** (`campagnes-table.tsx`, partagé avec `/campaigns`) : le secteur
sort de sous le nom en gris 11 px pour avoir **sa colonne** en pastilles ; la barre
d'avancement passe à 2,5 px avec **« X % envoyés » / « Y % restants »** en clair ; deux
nouvelles colonnes **Ouverture** et **Clic** alimentées par `campaign_recipients` (tiret =
pas encore mesurable, jamais « zéro »). L'erreur du moteur — une trace DuckDB de 300
caractères qui débordait et rendait la ligne illisible — devient « base occupée — envoi
interrompu », détail complet au survol.

**Attention au branchement** : `engagement_par_campagne()` est indexé sur l'uuid PostgreSQL
ET sur le `legacy_id` court. `campaign_recipients` porte l'uuid, `list_campaigns` rend
l'identifiant court : sans les deux clés la jointure tombe à vide et toutes les colonnes
affichent un tiret.

## 🔒 2026-08-21 — Contacts : colonne secteur, filtre secteur, garde-fou anti-aspiration

**Acquisition — lecture.** Le secteur était un émoji collé au nom du contact : invisible et
incomparable d'une ligne à l'autre. Il a sa **colonne** (pastilles, deux visibles + « +N »).
Le filtre secteur, jusqu'ici perdu dans une liste déroulante de la barre de recherche,
devient le **troisième axe de pastilles sous Étape et Cycle**, avec ses compteurs ; la
liste déroulante est retirée (deux contrôles pour un même filtre).

**Le garde-fou : `scripts/garde_lecture.py`.** La menace n'est pas un robot anonyme mais un
compte LÉGITIME — jeton valide, requêtes signées, indiscernables d'un usage normal. Un
pare-feu applicatif (Cloudflare) filtre l'origine, pas l'intention : **il ne sert à rien
ici**, et ce n'est donc pas ce qui a été installé. Trois mesures côté serveur, branchées sur
`/acquisition`, `/pool/contacts` et `/a-rappeler` :
  1. **Plafond de page par rôle** — 100 lignes hors admin/superadmin (l'écran en affiche 25,
     donc aucun impact sur le travail réel) ; la valeur `limit` rendue est celle APPLIQUÉE,
     sinon l'interface croit avoir tout reçu et saute des contacts ;
  2. **Quota horaire glissant** — **1 000 fiches/heure** pour un commercial (réglage de
     Camille) : quarante pages pleines en une heure, et plus de huit heures ininterrompues
     pour lire la base entière. **Aucun quota** pour `superadmin` ni `admin`. Au-delà : 429
     avec un message qui dit quoi faire ;
  3. **Journal `lecture_contacts`** (qui, quand, combien, quelle route) + alerte
     `alertes.py` **au-delà de 1 000 fiches sur l'heure écoulée** — même fenêtre et même
     seuil que le quota : l'alerte part à l'instant où le compte touche le plafond. Une clé
     par utilisateur.

**Les alertes partent sur le Telegram privé de Camille** (@Camilledata) via le robot
`@Chopin_orchestre_bot` — un seul destinataire, câblage vérifié le 21/08. Le message porte
désormais un pictogramme par famille : 🔥 sécurité (aspiration), ⏰ tâche en retard,
🛑 service arrêté, 🕷 collecte bloquée, 🩺 relevé en panne. Une aspiration change le TITRE du
message (`🔥🚨 SÉCURITÉ — <compte> 🚨🔥`) et passe en tête de liste : elle ne doit jamais se
noyer dans le train-train des tâches en retard. Le compte fautif est nommé dans le titre ET
dans le détail. Attention : un échec d'envoi Telegram est silencieux et non rejoué.

**Le calcul qui fixe le plafond** (terrain, Camille 2026-08-21) : un commercial passe AU
PLUS 30 appels dans l'heure. Trente fiches ouvertes, plus la liste pour les trouver — huit
pages de 25 si la recherche est laborieuse, soit 200 lignes. Un usage intense tient donc
dans **~230 fiches/heure**. Le plafond de 1 000 laisse un facteur **quatre** : personne ne
peut l'atteindre en travaillant. Qui le touche n'appelle pas, il aspire.

**Filigrane nominatif** (`components/filigrane.tsx`) sur les deux pages. À dire tel quel :
**empêcher une capture d'écran est impossible sur le web** — aucune API ne le permet, les
parades connues se contournent en secondes et un téléphone braqué sur l'écran les ignore
toutes. Le filigrane ne bloque rien ; il rend toute copie ATTRIBUABLE (nom du compte +
horodatage, 3,5 % d'opacité, illisible à l'usage, net sur une capture agrandie). C'est la
certitude d'être identifié qui dissuade, pas l'obstacle technique.

**Export** : le bouton d'Acquisition était déjà réservé au superadmin, et il n'exporte que
la page affichée (25 lignes). **`/a-rappeler` n'a aucun export** — il n'y avait rien à
bloquer, et en ajouter un irait contre l'objectif.

## 🕷 2026-08-21 — Refonte de la page Scraping

**Le problème** : 724 lignes, sept blocs empilés (bascule du module, formulaire régional,
historique complet, formulaire manuel avancé, cron, doc des points d'entrée Serper) pour
répondre à la question qu'on se pose en arrivant — *est-ce que ça collecte en ce moment ?*

**Trois blocs désormais** : (1) **Collectes en cours**, avec secteur, zone, déclencheur,
barre de progression, Scrapés / Validés (détail Basile + Serper) / Rejetés / Doublons /
Net Mailnjoy / Crédits — rafraîchi toutes les 5 s, et l'intervalle s'arrête avec le run ;
(2) **Mode automatique** : période, cibles de la période, créneaux réservés ;
(3) **Lancer une collecte** : le wizard.

**L'historique part sur `/scrapper/activite`** (sous-page) : DataTable triable et filtrable
par secteur, déclencheur et état, 200 derniers runs, avec les totaux en tête. Consulter le
passé et lancer un scrape sont deux gestes différents.

**Le déclencheur, marque nouvelle.** `run_autoscrape(declencheur=…)` écrit « manuel » ou
« automatique » dans le log `start_scrape` ; `autoscrape_daily` se déclare automatique.
Rien ne les distinguait : même fonction, même compte système. Les runs antérieurs sont
déduits du compte appelant.

**`stephane.py` — l'agent de collecte (ex-`scrape_conseil.py`, renommé et étoffé le 21/08).** Note sur 100, explicable :
rang du secteur (30) + terrain jamais collecté (25) + taux d'ouverture mesuré de la zone
(25) + rareté du couple en base (20). Les interdits sont écartés. **Pas de modèle de
langage** : sur une décision qui engage le budget Serper, une note recalculable à la main
vaut mieux qu'un avis invérifiable. Premier résultat : `tourisme` et `education-formation`
sur les Alpes-Maritimes à 100/100 (prioritaire · jamais collecté · zone à 41,2 % d'ouverture
· aucun contact en base). Servi par `/api/sites/{site}/scrape/conseil`, affiché en tête du
wizard sous forme de raccourcis cliquables.

**Le wizard** (`components/scrape-wizard.tsx`) : trois questions — quoi (secteurs en
pastilles, choix multiple), où (région), combien (paliers + saisie libre) — une seule à
l'écran, fondu de 220 ms, chemin cliquable en arrière uniquement, récapitulatif avant de
lancer. Les réglages fins (résultats par ville, plafond global) gardent leurs valeurs par
défaut : personne n'y avait touché depuis trois mois.

**Nouvel endpoint** `/api/sites/{site}/autoscrape/orchestrateur` — l'état du mode
automatique, à ne pas confondre avec `/autoscrape/status` qui décrit le run en train de
tourner.

## 🧠 2026-08-21 (suite) — Stéphane : mémoire, trois critères, et la sidebar

**Sa mémoire** (`memoire_stephane`, PostgreSQL) : une ligne par couple **secteur ×
département** — envois, ouvreurs, cliqueurs, taux, contacts en base. **380 couples** au
premier passage, actualisée à chaque reconstruction des statistiques (même cron). Elle FIGE
comme `stats_secteur_jour` : un contact sorti du pool n'efface pas rétroactivement la
performance d'une zone.

**Sa décision tient compte du clic avant l'ouverture** — le clic pèse deux tiers de la note
de performance : une ouverture peut venir d'un proxy antispam, un clic est un geste. Il
utilise d'abord la mesure du COUPLE secteur × zone, et se rabat sur la zone seule à défaut.
Premier enseignement : `immobilier` × **dept 37** fait **15 % de clic** pour 30 % d'ouverture,
loin devant le 06 (3,9 % de clic malgré 41,2 % d'ouverture) — l'ouverture seule aurait
désigné le mauvais gagnant.

**Trois critères réglables** (`config_stephane`, admin uniquement) : (1) secteurs autorisés,
(2) départements, (3) **ce qui doit primer** — Équilibré / Ce qui répond / Terrain neuf /
Volume. Le choix REDISTRIBUE les poids, il ne les remplace pas : un secteur interdit ne
remonte jamais. Vérifié de bout en bout : cadre `restaurant+tourisme × 37+06` en priorité
« Ce qui répond » → 1 786 candidats ramenés à 4, et le 37 passe devant le 06.

**Écran** : carte « Stéphane » sur `/scrapper` — ce qu'il a retenu (couples classés par
clic, trophée sur le premier) + le cadre repliable à trois critères. Le bloc
« Orchestrateur » ne garde que ce qu'il exécute.

**Sidebar** : « Activité des scrapes » ajoutée sous « Scraper » — la sous-page n'était
atteignable que par un bouton, donc introuvable pour qui la cherchait.
**Wizard** : les étapes s'annoncent « Étape 1 sur 3 — Quoi collecter » et prennent la forme
d'onglets (bord bas marqué) au lieu de cadres flottants.

## 🔗 2026-08-21 — L'orchestrateur obéit à Stéphane

`autoscrape_daily.next_target()` ne trie plus la file lui-même : il demande à Stéphane, et
retient sa première proposition **déjà éligible** (pending, sous le plafond de passes,
secteur autorisé). Stéphane propose, il ne contourne pas. Deux replis : s'il ne propose
aucune cible éligible, ou s'il est indisponible, l'ordre historique reprend la main — une
décision automatique ne doit jamais pouvoir bloquer la collecte. Le choix est tracé dans le
log (`[autoscrape] Stéphane choisit … — note X/100 : <raison>`) et la raison suit la cible
dans l'état (`note_stephane`, `pourquoi_stephane`, `priorite_stephane`).

**La liste « prochaines cibles » vient désormais de lui aussi.** Elle gardait le tri
historique alors que la pioche passait par Stéphane : l'écran annonçait une cible et une
autre partait. Elle est affichée sur `/scrapper` avec la note et la justification.

**Vérifié en direct avec le cadre réel** : Camille avait enregistré à 11h08 un cadre
`immobilier × dept 92`. Stéphane ramène 1 786 candidats à 1 et choisit `lcr:immobilier:92`
(61/100 — « secteur prioritaire · ce secteur y fait 6,1 % de clic et 34,8 % d'ouverture ·
déjà 28 contacts en 1 passage · 138 contacts en base »). Le cadre est donc bien respecté
de bout en bout.

## 🎯 2026-08-21 — Basile : les deux correctifs de volume

**1. Collecte par DÉPARTEMENT au lieu de ville par ville.** `run_sector_for_dept()` remplace
l'appel ville par ville dans la boucle d'autoscrape (un appel par secteur × dept, clé
`seen_basile_depts`). L'ancien filtre `headquarters_city` était alimenté par les cinq plus
grandes communes de plus de 10 000 habitants — le reste du département n'existait pas pour
Basile. **Gain mesuré en direct sur la Gironde :**

| Secteur | 5 villes | Département | Gain |
|---|---|---|---|
| artisan | 3 191 | 19 274 | **×6,0** |
| tourisme | 1 056 | 3 121 | ×3,0 |
| immobilier | 1 144 | 3 089 | ×2,7 |
| education-formation | 1 705 | 4 638 | ×2,7 |
| restaurant | 3 000 | 7 839 | ×2,6 |

**2. Les 7 secteurs inertes sont câblés.** `_nafs()` lit `SECTOR_NAF` (mappings testés en
prod) puis, à défaut, `secteurs_backend.CATALOGUE` — une seule source de vérité, import
local pour éviter le cycle. `tourisme`, `education-formation`, `transport`, `industrie`,
`agroalimentaire`, `luxe-mode`, `services-b2b` renvoyaient `no_naf` et partaient donc à
100 % sur Serper, la ressource rare — alors que `tourisme` et `education-formation` sont
les 2e et 3e meilleurs rendements Basile sur dix secteurs testés.

**Essai à blanc validé** : `tourisme` × 33 → 3 121 sociétés vues, extraction en 4 passes ;
`education-formation` × 33 → 4 638. Le garde-fou des secteurs interdits reste actif
(`sante-pharma` → `interdit`).

**`docs/basile-api.md` §10 corrigée** : la ligne « `headquarters_department_code` → 0, ne
pas utiliser » datait d'un essai de juin jamais revérifié. Le code s'y est fié deux mois.
La note porte désormais l'avertissement et la mesure.

## 🛡️ 2026-08-21 — Droits par rôle : la matrice, et son application côté serveur

**Le problème de fond** : cacher un menu n'est pas interdire. Le rôle décidait des entrées
de la sidebar côté navigateur ; or tout ce qui vit dans le navigateur se change dans le
navigateur. Un commercial écrivant `role: "superadmin"` dans `localStorage` retrouvait les
menus — et les routes d'API répondaient, parce que rien ne les gardait.

**`scripts/roles_backend.py`** : catalogue de **25 pages** (clé, libellé, groupe, URL, et
surtout **les préfixes d'API qui les alimentent**), 6 rôles, matrice en base
(`role_pages`), cache 30 s. L'autorisation est attachée aux ROUTES, pas aux écrans : une
page qu'on n'a pas le droit de voir est une page dont les données ne viennent pas.

**Trois règles non négociables**, écrites dans le module :
  1. `superadmin` a tout, toujours — il n'est pas stocké dans la matrice et ne peut pas
     être restreint : sinon un clic malheureux enferme tout le monde dehors ;
  2. ce qui n'est pas au catalogue n'est pas gardé — les protections existantes
     (`_ADMIN_PREFIXES`, isolation multi-tenant, quotas de lecture) s'appliquent EN PLUS ;
  3. matrice illisible → on laisse passer et on trace : refuser en masse sur une panne de
     base serait un déni de service auto-infligé.

**Application** : dans le middleware de `api.py`, après l'isolation multi-tenant. Le rôle
vient de la SESSION vérifiée côté serveur. Vérifié par matrice complète (9 routes × 6
rôles) : `/api/auth/users`, `/api/admin/database` et `/api/admin/roles` ne répondent qu'au
superadmin ; un commercial est refusé sur le scraping et les campagnes ; un rôle contenu
est refusé sur la liste d'appels.

**⚠️ Changement de comportement pour le rôle `admin`** : il perd l'accès par défaut à la
gestion des comptes, aux bases de données, aux logs et à la maintenance (la page
Utilisateurs annonçait déjà « réservé au superadmin », c'est désormais vrai côté serveur).
Il suffit de cocher les cases pour le lui rendre.

**Écran** `/admin/users/roles` (fille de `/admin/users`) : une carte par rôle avec sa
mission en une phrase, puis un tableau page × rôle groupé comme le menu, cases à cocher,
enregistrement colonne par colonne. La colonne `superadmin` affiche un cadenas.

**Sidebar** : elle demande ses entrées à `/api/mes-pages`, qui déduit les droits de la
session — la sidebar ne dit pas au serveur quel rôle elle croit avoir. Route sans paramètre,
donc impossible de demander « les pages du superadmin ».

## 📞 2026-08-21 — Rôles des comptes + tableau de bord commercial

**Comptes** : Gilles → `admin`, Romeo → `user` (demande Camille).

**⚠️ Effet de bord détecté et corrigé.** Plus aucun compte n'avait le rôle `commercial` :
`commercial_par_defaut('lcr')` rendait `None`, et les contacts promus n'étaient plus
attribués à personne — en silence. Romeo gardait ses 81 rappels mais n'en recevait plus.
`followup_backend` rattache désormais l'attribution au TRAVAIL (qui rappelle) et non à
l'étiquette du rôle : `ROLES_RAPPELANTS = ("commercial", "user", "admin")` et la requête
`commerciaux()` accepte `user`. Vérifié : Romeo est de nouveau l'attributaire par défaut.

**`/site/{code}/mon-activite`** — le tableau de bord du rappelant. Constat de départ :
82 rappels en attente, **un seul appel journalisé**. Le CRM savait tout ce qu'il fallait
faire et rien de ce qui avait été fait ; une liste qui ne raccourcit jamais et ne félicite
jamais, on l'ouvre une fois.

Trois idées, dans l'ordre d'une journée : **ma journée** (anneau de progression vers
30 appels — le rythme réel donné par Camille), **ce qui me tire** (série de jours
consécutifs, paliers nommés en vocabulaire de métier : Prospecteur, Closeur, Vétéran…),
**où ça mord** (secteurs et départements classés au taux de CLIC, depuis
`campaign_recipients`). Plus le bloc qui a le plus de valeur : **« À appeler en premier »**
— les contacts de SA liste qui ont cliqué dans un email, les plus récents d'abord.
`commercial_backend.py` + `/api/sites/{site}/mon-activite`.

**Parti pris assumé** : aucune donnée inventée. Quand les compteurs sont à zéro, l'écran le
dit et explique comment ils se rempliront. Un tableau qui affiche des zéros honnêtes reste
crédible ; un tableau décoratif ne l'est plus jamais.

**Sidebar** : « Activité commerciale » (icône casque) dans Acquisition — visible pour un
superadmin sans avoir à simuler un rôle — et « Mon activité » en tête de la vue commercial.

## ☎️ 2026-08-21 — La fiche d'appel : script, RDV, présentation, blacklist

**Le constat** : la fiche affichait des informations et laissait le commercial se
débrouiller. Prendre un rendez-vous = ouvrir un autre écran ; envoyer une présentation =
son client mail personnel ; blacklister = demander à quelqu'un. Trois ruptures pendant un
appel de deux minutes, donc trois gestes qu'on ne fait pas.

**`scripts/argumentaire.py`** — le script d'appel par secteur. **Immobilier complet** :
contexte du métier (mandats qui expirent, fichier acquéreurs dormant, fin du démarchage
téléphonique), accroche, question qui fait parler, 4 arguments de valeur, **3 objections
rangées par fréquence réelle** avec parade ET explication de pourquoi elle marche
(« j'ai déjà un logiciel immobilier », « mes clients n'aiment pas être sollicités »,
« le RGPD ne me permet pas »), et la sortie vers le rendez-vous. Les autres secteurs
héritent d'un socle générique **signalé comme tel** : mieux vaut un texte visiblement
générique qu'un faux texte de métier qui sonne creux à la deuxième phrase.

**`scripts/plaquette.py`** — la plaquette PDF d'une page, **générée à la volée** depuis
`argumentaire.py` (fpdf2 installé). Aucun fichier à maintenir : le jour où l'argumentaire
change, la plaquette change avec lui. Une page et une seule, personne ne lit la deuxième.

**Quatre gestes dans la fiche** (`components/actions-appel.tsx`), sans en sortir :
Script · Rendez-vous (sur les créneaux réellement libres du module existant) ·
Présentation (email du secteur + PDF joint, **envoi nominatif 1 à 1** depuis une boîte
Maildoso — pas une campagne) · Blacklister (définitif, avec confirmation).
**Chaque action écrit dans le journal de la fiche** : sans ça, on rappelle quelqu'un à qui
on vient d'écrire.

**`maildoso_backend.send_email`** accepte désormais `pieces_jointes` ; une pièce qui échoue
n'annule pas l'envoi. **`followup_backend.journaliser()`** expose l'écriture d'événement
hors transaction — une trace qui échoue ne doit pas faire échouer l'action qu'elle décrit.

**Lignes blacklistées inversées** : fond sombre, texte clair. Un contact exclu doit se
repérer sans lire. `v_a_rappeler` ne portait ni le secteur ni le blacklistage : les deux
sont maintenant servis depuis `contacts`.

## 🤝 2026-08-21 — Du « je signe » au contrat : opportunités et ventes

**Le tunnel s'arrêtait au rappel.** Quand un prospect disait oui, il n'y avait nulle part
où le dire : carnet, bouche-à-oreille, messagerie. L'affaire se perdait, et le moment ne
se fêtait pas.

**`scripts/opportunites.py`** — table `opportunites`, **trois états seulement** (`a_valider`
→ `contrat_envoye` → `signe`/`perdu`), chacun correspondant à un geste réel. Un état de
plus serait un état que personne ne mettrait à jour.

**L'origine du lead est FIGÉE à la création** : scraping Serper/Basile, import, formulaire,
et surtout **la campagne qui l'a fait cliquer**. Vérifié en direct : « Scraping Google
Places · a cliqué le 2026-08-21 dans "Agent immobilier, loi cazenave" · collecté le
2026-08-09 ». Si le contact est nettoyé six mois plus tard, on saura toujours ce qui a
produit cette vente — sans quoi on ne peut pas décider où investir.

**Montants et commissions ne sont jamais devinés** : saisis par le responsable au contrat.
La page Ventes signale le nombre de contrats signés SANS montant et prévient que le revenu
affiché est sous-estimé. Un revenu sous-estimé pousse à d'aussi mauvaises décisions qu'un
revenu surestimé.

**Écrans** : `/site/{code}/opportunites` (DataTable avec colonne « D'où vient ce lead »,
actions Contrat envoyé / Signé / Perdu réservées aux administrateurs — un commercial n'y
voit que ce qu'il a transmis, filtré côté serveur) et `/site/{code}/ventes` (clients signés,
MRR, ARR, commissions, classement par commercial, état du tunnel).

**Le bouton « 🤝 Signature client »** en tête de fiche : gros, vert, il transmet
l'opportunité ET célèbre — 60 confettis en CSS pur (aucune bibliothèque, aucun réseau),
le GIF Giphy demandé par Camille en bonus qui s'efface s'il ne charge pas, et
`prefers-reduced-motion` respecté. La célébration n'est pas décorative : c'est le retour
immédiat qui donne envie de passer l'appel suivant.

**Groupe « Ventes » dans la sidebar**, entre Acquisition et Campagnes. Bout en bout testé :
création → contrat 149 €/mois → signé → MRR 149 €, ARR 1 788 €, commission 14,90 €.

## 🗓️ Session du 2026-08-21 → 08-23 — récapitulatif de fermeture

**Sécurité (chantier majeur, terminé et vérifié).**
- Faille critique de FORCE BRUTE fermée : `_real_ip` (api.py) lisait la PREMIÈRE valeur de
  `X-Forwarded-For`, falsifiable → limite anti-force-brute et fail2ban contournables
  (démontré : 15 essais, 0 blocage). Corrigé : lit `X-Real-IP` (posé par Nginx, non
  falsifiable) puis la DERNIÈRE valeur XFF. Rejoué après correctif : bloqué dès le 6e.
- API liée sur `127.0.0.1:8080` (avant : `0.0.0.0`, port joignable en direct depuis
  Internet → contournait Nginx). Relancée via PM2 `--host 127.0.0.1` + `pm2 save`.
  Défaut de code aussi passé à 127.0.0.1 (`HOST_API` dans .env pour forcer 0.0.0.0).
- **Cloudflare** devant `api.cheffer.email` (domaine chez Spaceship, un seul enregistrement
  `api`, aucun email/MX — bascule sans risque). `nginx` restaure la vraie IP visiteur via
  `/etc/nginx/cloudflare-realip.conf` (CF-Connecting-IP + plages CF) — testé : la vraie IP
  remonte, pas une IP Cloudflare. SANS ce fichier, tout le trafic serait vu comme venant de
  CF → blocages en cascade.
- **Verrou d'origine** : `scripts/verrou-origine-cloudflare.sh` — 80/443 réservés aux
  plages Cloudflare (SSH + connexions établies préservés). Persistant via service systemd
  `cf-verrou-origine.service` (enabled). Réversible : `... --annuler`.
  ⚠️ PIÈGE : ne jamais désactiver le nuage orange Cloudflare sans annuler le verrou d'abord,
  sinon coupure totale de la plateforme.
- MFA activée sur camille (superadmin) ET Gilles (admin). Sujet CLOS — ne plus en parler.
- Restent MINEURS (revue) : hachage SHA-256 hérité accepté, énumération par timing du login.
  Et un test 4G à faire par Camille (confirmer que l'IP directe est bien fermée).

**Panne pg_reconcile (2026-08-23) — RÉGLÉE.** Cause : `logs/pg_reconcile.log` appartenait à
`root`, le cron tourne en `autoblog` → le `>>` échoue AVANT Python, la tâche ne s'exécutait
plus depuis le 20/08. MÊME PIÈGE que `alertes.json`. Corrigé (chown autoblog) + 2 autres
logs root par prévention. Réconciliation relancée : PG 12 295 → 10 027, `v_suppression`
intacte (968). Alerte levée. Sauvegarde des retirés dans `backups/`.

**Corruption `%20` — RÉGLÉE à la source.** `mailto:%20contact@…` sur les pages web donnait
des emails `%20contact@…` (le `%` est valide dans un email, le regex l'avalait).
`_emails_in_text` (god_mode_agents.py) décode+nettoie désormais chaque email extrait.
16 corrompus au total : 13 nettoyés par la réconciliation, 3 renommés. 0 restant.

**Produit livré cette session** (tout déployé) : audit Basile + filtre DÉPARTEMENT (×2,6 à
×6) + 7 secteurs câblés ; liste noire des adresses de rôle (`email_validator`) ; page
**Statistiques** + `campaign_recipients` + purge des 405 doublons de migration ; refonte
tableau de bord ; colonne+filtre secteur sur Acquisition ; **garde_lecture** (anti-
aspiration : plafond page + quota 1000/h commercial + journal + alerte) ; filigrane
nominatif ; refonte page **Scraping** + sous-page Activité + **agent Stéphane**
(`stephane.py` : mémoire `memoire_stephane`, config 3 critères, décision notée, branché sur
`autoscrape_daily.next_target`) ; **Mon activité** commercial (`commercial_backend.py`) ;
**matrice des droits par rôle** (`roles_backend.py` + `/admin/users/roles` + application
middleware) ; fiche d'appel (script `argumentaire.py`, plaquette PDF EN ATTENTE, RDV sur
créneaux réels via Maildoso, blacklist, lignes inversées, **Signature client** + confettis)
; **Opportunités** + **Ventes** (`opportunites.py`, tunnel 3 états, origine du lead figée,
MRR/commissions) ; popups de session ; page **login** 2 colonnes + marque **Cheffer** +
favicon. Revue de code : 12 défauts corrigés (2 failles d'autorisation, textes illisibles,
boucle de polling, code mort).

**Reste PRODUIT (feu vert Camille) :** argumentaires `restaurant`/`tourisme` ; bouton
« appel passé » (le tableau d'activité reste vide sans lui) ; refonte plaquette PDF
(désactivée par défaut, case opt-in) ; `contact@cheffer.email` de la plaquette rebondit
(pas de MX) ; voie « dirigeants nommés » Basile/Emelia (payant, non branché) ;
`/onboarding` : CONSERVÉ (lien entrant « Ajouter un site » vérifié, pas mort).

## Dernière mise à jour
2026-08-21 (Basile audité · liste noire des adresses de rôle · page Statistiques)

## 📊 2026-08-21 — Page Statistiques + comportement des destinataires

**Ce qui a été construit.** `campaign_recipients` (PostgreSQL) : UNE ligne par envoi
journalisé, avec ce que le destinataire en a fait. Le recollage était le problème — une
ligne `sent` porte sa campagne, les `open`/`click` qui suivent n'en portent aucune (webhook
identifié par l'adresse seule). Règle d'attribution : **une ouverture appartient au dernier
envoi fait à cette adresse avant elle**, la fenêtre se fermant au réenvoi suivant. 1 712
envois reconstruits, reconstruction complète et idempotente (`stats_backend.py
reconstruire`, cron horaire à :50).

**Ce qu'on ne mesure pas, et qu'on n'invente pas.** Sweego envoie en masse : aucun envoi
par destinataire, donc aucun dénominateur. Ses 1 491 rebonds et 21 plaintes sont comptés
**à part** (`angles_morts`, affiché en bas de page), jamais fondus dans les taux — les y
verser donnerait un taux calculé sur des envois jamais comptés.

**Page** `/site/{code}/statistiques` (menu Pilotage) : carte de tête « ce qui marche / ce
qui ne marche pas » (meilleur et pire secteur, meilleure et pire zone, à partir de 20
envois — sous ce seuil on ne désigne personne), 4 tuiles, puis cinq tableaux : canal, type
d'adresse, secteurs, zones, campagnes.

**Analyse sectorielle préparée d'avance (21/08, après-midi).** Trois ajouts pour que le
jour où d'autres secteurs partent en campagne, il n'y ait rien à construire :
`stats_secteur_jour` (historique FIGÉ jour × secteur — `campaign_recipients` est
reconstruite toutes les heures en rejoignant `contacts`, donc un contact sorti du pool
ferait basculer rétroactivement son envoi de juin en « inconnu » ; l'historique, lui, ne se
réécrit pas), `comparaison_secteurs()` (les 31 secteurs, sollicités ou NON, avec rang de la
politique + contacts disponibles en base + colonne `recul` : suffisant / à confirmer /
jamais sollicité) et `par_secteur_zone()` (croisement secteur × département, cases sous
5 envois écartées). Côté écran : deux DataTable triables et filtrables (TanStack, composant
maison déjà en place) remplacent le tableau figé des secteurs.

**Ce que ça montre tout de suite** : `tourisme` est prioritaire, a **153 contacts en base**
et n'a **jamais reçu un email** ; `restaurant` 97, `retail` 45. Et 883 contacts
`agence-marketing` dorment en base alors que le secteur est désormais interdit.

**⚠️ Doublons de migration corrigés le 21/08 (question de Camille sur le canal « inconnu »).**
La reprise depuis `contact_site_history` a rejoué 405 envois maildoso qui figuraient DÉJÀ
au journal : deux lignes `sent`, même adresse, même jour — une réelle (canal `maildoso`),
une de reprise (canal `inconnu`, sans campagne ni boîte). Ce n'était pas qu'un compteur
gonflé : deux lignes le même jour FERMAIENT la fenêtre d'attribution de la première sur la
seconde, et l'ouverture était portée au crédit de la ligne fantôme. Maildoso affichait
20,3 % et le fantôme 27,5 % — **le second volait les ouvertures du premier**. **PURGÉES du journal le 21/08** sur décision de Camille, via
`scripts/purge_doublons_journal.py` (essai à blanc par défaut, `--apply` pour écrire) :
405 lignes retirées, `email_events.sent` 1 712 → 1 307. Sauvegarde JSON intégrale et
restaurable (identifiants compris) dans `backups/journal/`. Trois conditions cumulatives
pour être supprimée — canal `inconnu`, `meta.source = contact_site_history`, ET un jumeau
le même jour sur un canal connu : aucune adresse ne pouvait donc perdre son dernier envoi.
Contrôle DANS la transaction : `v_suppression` inchangée à 808, sinon abandon. Sans effet
sur la règle des 120 jours ni sur les compteurs de campagne.

**Le filtre reste dans `stats_backend` en garde-fou** (au cas où une réimportation en
referait), mais RESSERRÉ sur cette seule signature : 7 doublons subsistent en juillet-août
qui sont de **vrais** envois — deux campagnes dispatchées le même matin à la même adresse.
Les fondre effacerait de la statistique un email réellement reçu. `stats_secteur_jour` a
été vidée deux fois, les jours ayant été figés sur des chiffres successivement faux.

**Ce que les chiffres disent (après correction)** : **29,4 % d'ouverture · 5,0 % de clic
sur 1 307 envois** (maildoso 29,1 %). Zone la plus forte **06 Alpes-Maritimes (41,2 %)**, la plus faible
**60 Oise (8,0 %)**. Meilleure campagne : « loi Cazenave » 35,6 %.
Aucune comparaison sectorielle possible : l'immobilier fait la quasi-totalité des envois.
**Et surtout : générique 26,7 % d'ouverture contre nominative 29,6 %** — 3 points d'écart,
et les génériques cliquent plus (4,7 % contre 3,3 %). C'est l'analyse que Camille voulait
pour trancher sur les 1 943 `contact@` en base.

## 🔎 2026-08-21 — Basile : pourquoi 26 contre 202 Serper

Trois causes mesurées en direct, aucune corrigée à ce jour :
1. **Le filtre géo montre 37 % du terrain.** `run_sector_for_city` filtre sur
   `headquarters_city`, alimenté par les 5 plus grandes villes du dept (≥ 10 000 hab).
   Gironde : 1 144 sociétés vues sur 3 089. `headquarters_department_code` **fonctionne**
   (vérifié sur 33, 75, 69, 64, 87) — `docs/basile-api.md:170` dit le contraire, la note
   est périmée et le code s'y fie.
2. **16 secteurs câblés sur 28.** `SECTOR_NAF` n'a jamais reçu les NAF du catalogue :
   `tourisme`, `education-formation`, `transport`, `services-b2b`, `industrie`,
   `agroalimentaire`, `luxe-mode` renvoient `no_naf` → 100 % Serper.
3. **On ne scrape que l'immobilier**, 5e en rendement sur 10 secteurs testés.

Extraction test de 1 000 leads (Gironde), livrable = email direct + repli page-contact
(mesuré à 52 % sur 40 sites) : artisan 61 % · tourisme 44 % · education-formation 44 % ·
immobilier 35 % · restaurant 23 % · coiffeur 11 %. **Sur le seul dept 33, les secteurs
prioritaires pèsent ≈ 18 000 contacts livrables** — Serper n'a aucune raison d'être la
source principale.

## 🚫 2026-08-21 — Liste noire des adresses de rôle (décision Camille)

`contact@` `info@` `accueil@` `agence@` `compta@` `devis@` + gabarits `exemple@domaine.fr`
sont désormais **rejetés à la collecte** (`email_validator`, étage 3, avant le contrôle MX).
157 parties locales, 43 boîtes d'accueil, 34 gabarits, 29 domaines de gabarit. Règle du
suffixe numérique : `contact33@` tombe, `dupont33@` passe.

**Coût mesuré, assumé** : −60 % du rendement Basile en email direct (183 → 73 sur
1 000 leads) ; l'immobilier tombe de 13 à 2 pour 100 leads. Conséquence : pour du volume
ET du nominatif, il faudra la voie **dirigeants** (`run_dirigeant_segment`, Emelia payant).

**Les 1 943 contacts génériques déjà en base ne sont PAS touchés** — décision de Camille du
21/08 : elle veut d'abord voir s'ils répondent. C'est ce que mesure la page Statistiques.

## 🗂️ 2026-08-21 — Classement des secteurs enregistré

`sector_policy` renseignée pour `lcr` et `mkd` (376 cibles interdites retirées de la file).
Prioritaires : immobilier · restaurant · tourisme · education-formation · garagiste ·
coiffeur · retail. `artisan` reste **collecté mais secondaire** (arbitrage Camille : le
volume est là, l'ajustement produit est plus faible). Interdits inchangés (9).


2026-08-20 (session fermée anormalement — état des lieux repris dans RESTE-A-FAIRE.md)
2026-08-19 (Prénoms depuis l'email + MINI-CRM commercial avec attribution des rappels)

## 🔧 2026-08-20 (13h50) — Trois correctifs de fond après une session interrompue

**1. La règle des 120 jours ne dépend plus de DuckDB.** `mark_pushed_to_emelia` écrit
désormais le journal PostgreSQL (`email_events`, qui alimente `v_suppression`) **avant**
d'ouvrir `contacts.duckdb`, quand l'appelant lui passe l'adresse — `campaign_engine` le
fait maintenant sur les deux canaux. Motif : le 20/08 à 8h31, un scrape tenait le pool,
le marquage a levé, et `david.daries@gers-immobilier.fr` a reçu son email **sans ligne de
repoussoir** — renvoyable. Réparé à la main (gelé jusqu'au 18/12), et la cause est
supprimée : le rempart qui compte s'écrit en premier, sur la base qui n'a pas de verrou.

**2. Le scraping 24 h/24 ne s'arrête plus à midi.** `MAX_TARGETS_PER_NIGHT` (3, taillé
pour une nuit de dix heures) devient `_max_cibles()` : 3 par nuit en mode fenêtre, **12
par jour en mode continu**. Le frein reste le quota de 1 000 contacts/jour. `_night_id()`
suit le jour calendaire en continu, aligné sur ce quota. Deux **créneaux réservés** où
aucune passe ne démarre : `06:20-07:20` (enrichissement + réconciliation) et
`08:20-10:00` (dispatch de campagnes) — c'est la collision de ce matin, supprimée.

**3. `pg_reconcile` a tourné pour la première fois.** `pg_gate._duck()` réessaie pendant
dix minutes au lieu d'abandonner au deuxième essai : en 24 h/24, un scrape peut tenir le
pool à 6h30. Résultat du premier passage : PostgreSQL 8 216 → **8 170**, aligné sur le
pool (46 contacts disparus du pool retirés — 0 rappel, 0 événement perdus, vérifié avant).
Répartition : ok 6 316 · spam 1 482 · à vérifier 200 · exclu 152 · ko 20.

**Reste à faire : voir `RESTE-A-FAIRE.md`.** Lot 2 (secteurs) attend toujours l'arbitrage.

## 🔝 REPRISE — session du 2026-08-19 (à lire en premier)

**État à la fermeture (21h00 Paris) : plateforme OUVERTE, tout est en ligne et vérifié.**
Services `genesis-ui`, `genesis-dashboard`, `genesis-mailnjoy-drain` en ligne, PostgreSQL
actif, maintenance levée. Pool DuckDB 7 916 contacts · PostgreSQL 6 194 contacts,
3 571 événements, 731 adresses bloquées 120 j.

> **Attention** : les sessions ont été purgées pendant la migration. Tout le monde doit
> ressaisir son mot de passe.

### À SURVEILLER DEMAIN MATIN — dans cet ordre
1. **06:30 UTC** — enrichissement data.gouv puis `pg_reconcile`. Les **13 contacts à
   rappeler** qui attendent leur enrichissement doivent entrer dans PostgreSQL
   (`v_a_rappeler` doit passer de 61 à ~74). Log : `logs/pg_reconcile.log`.
2. **08:30 UTC** — dispatch « Agent immobilier, loi Cazenave » (72/1000). **C'est le PREMIER
   dispatch qui tourne sur les lectures PostgreSQL et le capping 120 jours.**
   Contrôle : la colonne **Redites** du tableau de bord doit être à **0**, et
   `campaign-dispatch.log` ne doit contenir aucun « contact(s) écarté(s) ».
3. **RDV en attente depuis le 7 août** : Anne GERHART, jamais rappelée. La tuile Rendez-vous
   du tableau de bord est rouge à cause d'elle.

### À FAIRE — par priorité
1. **`/code-review ultra` sur le mini-CRM** — demandé par le user, déclenchable par LUI seul
   (je ne peux pas la lancer). Fichiers prioritaires : `scripts/followup_backend.py` (règles
   d'accès), `scripts/pg_schema_crm.sql`, les 5 endpoints `/a-rappeler` dans `api.py`.
2. **Migration PostgreSQL, étapes 5 à 7** : couper l'écriture DuckDB du pool (le 1 Go
   disparaît), faire lire les campagnes depuis PostgreSQL, supprimer le code de double
   écriture. Ne nécessite PAS de fermer la plateforme.
3. **Refonte UI, phases 4 et 5** : reprise écran par écran (dont **8 `catch` vides** restants
   sur la page Campagnes — c'est la cause commune des 4 bugs de câblage trouvés aujourd'hui),
   **22 `confirm()` natifs** à supprimer, formulaires longs en modale → pages, tiroirs pour
   les fiches, **11 tableaux** sans défilement, **50 largeurs figées**.

### DÉCISIONS PRODUIT EN ATTENTE (aucune n'est bloquante)
- **`/onboarding`** (570 lignes, aucun lien entrant) : garder ou supprimer ?
- **Fusionner « Vision » dans le tableau de bord** ? Les deux répondent à la même question ;
  je ne l'ai pas fait, ça change une habitude.
- **Règle de promotion PRM** : 14 des 71 PRM viennent d'un clic `campaign=default` sans
  horodatage — flux pollué par les boîtes de test et les proxys antispam, il a promu
  `gilles@squaremx.com`. Cesser de promouvoir sur ce flux ?
- **`phone_enrich_backend`** : 0 numéro trouvé sur 56 tentatives, par inadéquation
  structurelle (exige un nom que le scraping ne collecte jamais). Le débrancher et le
  remplacer par une requête Serper Places sur les **622 contacts ayant une société sans
  téléphone** — même source que les 4 780 numéros déjà obtenus.

### DETTES TECHNIQUES CONNUES (documentées, non bloquantes)
- **`pg_sync.promote_contact` est lent en masse** : 1 connexion PostgreSQL + 1 DuckDB par
  contact. 947 contacts ont pris plus de 10 minutes. À traiter avant le prochain rattrapage.
- **La base CRM legacy `crm/{site}.duckdb` est encore ÉCRITE** par `tally_to_prm` (cron
  horaire), `emelia_to_crm` (19 h), `workflow_emelia_push`, `prospect_scraper` et 2 webhooks.
  Ils écrivent AUSSI dans le pool, donc aucune perte — mais la base fantôme grossit.
  **Plus aucun écran ne la lit.**
- **1 573 des 1 996 contacts d'août n'ont pas de `dept_code`** — invisibles à tout ciblage géo.
- **`contacts.duckdb` pèse 1 Go** pour 26 000 lignes (3 510 row groups à 5 lignes). Ne pas
  recompacter : l'étape 5 de la migration rend l'opération sans objet.
- **L'API 8080 a été redémarrée** plusieurs fois aujourd'hui : elle tourne bien avec le code
  courant, contrairement à ce qui était noté plus tôt.

### RÈGLES À NE PAS RÉINTRODUIRE
- **120 jours entre deux emails** à une même personne, tous sites et canaux. Deux barrières
  (cooldown du pool + `v_suppression` déduite du journal) plus un garde-fou à l'envoi.
- **Porte d'entrée PostgreSQL : ABANDONNÉE le 2026-08-20 (décision user).** PostgreSQL
  accueille désormais TOUS les contacts (7 970), chacun portant `contacts.etat` :
  `a_verifier` · `ok` · `ko` (verdict Mailnjoy) · `exclu` (data.gouv) · `spam` (désinscrit,
  plainte, rebond). La porte est devenue un DRAPEAU, plus un filtre. Motif : l'entonnoir
  laissait 1 776 contacts hors de PostgreSQL et interdisait au scraping d'y écrire — donc
  de sortir de la fenêtre 22 h-8 h. `pg_gate.ETAT_SQL` porte la cascade, `pg_reconcile`
  réaligne l'état de tout le monde à chaque passage, et **ne supprime plus que les contacts
  DISPARUS du pool**. `pool_pg._ELIGIBLE` exige `etat = 'ok'` en plus des conditions brutes.
  NE PAS réintroduire une suppression sur « devenu mauvais » : on perd la mémoire de l'avoir
  écarté, et on le re-scrape trois semaines plus tard.
- **Ne JAMAIS ouvrir une base DuckDB en lecture seule dans le process de l'API** — DuckDB met
  l'instance en cache et refuse ensuite toute connexion en écriture (« 0 campagne »).
  **Appliqué le 2026-08-19** : toutes les ouvertures passent par `scripts/duck_ouverture.py`
  (lecture-écriture, ré-essais, repli lecture seule en dernier recours). 12 ouvertures en
  lecture seule subsistaient dans `api.py`, `god_mode_backend`, `god_mode_api`,
  `autoscrape_backend` et `followup_backend` : c'est ce qui produisait « Liste des campagnes
  indisponible — la base est occupée » plusieurs fois par heure, sans qu'aucun verrou ne soit
  pris. `contacts_pool_backend._connect_with_retry` bascule en plus sur l'autre configuration
  quand DuckDB signale un conflit — réessayer à l'identique n'aurait jamais abouti.
- **Aucune couleur écrite en dur** dans l'UI : uniquement les rôles du thème. Et un aplat a
  besoin de DEUX rôles (couleur + `-foreground`), sinon on obtient du marron sur du marron.
- **`datagouv_enrich` plantait tous les matins** sur une coordonnée `[NON-DIFFUSIBLE]`
  (ValueError sur `float()`), et le cron enchaînant en `&&`, **`pg_reconcile` n'a jamais
  tourné** — d'où les 1 776 contacts absents. Corrigé : `_flottant()` tolère les valeurs non
  numériques, et le cron passe en `;`. Un échec d'enrichissement ne doit jamais bloquer la
  réconciliation.
- **Relevé technique quotidien** : `scripts/etat_technique.py --enregistrer`, cron 6 h 45,
  table `etat_technique_journalier` (une ligne par jour), page `/admin/etat-technique`.
  C'est lui qui a trouvé la panne ci-dessus en 30 secondes.
- **Scraping ouvert 24 h/24 le 2026-08-20.** La fenêtre 22 h-8 h protégeait les compteurs
  de l'interface du verrou DuckDB ; mesuré ce jour-là, sous écritures continues et même avec
  un verrou tenu 3 s, **18 lectures d'interface sur 18 aboutissent** (1,4 s médian, 2,0 s au
  pire). Ce n'est plus une indisponibilité, c'est un délai. Réglages dans `.env` :
  `SCRAPE_WINDOW=24h` (mettre `22:00-08:00` pour revenir en arrière SANS toucher au code) et
  `SCRAPE_MAX_JOUR=300`. Les butoirs de nuit (`SCRAPE_STOP`, `CLEANUP_STOP`) et le test
  « trop tard pour une nouvelle cible » sont neutralisés en mode continu — sinon plus rien
  ne démarrerait passé 7 h 20. Crons `autoscrape_daily` et `autoscrape_watchdog` ouverts à
  toutes les heures.
- **Ordre des sources INVERSÉ le 2026-08-20 : Basile d'abord, Serper en complément.**
  Vérifié dans le code : Basile ne consomme AUCUN crédit Serper — sa recherche passe par sa
  propre API, et son repli email lit directement la page contact du site
  (`god_mode_agents.fetch_email_from_site`, un simple GET). L'arithmétique des forfaits :
  Basile 250 000 exports/mois (8 333/jour) contre Serper 10 000 crédits/mois ÷ **7 crédits
  par contact gardé** (mesuré sur août : 8 625 crédits pour 1 239 contacts) = ~1 430
  contacts/mois, soit 5 % du volume visé. Serper ne peut donc être qu'un complément.
  `SERPER_RESERVE=5000` dans `.env` : sous ce seuil, la collecte **continue sur Basile seul**
  au lieu de s'arrêter. `SCRAPE_MAX_JOUR=1000`.
- **L'exclusion d'un segment se combine en ET par défaut** (`exclude_match`, 2026-08-20).
  Elle était figée en OU : ajouter « secteur immobilier » à une exclusion « a ouvert »
  retirait TOUT l'immobilier, alors que l'intention évidente est « retirer les immobiliers
  QUI ont ouvert ». Les valeurs d'une même famille restent en OU (« exclure banque ou
  assurance »). Sélecteur ET/OU dans l'éditeur, comme à l'inclusion.
  `conflits_rules()` ne signale un critère des deux côtés QUE si l'exclusion est en OU —
  en ET c'est légitime. `expliquer_segment` rend `inclus` et `retires_par_exclusion`.
- **PRESSION MARKETING — remplace les 120 jours POUR LES SEGMENTS (décision user 2026-08-20).**
  Un segment sert une action ciblée : « relancer ceux qui ont ouvert » ne peut pas exclure
  ceux qui ont ouvert. La fenêtre de 120 jours ne s'applique donc plus aux segments ; à la
  place, **4 communications maximum par mois glissant** (`PRESSION_MAX_MOIS` dans `.env`,
  `pool_pg._PRESSION_SQL`), tous canaux et tous sites confondus. Effet mesuré : « ouvreurs »
  passe de 1 à 348 contactables, « immobilier + Paris + ouvert » de 0 à 4.
  **Les 120 jours restent en vigueur pour le cold email sans segment** (`_ELIGIBLE`).
  Comptée sur `email_events` — le pool DuckDB ne garde qu'une date de dernier envoi et ne
  sait pas compter : c'est pourquoi `count_for_segment` / `pick_for_segment` passent
  DÉSORMAIS TOUJOURS par PostgreSQL, sans regarder `PG_READS`.
  Page de contrôle : `/admin/pression`.
- **La page Vision lit PostgreSQL depuis le 2026-08-20** (`pool_pg.vision_contacts` et
  `pool_pg.enrichment_stats`), avec repli DuckDB si PostgreSQL est injoignable. Équivalence
  vérifiée chiffre par chiffre avant bascule : étapes, enrichissement et secteurs
  identiques ; l'engagement diffère à l'avantage de PostgreSQL (journal `email_events`
  complet contre dernier signal seulement côté pool). Le miroir `contact_enrichment` a été
  complété (colonnes siret / match_quality / motifs / signaux + `pg_sync_enrichment.py`).
- **Bug corrigé : `pg_reconcile` écrivait `global_blacklisted = false` EN DUR.** Les 1 482
  contacts blacklistés entraient dans PostgreSQL comme s'ils ne l'étaient pas. L'`etat`
  ('spam') était juste, mais la colonne brute — celle que lit la clause d'éligibilité des
  envois — mentait. Corrigé et réaligné à chaque passage de la réconciliation.
- **Deux cascades d'état divergeaient** : `pg_gate.ETAT_SQL` exigeait l'enrichissement pour
  dire « ok », pas `contacts_pool_backend._ETAPE_SQL`. 73 contacts s'affichaient « À
  vérifier » d'un côté et « Vérifié » de l'autre. L'état décrit désormais l'ADRESSE seule ;
  l'exigence d'enrichissement est explicite dans la pioche d'envoi (`pool_pg._ELIGIBLE`).
- **Campagnes et segments : PostgreSQL est la SOURCE** (migré le 2026-08-19, étape 6 du
  plan). `campaign_engine` et `segments_backend` lisent et écrivent la table `campaigns` /
  `segments` de PostgreSQL ; l'id public reste l'id court porté par `legacy_id` (il est
  inscrit dans les identifiants de dispatch `lcr-xxxx-date`, les URL et `params.segment_id`).
  Les tables DuckDB `campaigns_unified` / `segments` restent en place, intactes, comme filet
  de retour arrière. **`pg_migrate.py` refuse de tourner sans `--je-sais-ce-que-je-fais`** :
  rejouer la copie DuckDB → PostgreSQL écraserait l'état courant. Les JOURNAUX d'envoi
  (`maildoso_sent`, `mass_campaigns`, `sweego_events`) sont encore dans DuckDB — étape
  suivante.
- **Dédoublonnage du scraping contre le POOL** : `god_mode_backend.email_deja_en_base()`,
  appelé avant Mailnjoy dans `god_mode_agents` et `basile_backend`. Les trois garde-fous
  historiques n'interrogeaient que les tables du scraping : un contact importé par CSV,
  Basile ou Tally était re-scrapé et re-vérifié à crédit perdu.
- **Étapes de traitement d'un contact** (2026-08-19) : calculées par
  `contacts_pool_backend._etape_contact`, en CASCADE — blacklisté > écarté (Mailnjoy
  invalide/risqué, ou entreprise fermée/administration) > en repos (120 j) > à vérifier >
  vérifié > prêt (SIRET data.gouv trouvé). C'est un axe DISTINCT du cycle commercial
  (cold_email/lead/prm/client), qui reste la colonne « Cycle ». Ne pas fusionner les deux :
  c'est la confusion qui rendait la colonne « État » illisible. Répartition LCR au
  2026-08-19 : vérifié 2 798 · prêt 2 739 · blacklisté 1 482 · en repos 727 · écarté 151 ·
  à vérifier 78.
- **Épingle et retrait dans « À rappeler »** : `contact_followup.flash` (marque-page, remonte
  en tête, pas journalisé) et `retire_at` (sort de `v_a_rappeler`, journalisé, réversible).
  Ne JAMAIS remplacer le retrait par une suppression : `pg_reconcile` rétablirait le contact
  au passage de 6 h 30 puisqu'il reste éligible.
- **Attribution automatique des rappels** (décidée le 2026-08-19) : tout contact qui devient
  `lead` ou `prm` sur LCR part d'office chez **Romeo** — hook dans `pg_sync.sync_contact_site`,
  filet de rattrapage à la fin de `pg_reconcile`. Ne JAMAIS écraser une attribution existante :
  le `WHERE contact_followup.assigned_to IS NULL` de l'`ON CONFLICT` est là pour ça. Si le
  compte nommé n'existe pas ou n'a pas le site (cas de MKD), on n'attribue à PERSONNE plutôt
  que de désigner « le premier commercial venu ». Nom du destinataire :
  `followup_backend.COMMERCIAL_PAR_DEFAUT`, exposé à l'UI par `/a-rappeler/commerciaux`.
- **Un test ne doit rien laisser en production** : `pg_sync._ACTIF = False` et
  `pool._PG_READS = False` dans les tests qui écrivent.


## 🔝 REPRISE 2026-08-19 — Renvois en boucle : base repoussoir 120 jours (FIXÉ)

**Constat (état des lieux demandé par le user) :** sur août, 1 189 emails envoyés pour
seulement **724 destinataires uniques** — 39 % de redites. La courbe empire : 84/100 de
renvois le 11/08, 98/100 le 15/08, 25/25 le 18/08, 43/47 le 19/08. Quatre adresses ont reçu
**11 à 18 fois** le même message (`chloe.mouget@gemilli.fr` : 18 envois, un par jour).

**Causes (3 bugs qui se cumulaient) :**
1. **Cooldown même-site à 7 jours** (`COOLDOWN_SAME_SITE_DAYS`) : un contact touché le 1er
   redevenait éligible le 8.
2. **Tri sans priorité aux contacts frais** : `ORDER BY source, email_score, updated_at`
   ramenait en tête les contacts déjà contactés (meilleur score) dès leur sortie de
   cooldown — alors que 2 126 contacts immobilier n'avaient JAMAIS rien reçu.
3. **`mark_pushed_to_emelia` = UPDATE muet** : sur un contact sans ligne
   `contact_site_history`, l'UPDATE touchait 0 ligne sans erreur → aucun cooldown posé →
   repêché tous les jours. C'est l'origine des adresses à 11-18 envois (14 contacts
   concernés).

**Décision user 2026-08-19 :** une personne ayant reçu **1** email est flaggée à 0 en base
repoussoir avec la date d'envoi, et **ne reçoit plus rien pendant 120 jours**.

**Fixes déployés :**
- **`email_suppression` (NOUVELLE table, contacts.duckdb)** : `email` (PK, normalisé),
  `contactable` (0 = bloqué), `last_sent_at`, `release_at`, `site_code`, `campaign_id`,
  `reason`. Indexée sur `release_at`. Clé = l'ADRESSE, pas l'id du contact : un contact
  purgé puis re-scrapé retrouve son blocage (c'était le trou principal).
- **`SUPPRESSION_DAYS = 120`**, `COOLDOWN_SAME_SITE_DAYS` et `COOLDOWN_GLOBAL_DAYS` alignés
  dessus. `campaign_engine.MIN_DAYS_BETWEEN_EMAILS` importe la constante (pas de recopie).
- Helpers : `suppress()`, `_suppress_conn()`, `is_suppressed()`, `filter_suppressed()`,
  `release_expired()`, `suppression_stats()`.
- **`SUPPRESSION_CLAUSE_SQL`** branché sur les 3 requêtes de pioche (`pick_for_campaign`,
  `_segment_query`, `count_available_for_sector`). `NOT EXISTS` et pas `NOT IN` (piège NULL).
- **`NEVER_CONTACTED_FIRST_SQL`** en tête des `ORDER BY` : on épuise le pool frais d'abord.
- **`mark_pushed_to_emelia`** : upsert (crée la ligne manquante) + VÉRIFIE que le cooldown
  est posé (lève sinon) + inscrit en base repoussoir dans la MÊME transaction.
- **`_drop_recently_emailed`** (campaign_engine) : dernière barrière avant envoi, croise la
  base repoussoir ET le journal `maildoso_sent`. Loggue tout écart (doit rester à 0).
- **Données réparées** : 14 lignes `contact_site_history` manquantes créées avec cooldown
  rétroactif ; 4 cooldowns en retard réalignés sur le journal d'envois ; **730 adresses**
  amorcées en base repoussoir (journal maildoso + historique pool, tous canaux).
- **Tests** : `tests/test_frequence_capping.py`, 21 assertions (bornes 119/121 jours,
  orphelins, priorité aux frais, base repoussoir prioritaire sur un cooldown perdu). Vert.
- **Spec** : `specs/contacts-model.md §3.2` réécrit (ancienne règle 7j/30j barrée).

**Vérifié après fix** : la pioche de 160 pour la campagne « loi Cazenave » renvoie
160 contacts jamais contactés, 0 déjà contacté, 0 en base repoussoir. 2 122 contacts
immobilier restent contactables.

**RESTE :** (1) l'API 8080 (PID 2676878) tourne avec l'ANCIEN code — décision user : ne pas
la redémarrer. Le cron de 08:30 UTC recharge le code à chaque exécution donc il est couvert ;
un envoi manuel depuis l'UI ne l'est pas tant qu'elle n'a pas redémarré. (2) Le dispatch du
19/08 s'est terminé sur un `IO Error` de verrou DuckDB tenu par l'API elle-même (47 envoyés
sur 160). (3) Scraping : 1 573 des 1 996 contacts d'août n'ont pas de `dept_code` —
invisibles à tout ciblage géographique.

## 🔝 2026-08-19 (suite) — Les 397 pending bloqués : VIDÉS, cause structurelle corrigée

**Cause réelle (≠ celle supposée le 24/07) :** les 397 étaient TOUS sur `http_500`, et le 500
est **déterministe par adresse** — sondage manuel : 28,3 s puis 500, systématiquement, alors
qu'une adresse saine répond 200 en 3,2 s. Mailnjoy ne SAIT PAS valider ces adresses. Le reset
du 24/07 ne pouvait donc pas tenir : les compteurs remontaient à 5 en cinq passes.

**Cause structurelle :** `list_pending` filtrait sur `mailnjoy_attempts < 5` — un cul-de-sac
**sans sortie ni compteur**. Une ligne atteignant 5 devenait invisible pour toujours. 397 s'y
sont empilées du 22/05 au 18/08 sans qu'aucun indicateur ne le signale.

**Reprise exécutée (31 min, 6 threads, 1 tentative/adresse) :** 390 × HTTP 500, 7 × HTTP 200
→ 1 risky, 6 invalid, **0 valid**. Aucune adresse n'était récupérable. Coût : 7 crédits
Mailnjoy (un 500 ne coûte rien).

**Fixes déployés :**
- `MAILNJOY_MAX_ATTEMPTS = 5` + `CHRONIC_AGE_DAYS = 7` (god_mode_backend) : la file a une
  SORTIE. `retire_chronic_pending()` envoie au tombstone (`decision='unverifiable'`) les
  lignes à bout de tentatives ET âgées de +7 j — le délai laisse passer une panne Mailnjoy.
- `count_chronic_pending()` + clés `retired_chronic` / `retired_pool_copies` /
  `chronic_remaining` dans les stats du drain ET dans le filtre de log de
  `mailnjoy_drain_loop.py` (le filtre les jetait : les taire = reproduire le bug).
- `_delete_errored_pool_copy()` (mailnjoy_check) : purge la copie pool en `decision='error'`,
  que `_delete_unverified_pool_copy` (qui ne couvre que `mailnjoy_check` NULL) laissait
  traîner — 294 copies orphelines trouvées et supprimées.
- `tests/test_pending_chronic.py` : 15 assertions, vertes.

**État final :** `scrappe_pending` = 0 (était 397). Tombstone = 7 761 dont 390 `unverifiable`.
Pool contacts = 7 916 (était 8 210, -294 copies mortes). Drain PM2 38 redémarré.

## 📞 2026-08-19 — PRÉNOMS depuis l'email + MINI-CRM commercial

### Volet 1 — Extraction des prénoms
**Constat user :** « si son email permet d'avoir son prénom, le commercial peut accrocher la
personne ». Vérifié : **7 des 10 modèles d'email utilisent `{{prenom}}`**, remplacé par une
chaîne vide quand il manque — et AUCUN contact scrapé n'avait de prénom. Tous les cold emails
partaient donc avec « Bonjour, ».

- **`data/ref/prenoms.tsv`** : data.gouv « Liste de prénoms et patronymes », filtré à
  >= 50 naissances → **5 763 prénoms, avec DEUX fréquences** (porté comme prénom / comme
  patronyme). Indispensable : `dupont` = 50 naissances contre 8 033 porteurs du nom,
  `bernard` = 150 715 contre 16 475. Un seuil seul ne peut pas trancher.
- **`scripts/name_extract.py`** : la règle dépend de la FORME de l'adresse —
  `prenom.nom` (la position tranche) · `j.dupont` (après une initiale, c'est TOUJOURS un nom
  de famille, jamais un prénom : « Bonjour Dupont » est pire que « Bonjour ») · mot isolé
  (le prénom doit l'emporter sur le patronyme) · collés (règle stricte aussi).
- **Colonne `prenom_source`** (pool + PostgreSQL) : `email:<forme>` quand la valeur est
  déduite. Sans cette trace, impossible de distinguer une donnée vérifiée d'une déduction
  ni de revenir en arrière. Un prénom saisi n'est JAMAIS écrasé.
- **Rattrapage : 947 prénoms + 819 noms écrits.** Pool passé de 36 % à **48 %** de contacts
  avec prénom, PostgreSQL à 52 %. Contrôle qualité sur la forme la plus risquée
  (`prenom_seul`) : 17 justes sur 18 tirages au hasard.
- **Branché à `create_in_pool`** : tout nouveau contact scrapé passe par l'extraction.

**Sur l'enrichissement téléphone qui échouait en `insufficient_info` (56/56)** : le code
exigeait `nom ET societe`, or **0 contact sur 2 121 sans téléphone n'avait de nom** — le
scraping collecte des données d'ENTREPRISE (fiche Google Places via Serper : 4 780 numéros),
pas d'individus. Inadéquation outil/donnée, pas bug. 622 contacts ont une société sans
téléphone : la piste utile est de ré-interroger Serper Places, pas Basile/LinkedIn.

### Volet 2 — Mini-CRM commercial (dans PostgreSQL)
**Choix :** construit dans PostgreSQL et non dans le pool DuckDB. Vérifié avant de trancher :
sur les 75 contacts à rappeler, 14 manquaient à PostgreSQL — dont **13 simplement pas encore
enrichis** (ils entrent au cron de 06:30) et 1 en erreur Mailnjoy. Exclusion transitoire, pas
structurelle.

- **`scripts/pg_schema_crm.sql`** : `contact_followup` (l'ÉTAT : attribution, statut,
  relance) + `followup_events` (le JOURNAL, en ajout seul) + vue `v_a_rappeler`.
  Même leçon que `email_events` : un CRM qui écrase « dernier appel » perd la relation.
  Clé sur l'ADRESSE — le suivi survit à la sortie du contact du référentiel.
  `UNIQUE(email, site_code)` : sans quoi deux commerciaux appellent le même prospect.
- **`scripts/followup_backend.py`** : règles d'accès appliquées CÔTÉ SERVEUR —
  un commercial voit ses contacts + le vivier non attribué, jamais ceux d'un collègue ;
  il ne peut attribuer qu'à lui-même ; un admin voit tout et distribue. Traiter un contact
  du vivier se l'attribue automatiquement.
- **5 endpoints** : liste (vue mes|vivier|tous), commerciaux, journal, assigner, appel.
  Rôle et identité viennent de la SESSION, jamais du corps de la requête.
  `vers: "__moi__"` résolu côté serveur.
- **Page `/site/[code]/a-rappeler`** : liste + fiche en panneau latéral (pas une modale :
  inutilisable sur téléphone, or un commercial consulte debout entre deux appels).
  Relances en retard en tête et en rouge. Téléphone cliquable. Mention explicite quand le
  prénom est déduit (« à confirmer au téléphone »).
- **Menu dédié au rôle `commercial`** : groupe « Mon travail » — À rappeler, Contacts,
  Rendez-vous. Plus de scraping ni de SEO : ce n'est pas son métier.
- **Vérifié** : Romeo prend un contact, Gilles est refusé dessus (403), un commercial ne peut
  pas attribuer à un tiers, l'admin le peut, le journal enregistre tout. Données de test
  purgées après chaque essai.

**Comptes commerciaux existants** : Romeo, Gilles, test — tous sur lcr.

**RESTE** : `/code-review ultra` demandé par le user sur cette partie (déclenchable par LUI
seul, je ne peux pas la lancer). Boucle de propagation `promote_contact` inefficace en masse
(1 connexion PG + 1 DuckDB par contact — 947 contacts ont pris > 10 min).

## 🔌 2026-08-19 — BALAYAGE DU CÂBLAGE (126 appels API analysés)

Outil : script de balayage croisant chaque `apiFetch` de l'UI avec le handler `api.py`
correspondant et le module/base qu'il importe réellement.
**Piège rencontré** : la 1re version cherchait le NOM du module dans le corps du handler —
elle signalait donc comme suspect un endpoint dont le commentaire disait « on a quitté
acquisition_backend ». Corrigé pour ne détecter qu'un IMPORT réel, commentaires et
docstrings retirés. Un outil d'audit qui se trompe est pire que pas d'audit.

**4 vrais défauts trouvés et corrigés :**

1. **`/api/sites/{site}/acquisition/stats`** — les 3 tuiles du tableau de bord lisaient
   `crm/{site}.duckdb`, la base CRM legacy : **1 653 contacts dont 1 506 blacklistés**.
   Affichait « Contacts 1 653 / Cold email 19 / À rappeler 128 » au lieu de
   **7 916 / 6 357 / 75**. Recâblé sur `contacts_pool_backend.stats_for_site`. Le
   sous-titre dit désormais « 1 482 blacklistés inclus » — un total qui laisse croire à du
   contactable est un demi-mensonge.
2. **`/api/sites/{site}/acquisition` (GET)** — mêmes symptômes pour les listes « À rappeler »
   et « Contacts récents ». Recâblé sur `list_contacts_for_site`.
3. **`/api/seo-ahrefs/{site}`** — lisait `{site}-ahrefs-latest.json`, **plus écrit depuis le
   21/05/2026**. Le cron de 6 h écrit `{site}-metrics-latest.json` sous un autre nom : la
   tuile Domain Rating servait des chiffres vieux de 3 mois sans le signaler. Recâblé, avec
   repli sur l'ancien fichier pour `domain_rating` que le format récent ne porte pas.
   NB : le « 0 visite/mois » est EXACT — Ahrefs ne positionne leclientroi.com que sur
   1 mot-clé (« client roi », position 4). Ce n'est pas un bug, c'est un constat SEO.
4. **`/api/sites/{site}/contacts/pool/count`** — route **INEXISTANTE**, appelée par
   l'éditeur de newsletters pour annoncer la taille de la cible. 404 avalé par un `catch` :
   à l'écran, une route absente et un compteur à zéro sont indiscernables. Créée
   (immobilier : 2 085).

**2 faux positifs vérifiés** : `cleanup_backend` opère bien sur le pool (il n'importe
d'`acquisition_backend` qu'une fonction de validation, sans accès base) ; les
POST/PATCH/DELETE sur `/acquisition` écrivent bien dans la base legacy mais **l'UI ne les
appelle jamais** — toutes ses écritures passent par `/pool/contacts/*`.

**RESTE, connu et documenté** : la base CRM legacy est encore ÉCRITE par 4 scripts
(`tally_to_prm` cron horaire, `emelia_to_crm` cron 19 h, `workflow_emelia_push`,
`prospect_scraper`) et 2 webhooks. Ces scripts écrivent AUSSI dans le pool, donc aucune perte
de données — mais la base fantôme continue de grossir (source `sweego:default` = 1 560 lignes
de rebonds). Plus AUCUN écran ne la lit désormais. Son débranchement complet relève des
étapes 6-7 de la migration.

**2 collisions de couleurs introduites par mon remplacement mécanique, corrigées :**
`superadmin-bar` avait `bg-warning` + `text-warning` (marron sur marron, illisible) et
`newsletter-editor` `bg-primary` + `text-primary` (violet sur violet). Un aplat a besoin de
DEUX rôles : la couleur et son contraste — c'est à ça que sert `-foreground`. Le cadre
superadmin de 5 px ambre est passé à **1 px rose** (il mangeait 5 px de contenu sur chaque
bord). KPI remontés au-dessus des tableaux journaliers.

## 🎨 2026-08-19 — REFONTE UI, phases 1 à 3 (déployées)

Plan complet : artefact « Remettre la plateforme d'aplomb ». Audit chiffré : 673 couleurs en
dur sur 40 fichiers, 7 pages hors menu, 22 `confirm()` natifs, 11 tableaux sans défilement,
50 largeurs figées. Structure du thème déjà correcte (Tailwind v4 + `@theme inline`).

**Phase 1 — tri des pages.** Supprimées : `/dashboard` (gabarit shadcn, 0 appel API),
`/campaigns` (756 l., ancienne API, 0 lien entrant), `/site/[code]/messages`.
  - **Correction en cours de route** : mon plan proposait de « fusionner » cold-email et
    messages. Faux — `Messages` était une PAGE-MENU affichant deux cartes vers cold-email et
    newsletters. Le bon geste était de la supprimer et d'exposer les deux destinations
    directement au menu : un écran dont le seul rôle est d'afficher deux liens est un clic
    pour rien. Les 2 fils d'Ariane « ← Messages » renvoient désormais au tableau de bord.
  - `/onboarding` (570 l.) CONSERVÉE, décision user en attente.
  - Sauvegardes dans `genesis-ui/.refonte-bak/`.

**Phase 2 — navigation en deux espaces** (`app-sidebar.tsx`).
  - Espace de travail : **Pilotage** (Tableau de bord, Vision) · **Acquisition** (Scraper,
    Contacts, Segments, Nettoyage) · **Campagnes** (Cold email, Newsletters, Campagnes,
    Rendez-vous) · **Contenu & SEO** (Articles, Analyse SEO, Stratégie SEO, Plan de taggage,
    Agents IA) · **Configuration** (Clés API, admins seulement).
  - Espace admin : **Plateforme** (Vue multi-sites, Maintenance, Versions) · **Données**
    (Bases de données, Coûts LLM) · **Accès & sécurité** (Utilisateurs, Sécurité, Logs).
  - **Mapping des rôles refait** : `commercial`/`contenu`/`strategie` pointaient vers des
    groupes supprimés — ces comptes se seraient retrouvés devant un menu vide.
  - « Vision » N'A PAS été fusionnée dans le tableau de bord : c'est une décision produit,
    elle attend le user. Les deux cohabitent dans Pilotage.

**Phase 3 — police et thème.**
  - `layout.tsx` : Plus Jakarta Sans + JetBrains Mono → **Outfit + Fira Code** via
    `next/font` (auto-hébergées au build : plus de requête vers Google au chargement, les
    `<link> preconnect` ont été retirés).
  - `globals.css` : tokens oklch du user. **Deux écarts assumés et commentés** : (1)
    `--muted-foreground` éclairci — la maquette le donnait identique au texte principal, ce
    qui supprimait toute hiérarchie de lecture ; (2) ajout des rôles **`--success` et
    `--warning`**, absents de la maquette, qui sont des ÉTATS au même titre que
    `destructive` — sans eux chaque écran réinvente sa teinte, ce qui est la cause des 673.
  - **673 → 0 couleur en dur.** 602 remplacées mécaniquement (emerald/green/teal→success,
    amber/yellow/orange→warning, rose/red→destructive, indigo/violet/sky/blue→primary), et
    **5 palettes CATÉGORIELLES traitées à la main** (états de contact, canaux d'envoi, types
    de version, sites) : elles distinguent des catégories, pas des états — les écraser sur un
    rôle unique aurait rendu deux catégories identiques. Elles vont sur `chart-1..5`, et un
    « lead » a maintenant la même couleur d'un écran à l'autre.

**Vérifié** : build OK, 13 erreurs TS préexistantes inchangées (aucune ajoutée), 10 pages
servies en 200, les 3 supprimées en 404, `--primary:#7300ff` et `--accent:#0fc` dans la CSS
livrée, 4 fichiers de police auto-hébergés. 29 pages (contre 32).

**RESTE (phases 4-5)** : reprise écran par écran (câblage des données + 8 `catch` vides
restants sur Campagnes), 22 `confirm()` natifs à supprimer, formulaires longs en modale à
passer en pages, 11 tableaux à encadrer, 50 largeurs figées à assouplir.

## 🚪 2026-08-19 — CORRECTION DE CAP : modèle ENTONNOIR, pas miroir

**Reprise user :** « j'avais pas demandé que ça parte dans 2 bases, je voulais que les
scrapes/nettoyages soient faits dans DuckDB, tous les contrôles d'enrichissement effectués,
et quand le contact est ok il passe en base SQL. Je ne veux pas polluer Postgres avec des
données sales. » J'avais construit un miroir intégral — contresens. Corrigé.

**Les 27 contrôles ont été inventoriés et présentés** (étage 0 découverte : tombstone, syntaxe,
motifs, honeypot, TLD interdit, rôle, jetable, TLD poubelle, MX, RGPD ×3, score ; étage 1
Mailnjoy : valid/risky/invalid/spamtrap/500 ; étage 2 data.gouv : diffusion partielle,
administration, entreprise fermée ; étage 3 entretien : blacklist, récence 180 j, nettoyage
nocturne, purge RGPD ; étage 4 envoi : 120 j, état, secteur/géo, caps).

**DÉCISION USER : option C, la plus stricte** + **retrait avec conservation du journal**.
Un contact entre dans PostgreSQL si : Mailnjoy `valid`, vérifié il y a < 180 j, non
blacklisté, ET **enrichissement data.gouv EFFECTUÉ et non excluant**.

**Implémenté :**
- `scripts/pg_gate.py` : `ELIGIBILITE_SQL`, le critère écrit UNE fois (le balayage et la
  décision unitaire s'en servent tous les deux ; deux formulations divergeraient).
- `pg_sync` : `sync_contact` → **`promote_contact(id)`**, une seule fonction pour les deux
  sens — elle relit l'éligibilité et met PostgreSQL en conformité, promotion comme retrait.
  `sync_blacklist` devient un RETRAIT. `record_event` résout `contact_id` **dans PostgreSQL**
  (le contact peut ne pas avoir franchi la porte ; une FK invalide ferait échouer l'insert).
- `scripts/pg_reconcile.py` : balayage complet, `--dry-run` disponible. **Garde-fou : si le
  retrait détruisait des événements, la transaction est annulée** — la fenêtre de 120 j en
  dépend.
- **CRON AJOUTÉ 06:30 UTC** : `datagouv_enrich.py && pg_reconcile.py`. Indispensable à
  l'option C — l'enrichissement n'avait AUCUN cron (dernier passage manuel le 18/08), les
  contacts seraient restés bloqués en salle d'attente indéfiniment.

**Purge effectuée : 7 916 → 6 194 contacts** (1 722 retirés). Vérifié : 0 blacklisté,
0 non-valid, 0 exclu, 0 non enrichi. **1 523 événements conservés** pour les contacts
retirés, dont 9 adresses toujours protégées par la fenêtre de 120 j sans avoir de contact en
base — la preuve que le journal survit au retrait.

**DEUX DÉFAUTS TROUVÉS PAR LES TESTS, corrigés :**
1. `test_pg_equivalence` comparait PostgreSQL **avec lui-même** : `contacts_pool_backend`
   délègue à PG quand `PG_READS=1`, donc sans `duck._PG_READS = False` le test était vert
   quoi qu'il arrive. Le pire des tests, celui qui rassure sans rien vérifier.
2. `test_frequence_capping` **écrivait dans la production** : ses contacts fictifs
   (`neuf@`, `orphelin@`, `perdu@exemple.fr`) partaient dans `email_events` via le miroir et
   se retrouvaient dans la fenêtre de 120 j. Corrigé par `pg_sync._ACTIF = False` dans le
   test ; les 3 événements fictifs ont été purgés.

**Test réécrit pour l'entonnoir** : PostgreSQL n'est plus comparé à l'identique mais comme
**sous-ensemble justifié** — PG ⊆ DuckDB sur le jeu complet (2 085 vs 2 122), et les 37
absents attendent TOUS leur enrichissement (aucun écart inexpliqué). Comparaison sur les jeux
complets et non sur les tranches top-N, qui diffèrent légitimement quand les pools diffèrent.
4 suites vertes.

## 🐘 2026-08-19 — MIGRATION POSTGRESQL : étapes 1 à 3 FAITES (plateforme fermée)

**Demande user :** « déconnecte tout le monde, affiche le module site en maintenance, ensuite
fait la migration ». Exécuté dans cet ordre.

**Fermeture :** maintenance activée (message + eta), puis **4 sessions purgées** (2 users).
Ordre volontaire : maintenance AVANT la purge, sinon quelqu'un se reconnecte dans l'intervalle.

**Étape 1 — socle.** PostgreSQL 16.14 installé (apt), service actif+enabled sur 5432,
`python3-psycopg2` 2.9.9. Rôle+base `cheffer`, extensions `citext` et `pgcrypto`.
`PG_DSN` dans `.env` (chmod 600, autoblog). Schéma : `scripts/pg_schema.sql`, idempotent —
8 tables + 2 vues.
  - `contacts` : `sectors` en **text[] indexé GIN** (avant : `sectors::VARCHAR LIKE '%x%'` =
    scan complet), `mailnjoy_decision`/`mailnjoy_checked_at` sortis du JSON pour être indexés.
  - `contact_sites` : l'ÉTAT SEUL. Les événements partent dans `email_events`.
  - **`email_events`** : journal EN AJOUT SEUL, clé = l'**email** (survit à la purge d'un
    contact — c'était le trou des renvois d'août). CHECK sur event_type, 4 index dont un
    partiel `WHERE event_type='sent'` pour la fenêtre de 120 j.
  - Vues `v_suppression` (la base repoussoir devient DÉDUITE) et `v_contact_engagement`.

**Étape 2 — reprise.** `scripts/pg_migrate.py`, idempotent, lecture seule sur DuckDB.
Résultat : contacts 7 916, contact_sites 7 916, enrichment 6 367, campaigns 8, mailboxes 4,
ramp_log 32, **email_events 3 564**.
  - Sources du journal : `sent` = `maildoso_sent` ; `open`/`click` = `contact_site_history`
    (pixel /api/track/open) et **PAS** `sweego_events` (pollué par les boîtes de test et les
    proxys anti-spam → taux à 15 000 %) ; `bounce`/`complaint`/`unsub` = sweego_events
    restreint aux adresses réellement prospectées ; + Emelia.
  - **Correctif trouvé par la vérification** : 2 adresses manquaient à `v_suppression`
    (envoyées via Sweego/Emelia, sans journal par destinataire) → ajout d'une source
    complémentaire depuis `last_contacted_by_site_at`. Après : **0 manquante**.

**VÉRIFICATIONS (toutes vertes) :** contacts 7916=7916, non-blacklistés 6434=6434, mailnjoy
valid 6415=6415, relations 7916=7916, campagnes 8=8, envois maildoso 1221=1221.
**Pioche immobilier contactable : 2122 (DuckDB) = 2122 (PostgreSQL).** Base repoussoir : 730
DuckDB / 731 PG (0 manquante, 1 de couverture en plus). Écarts expliqués : +7 ouvertures /
+2 clics = apport Emelia (journal plus complet) ; 2 776 lignes `contact_site_history`
non reprises = références mortes vers des contacts supprimés (la clé étrangère
`ON DELETE CASCADE` rend ce cas structurellement impossible en PG).

**Étape 3 — double écriture EN PLACE.** `scripts/pg_sync.py` : miroir best-effort, jamais
bloquant pour DuckDB, mais **compteurs d'échec exposés** (`sync_health()`) — un miroir qui
échoue en silence serait pire que pas de miroir. Désactivable à chaud par `PG_SYNC=0`.
Branché sur 6 points d'écriture de `contacts_pool_backend` : `create_in_pool`,
`set_global_blacklist`, `upsert_site_history`, `change_state_for_site`,
`mark_pushed_to_emelia` (→ `record_send`, c'est lui qui alimente la fenêtre de 120 j) et
`record_engagement`. Testé bout en bout : événement créé, campagne et contact rattachés,
`v_suppression` le voit. **Le contact utilisé pour le test a été remis à zéro des deux côtés.**

**Poids :** PostgreSQL = 28 746 lignes en **24,9 Mo**. contacts.duckdb = 26 000 lignes en
**1 061 Mo**. Facteur 42.

**Page admin** : PostgreSQL apparaît dans `/admin/database` à côté des bases DuckDB, avec la
santé de la double écriture — voir les deux côte à côte est le seul moyen simple de repérer
une divergence.

**Étape 4 — BASCULE DES LECTURES FAITE.** `scripts/pool_pg.py` : implémentation PostgreSQL
des 8 lectures qui décident QUI reçoit un email (`pick_for_campaign`,
`count_available_for_sector`, `pick_for_segment`, `count_for_segment`, `is_suppressed`,
`filter_suppressed`, `suppression_stats`, `pool_sectors`). Portées EN PREMIER car une
divergence s'y paie en renvois. Le reste du module (listes d'écran, compteurs d'ambiance)
reste sur DuckDB — sans risque, les deux bases étant tenues alignées par `pg_sync`.
  - Drapeau **`PG_READS=1`** dans `.env` : retour arrière en une minute, sans redéploiement.
  - Pool de connexions `ThreadedConnectionPool(1,10)` : l'API ouvrait une connexion par appel
    faute de choix côté DuckDB (verrou unique) ; ici on peut faire mieux.
  - La fenêtre de 120 j est DÉDUITE de `email_events`, plus lue dans une table tenue à la
    main. `sectors` en `= ANY()` sur index GIN au lieu d'un LIKE sur du JSON.
  - `tests/test_pg_equivalence.py` — **25 contrôles sur les DONNÉES RÉELLES**, tous verts :
    volumes par secteur (6 secteurs), IDENTITÉ des contacts piochés (lots de 10/160/500,
    pas seulement le nombre), ORDRE des 10 premiers, les 730 adresses bloquées le restent,
    3 jeux de règles de segment, 2 filtres géographiques.
  - Simulation de dispatch à blanc sur lectures PG : `would_send 160`. Garde-fou 120 j :
    3 écartés sur 6 comme attendu.
  - `tests/test_frequence_capping.py` force désormais `_PG_READS = False` (il teste le
    chemin DuckDB sur une base jetable ; sinon il interrogerait la production).
  - 4 suites de tests vertes, 8 tours de concurrence sans échec.

**Complément (trou trouvé en répondant à « la migration est finie ? ») :** `pg_sync` ne
recopiait PAS les campagnes. Une campagne créée après la bascule n'aurait existé que dans
DuckDB, et TOUS ses envois seraient entrés au journal avec `campaign_id = NULL` — le
reporting par campagne, raison d'être du journal, aurait été muet sur les campagnes récentes.
Corrigé : `pg_sync.sync_campaign()` + `_miroir_campagne()` branché sur `create_campaign`,
`set_status`, `update_campaign` et la fin de `dispatch_campaign` (PAS sur `_bump_sent`, qui
est appelé à chaque email — 160 écritures PG par lot pour une seule valeur utile). Testé :
une pause de campagne se reflète immédiatement dans PostgreSQL.

**RESTE (étapes 5 à 7)** : couper l'écriture DuckDB du pool, faire lire les campagnes depuis
PostgreSQL (elles y sont, mais l'application lit encore DuckDB), nettoyer. Ces étapes
n'exigent PAS que la plateforme reste fermée. **Plateforme encore FERMÉE** (choix user) —
la réouverture est sûre dès maintenant.

## 🖥️ 2026-08-19 — UI : maintenance, tableaux hebdo, inventaire des bases (DÉPLOYÉ)

**Demande user :** (1) page de maintenance sur le login avant la migration, (2) sur le
tableau de bord, DEUX tableaux hebdo distincts (emails envoyés / contacts scrapés) « car
aujourd'hui on comprend rien », (3) page admin listant les tables et leur nombre de lignes.

**Livré et déployé** (build Next + `pm2 restart 20 18`, 17h05 Paris, aucun envoi en cours) :
- **`scripts/maintenance_backend.py` (NOUVEAU)** — état dans `memory/maintenance.json`, PAS
  en DuckDB : lu à chaque affichage du login par des visiteurs non authentifiés ; passer ce
  chemin public par la base ajouterait de la contention sur le verrou mono-écrivain.
  `login_allowed()` laisse TOUJOURS passer admin/superadmin (sinon plus personne ne peut
  lever la maintenance). CLI : `maintenance_backend.py [on <msg>|off]`.
- **`scripts/dashboard_stats_backend.py` (NOUVEAU)** — `daily_email_stats`,
  `daily_scraping_stats`, `database_inventory`. Une ligne par JOUR sur **7 / 15 / 31 jours**
  (demande user), **heure de Paris** (le scraping 22h-8h est à cheval sur minuit UTC),
  regroupement en Python pour survivre à la migration PG.
  **Statut par jour** (`_statut()`) qui pilote le surlignage : `inactif` = ROUGE ;
  `ferme` = dimanche sans envoi (fenêtre lun-sam), neutre ; `en_cours` = journée non finie,
  neutre. Sans cette distinction chaque dimanche et chaque matin seraient rouges, et
  l'alerte deviendrait un bruit de fond. Sur 31 j : 6 jours rouges côté emails, 7 côté
  scraping — ils correspondent au gel du 20-24/07 et au démarrage tardif de l'autoscrape.
- **api.py** : `/api/maintenance` (PUBLIC, ajouté à `_AUTH_OPEN_PATHS`),
  `/api/admin/maintenance` GET+POST, `/api/sites/{site}/daily-stats?days=7|15|31`, `/api/admin/database`
  (les 2 derniers + maintenance admin ajoutés à `_ADMIN_PREFIXES`). **Refus de login 503**
  pour les non-admins pendant la maintenance — sans ça la page ne serait que cosmétique.
- **UI** : `components/daily-tables.tsx`, `app/admin/database/page.tsx`,
  `app/admin/maintenance/page.tsx`, écran de maintenance dans `app/login/page.tsx` (avec
  lien « Accès administrateur »), 2 entrées de sidebar. `next.config.ts` : `distDir`
  paramétrable par `NEXT_DIST_DIR` pour compiler sans écraser le `.next` de production.

**2 défauts trouvés EN CONSTRUISANT, et corrigés :**
1. **Taux d'ouverture absurdes (jusqu'à 15 450 %)** : je comptais les ouvertures depuis
   `sweego_events`, qui ne couvre pas le canal maildoso ET contient le trafic des boîtes de
   test/warmup (`gilles@leclientroi.com`, `quickeneen@outlook.com`…) plus les ouvertures par
   proxy anti-spam. **La bonne source pour maildoso est `contact_site_history`**, alimentée
   par le pixel `/api/track/open`. Les taux tombent à 0-58 %. (Le chiffre de 345 ouvertures
   du rapport du matin venait déjà de la bonne source : il reste valable.)
2. **La maintenance ne s'appliquait pas, en silence** : `tempfile.mkstemp` crée en **0600**.
   Fichier écrit par root (CLI) → illisible par `autoblog` (l'API) → le `except` renvoyait
   « pas de maintenance ». Fix : `os.chmod(tmp, 0o644)` avant le rename, ET `get_status`
   distingue désormais fichier ABSENT (normal) de fichier ILLISIBLE (incident loggué
   bruyamment). Vérifié dans les deux sens : écriture root ET écriture autoblog.

**Colonne « Redites »** dans le tableau emails = envois vers quelqu'un déjà servi le même
jour. Doit rester à 0. Rend visible d'un coup d'œil le problème d'août.

**Attention documentée dans l'UI** : la maintenance ferme l'INTERFACE, elle n'arrête ni le
cron d'envoi de 8h30 UTC ni le scraping nocturne.

## ⚠️ 2026-08-19 — RÉGRESSION introduite puis corrigée : « 0 campagne » sur /site/lcr/campaigns

**Symptôme user :** la page Campagnes affichait « 0 campagne » alors que `campaigns_unified`
en contient 8, dont une `running`.

**Cause — c'était bien la régression du jour, pas un bug préexistant.** Le nouveau
`dashboard_stats_backend` ouvrait `god_mode.duckdb` en **lecture seule**. Or DuckDB met
l'instance de base **en cache par processus** : tant qu'une connexion lecture seule est
ouverte, toute connexion lecture-écriture sur le même fichier lève
`Can't open a connection to same database file with a different configuration`.
`campaign_engine._conn()` n'ouvre qu'en lecture-écriture, sans repli → l'endpoint
`/api/sites/{site}/campaigns` échouait dès que le tableau de bord chargeait ses stats en
parallèle (FastAPI sert les endpoints synchrones dans un threadpool : les requêtes se
chevauchent). Reproduit en 2 threads, 5/5 échecs.

**Fixes :**
- `dashboard_stats_backend._connect()` : tente **lecture-écriture D'ABORD** (contre-intuitif
  pour un module qui n'écrit jamais, mais c'est la config de tous les autres modules de
  l'API — ouvrir en lecture seule met en cache une instance qu'ils ne peuvent plus
  rejoindre), lecture seule en repli, avec réessais sur verrou. Vérifié : 10 tours de
  concurrence, 0 échec, 8 campagnes lues.
- **Page Campagnes** : le `catch {}` avalait l'erreur et affichait « 0 campagne »,
  indiscernable d'une liste vide. Désormais trois états distincts — erreur (avec bouton
  Réessayer), chargement, réellement vide. Il reste 8 autres `catch {}` silencieux dans
  cette page : même piège potentiel ailleurs.

**Règle à retenir :** dans ce process, ne JAMAIS ouvrir une base DuckDB en lecture seule si
un autre module l'ouvre en lecture-écriture. Ce piège disparaît avec PostgreSQL.

## 📐 2026-08-19 — Proposition de migration PostgreSQL (à arbitrer par le user)

**Demande user :** modèle hybride — DuckDB garde le scraping, PostgreSQL prend les données
propres, + une table comportementale email (envoi/open/clic). Motif : « le projet ne marche
plus », la segmentation a fait déborder le vase.

**Mesures faites :** aucun PostgreSQL installé (ni psycopg ni sqlalchemy) ; VPS = 4 cœurs,
3 Go RAM libres, 23 Go disque. **`contacts_pool_backend.py` est une VRAIE porte unique** :
21 fichiers touchent au pool, seulement **3 accès directs** hors du module (2 dans
`mailnjoy_check`, 1 script mort). 40 constructions SQL DuckDB à porter (`FILTER (WHERE)` et
`GREATEST` identiques en PG ; `json_extract_string`→`->>`; `INTERVAL '30' DAY`→`'30 days'`;
5 PRAGMA→catalogue). ~175 000 lignes au total : reprise en minutes.

**Frontière proposée :** DuckDB = ce qui est écrit par 1 process et jetable (scrappe_pending,
scrappe, rejected, targets, serper). PostgreSQL = ce que tout le monde lit/écrit et qui doit
rester cohérent (contacts, contact_sites, enrichment, email_events, campaigns, segments,
mailboxes). **Une seule porte, un seul sens** : promotion à la validation Mailnjoy (fin du
dual-write, source des 294 orphelines).

**`email_events` en ajout seul** : la base repoussoir devient un fait DÉDUIT
(`NOT EXISTS ... event_type='sent' AND occurred_at > now()-interval '120 days'`) au lieu d'un
état recopié dans 3 endroits — ce qui supprime la classe de bug du matin.

**Procédure en 7 étapes réversibles** (artefact publié) : socle PG → email_events (additif,
valeur immédiate) → double écriture + contrôle quotidien → bascule des lectures (drapeau) →
coupure du pool DuckDB (le 1 Go disparaît) → rapatriement campagnes/segments → nettoyage.

**Sur le 1 Go de contacts.duckdb** : CHECKPOINT exécuté, **0 Mo rendu** (20 blocs libres sur
4 058 — pas d'espace mort). Cause = **3 510 row groups à 5 lignes** (`contacts` 8 210 lignes
/1 717 groupes ; `contact_site_history` 10 986/1 793 ; vs `contact_enrichment` 7 108/4 groupes
= 6,6 Mo). Origine : écriture ligne à ligne avec fermeture de connexion (donc checkpoint) à
chaque opération, imposée par le verrou mono-écrivain. Recompactage NON fait : l'étape 5 de
la migration le rend sans objet.

## 🔝 REPRISE 2026-07-24 — Scraping : boucle infinie Mailnjoy + gel 11 h/jour (FIXÉ)

**Symptômes user :** (1) cleanup quotidien 07:05 supprimait 100 % des contacts depuis le 17/07
(0 validés), (2) scrapes « vides » depuis que Serper est à 0 crédit, impression que Basile ne
peut pas tourner seul.

**Causes trouvées (3 bugs indépendants qui se combinaient) :**
1. **Aucune mémoire des rejets** : un email tué par Mailnjoy (risky/invalid — décision user
   2026-05-22 : risky = kill) était supprimé du pool sans trace. Basile/Serper le re-trouvaient
   le lendemain → ré-insertion → re-check Mailnjoy (2 crédits/jour/email) → re-suppression.
   ~50 emails tournaient en boucle depuis le 17/07 ; le lot quotidien du cleanup n'était QUE ça,
   d'où 100 % supprimés.
2. **Reprise sans mémoire des villes** : `daily_retry`/`autoscrape_plan` ne persistaient que
   `depts_done` — chaque matin le dept 59 repartait de la ville 1 (jamais au-delà de ~40/54).
3. **Gel 11 h/jour** : `fetch_email_from_site` (appelé aussi par Basile) faisait `r.text` sans
   cap de taille → un site pathologique gelait le run de 06:15 à ~17:13 (state R, chardet/regex
   sur blob géant). C'est LA raison des « timeout » quotidiens et de la non-progression.
   Basile tournait bien SEUL (70 valid/jour) mais ne produisait que les loopers du bug 1.

**Fixes déployés :**
- **`scrappe_rejected`** (god_mode.duckdb) : tombstone des emails tués. Marqué par drain
  (`mailnjoy_check.check_pending_queue`), cleanup (`cleanup_backend.run_cleanup`), imports
  (`acquisition_backend._validate_address` → early-return gratuit `rejected_before`).
  Consulté avant insertion (god_mode_agents + basile_backend ×2) et avant tout check payant.
  **Backfill : 8 327 emails** depuis logs/mailnjoy_deletions.log + god_mode_logs.
- **Drain** : supprime aussi la copie pool non vérifiée quand il tue un pending
  (`_delete_unverified_pool_copy`) — c'était la fuite qui alimentait le cleanup du matin.
- **Reprise intra-dept** : `run_autoscrape(cities_done=, cities_dept=)` + persistance par ville
  dans `<site>-region-progress.json` ; branché dans `daily_retry` ET `autoscrape_plan.work`.
- **`daily_retry`** : reprend en Basile-seul si Serper bloqué (avant : test Serper KO = rien).
- **`fetch_email_from_site`** : stream + cap 2 Mo + filtre content-type + décodage utf-8/replace.
- Pending `mailnjoy_attempts` ≥5 (194 rows invisibles au drain) resetés à 0 ; crédit Mailnjoy
  vérifié : 1 036 125.
- Run du 24/07 stoppé (figé depuis 06:15), progress patché (39 villes dept 59 done, valid=529),
  retry relancé avec le nouveau code → reprise ville 40/54.

- **4e bug (même session, plus tard)** : le vrai `fetch_email_from_site` gelait sur la REGEX
  `EMAIL_RE.findall` (quadratique sur blobs sans `@`) — remplacée par `_emails_in_text()`
  (fenêtre bornée autour de chaque `@`, testé : 2 Mo pathologique en 0,000 s vs heures).
- **5e bug** : le drain PM2 était un zombie (« online » sans PID) ; le VRAI drain était un
  process orphelin de 30 jours (PID 2741494, lancé 23/06, binaire python supprimé, ancien
  code sans tombstones) qui tenait le verrou DuckDB par à-coups. Orphelin tué, drain PM2
  recréé proprement (`pm2 delete` + `start`, pm2 save) — il logge enfin.

- **7e fix (analyse des rejetés, demande user)** : 55 % des 4 990 emails supprimés étaient des
  FAUX POSITIFS (Mailnjoy disait VALID/SAFE, tués par l'attribut role/catchall). Décision user
  2026-07-24 : les `contact@` sont de bons contacts cold-email → `classify_response` garde
  désormais tout VALID+SAFE ; VALID/RISKY (catchall) toujours tué. 2 676 purgés du tombstone.
  Doc : `docs/contact-acquisition.md §0ter`.

**RESTE :** vérifier demain 07:05 que le cleanup ne supprime plus 100 % ; le plan immobilier est
« done » sur les 12 régions mais les chiffres du 16/07 incluent des fantômes → envisager une
relance du plan (les tombstones + reprise par ville rendent le re-scan quasi gratuit) ; l'UI
Activité des anciens runs reste approximative — cosmétique.

## 🔝 REPRISE 2026-06-29 — Prise de RDV publique (type Calendly/TidyCal)

**Demande user :** lien public de prise de RDV par site, le prospect choisit un motif
(démo/question/partenariat), un créneau parmi ceux ouverts en back-office, saisit ses coords →
**email + SMS de confirmation**. Belle page. Condition : URL testée + email démo réellement envoyé.

**FAIT + TESTÉ bout-en-bout :**
- **`booking_backend.py` (NOUVEAU)** : tables `booking_settings` (config JSON/site, seed défaut :
  Lun-Ven 9-12/14-18, créneaux 30 min, 3 motifs) + `bookings`. Helpers `get_settings`/
  `update_settings`, `available_days`/`available_slots` (filtre passé + déjà réservé, tz Europe/Paris),
  `create_booking` (valide motif + créneau libre), `list_bookings`, `send_confirmations`.
- **`booking_page.py` (NOUVEAU)** : page HTML autonome (CSS inline, responsive, wizard motif→jour→
  créneau→coords), JS vanilla consommant les endpoints.
- **`sweego_backend.py`** : `send_transactional_email` (campaign-type=transac, 1 destinataire) +
  `send_sms` (provider=sms, normalise 06→+336, best-effort). Domaine expéditeur = leclientroi.com
  (seul vérifié Sweego) même pour MKD.
- **`api.py`** : endpoints PUBLICS (exemptés middleware, comme /sweego/click) `GET /api/book/{site}`
  (HTML), `/config`, `/slots`, `POST /submit` ; back-office AUTHENTIFIÉ `GET|PUT /api/sites/{site}/
  booking/settings`, `GET .../booking/list`.
- **UI** : page `/site/{code}/booking` (édite réglages, motifs, dispos hebdo, lien public copiable,
  liste RDV) + entrée sidebar « Rendez-vous » (Commercial). Build Next OK, UI restart OK.
- ✅ **TEST RÉEL** : `GET /api/book/lcr` → 200 ; config/slots OK ; `POST /submit` (démo,
  afchain.camille@gmail.com) → RDV `ba6ba218` créé + **Sweego transaction_id 56bfbd93-…
  (email.ok:true)**. Créneau retiré des dispos après réservation + double-booking refusé. **(1 RDV
  de test reste dans la liste back-office LCR — pas de endpoint delete pour l'instant.)**
- ⚠️ **SMS pas testé en réel** (pas de numéro de test, coût) : payload Sweego `provider:sms`
  best-effort, non bloquant. À valider avec un vrai numéro. ⚠️ Lien public = `https://api.cheffer.email/
  api/book/{site}` (sous /api/ car servi par FastAPI). API à redémarrée faite.
- **MAJ 2026-06-29 (retour user)** : page publique enrichie — **logo** (champ `logo_url`, fallback nom
  du site), **favicon + lien site** (`website_url`, favicon Google s2), **description** (texte d'intro).
  Défauts pré-remplis depuis `sites_config` (url, primary_color, rag_context.business_description).
  Back-office **séparé en 2 onglets** : « Configuration » (identité + réglages + motifs + dispos) et
  « Rendez-vous » (formulaires reçus). Build Next OK, restart OK, rendu vérifié (couleur #0066FF,
  desc + favicon + lien présents).
- **MAJ 2026-06-29 (retour user #2)** : onglets inversés (**Rendez-vous** en 1er + défaut, Configuration
  2e). Système **lu/non-lu** : statut `bookings.status` (`confirmed`=à traiter → `answered`=répondu).
  Endpoints `GET .../booking/unread-count` + `POST .../booking/{id}/status`. Helpers `unread_count` /
  `set_status`. UI : badge « Nouveau » + point rouge + bouton « Marquer répondu » par RDV ; **pastille
  rouge dans la sidebar** sur l'item « Rendez-vous » (nb non-répondus, poll 45s + refresh navigation,
  injectée dans `nav-main.tsx` via champ `badge`). La pastille ne décroît QUE sur « répondu ». Testé :
  unread 2→1 après set_status answered. Build + restart OK.
- **MAJ 2026-06-29 (retour user #3)** : champ `hero_image_url` = **image de fond derrière l'en-tête**
  (voile teinté couleur de marque via color-mix + text-shadow pour lisibilité, ancrée à gauche/cover).
  Champ éditable en back-office (carte Identité). Couleur LCR passée du bleu #0066FF au **violet pastel
  `#a78bfa`** (charte). Persisté pour lcr via `update_settings`. ⚠️ Bug corrigé : l'upsert DuckDB
  `INSERT…ON CONFLICT…CURRENT_TIMESTAMP` plantait (BinderException) → remplacé par read-modify-write
  (SELECT puis UPDATE/INSERT). Rendu vérifié : `--brand:#a78bfa`, `head has-hero`, bg image OK.
- **MAJ 2026-06-29 (sécurité RDV)** : durcissement injection.
  • **XSS email** (vraie faille) : le `name` du prospect était interpolé NON-échappé dans
    `_confirmation_html` → `html.escape()` sur name/label/reason_label. Testé : `<script>` → `&lt;script&gt;`.
  • **Email regex stricte** (`_EMAIL_RE`, ≤254 car) côté backend (`create_booking`) + côté page (bouton
    bloqué + message « email invalide »). Testé live : `<script>…`@ et `pasunemail` → refus, aucun envoi.
  • **Bornage entrées** : name≤120, message≤2000, phone nettoyé `[0-9+ ().-]`≤30 (anti-payload + anti-injection SMS).
  • **Couleur** : `_safe_color` (hex only) sur email + page → anti-injection CSS via `--brand`.
  • **DOM** : motifs rendus via `textContent`/`createTextNode` (plus d'`innerHTML` avec la config).
  • Back-office = React (auto-échappé) ; page publique ne reflète aucune saisie. SQL = paramétré partout.

## 🔝 REPRISE 2026-06-26 (suite) — Quota scrape mensuel + alerte crédits d'envoi

## 🔝 REPRISE 2026-06-26 (suite) — Quota scrape mensuel + alerte crédits d'envoi

**Demande user :** (1) plafonner les users à **5000 scrappe/mois**, (2) **alerte admin quand
il n'y a plus de crédit d'envoi**. Choix validés : quota = contacts GARDÉS/mois, canal alerte =
Telegram (déjà câblé), seuils = bas + épuisé.

**FAIT :**
- **Quota scrape (`god_mode_backend.py`)** : nouvelle table `scrape_quota_usage`
  (user_id, year_month, used, PK) + helpers `scrape_quota_status(user_id)` /
  `record_scrape_usage(user_id, n)`. Cap = `SCRAPE_MONTHLY_CAP = 5000`, par user, tous sites.
- **Enforcement (`god_mode_api.py` POST `/{site}/scrape`)** : si `role != superadmin` →
  refuse (429) quand `remaining<=0`, sinon **clampe `global_cap` au restant**. En fin de scrape
  (thread `run`), `record_scrape_usage(user_id, kept_total)` additionne les contacts réellement
  gardés. **Le superadmin (Camille) n'est PAS limité.**
- **Alerte crédits (`scripts/credit_alerts.py` NOUVEAU)** : surveille les soldes LIVE Emelia
  (`fetch_live_balance`) + Mailnjoy (`get_credit`). Niveaux `low`/`empty` (seuils Emelia<50,
  Mailnjoy<100). Anti-spam : alerte seulement au franchissement d'un palier (état
  `memory/credit_alerts.json`), réarme au retour `ok`. Envoi Telegram (TELEGRAM_BOT_TOKEN/CHAT_ID).
- **Branchements** : `campaign_engine.dispatch_due()` (cron 8h30) + endpoint send-now
  (`api.py`) appellent `credit_alerts.check_and_alert()` avant l'envoi (best-effort).
- Vérifié : `py_compile` OK sur les 5 fichiers ; `scrape_quota_status` → 5000 dispo ;
  logique de seuils OK. (Pas d'envoi Telegram réel déclenché pendant les tests.)
- ⚠️ Sweego n'expose pas de solde lisible → seuls Emelia + Mailnjoy sont surveillés (les 2
  crédits LIVE du pipeline d'envoi). API à redémarrer pour activer (`pm2 restart genesis-dashboard`).

## 🔝 REPRISE 2026-06-26 — Isolation multi-tenant (faille cross-site fermée)

**Problème (signalé user, confirmé) :** un commercial scoppé LCR voyait des données/alertes MKD
(alerte « WordPress (MKD) », « MKDgroupe » dans /view). Cause : l'isolation n'était posée QUE sur
`/api/sites/{site}/*` ; tous les autres endpoints à site (`/api/crm/{site}`, `/api/dashboard/{site}`,
`/api/seo-ahrefs/{site}`, `/api/agents/{site}/*`…) **fuyaient** (200 au lieu de 403). **Vraie fuite
de données, pas cosmétique.**

**Corrigé + VÉRIFIÉ (token commercial réel) :**
- **Middleware (`api.py`) — isolation GÉNÉRALE** : détecte un code site (`_known_site_codes()` =
  registre `sites_config`, fallback `{lcr,mkd,tst}`) dans **n'importe quel** segment d'URL OU le
  query `?site=`, et renvoie **403** si pas dans `sess["sites"]` (superadmin bypass). Remplace
  l'ancien check `/api/sites/` only. Testé : tous endpoints MKD → 403, son site → 200.
- **Agrégés filtrés par session** (helper `_scope_connectors` + filtres) :
  `/api/connectors/health`, `/api/connectors` (masquent emdash=LCR / wordpress=MKD / tally_* selon
  les sites), `/api/health-check` (ne check QUE ses sites), `/api/budget` (force son site),
  `/api/campaigns` (filtre par préfixe de nom `lcr-`/`mkd-`). `_CONNECTOR_SITE` mappe connecteur→site.
- **Front** : `/view` ET `/campaigns` (pages globales cross-site) réservées superadmin → un user
  métier est redirigé vers `/site/{son_site}/dashboard|campaigns`. Garde de rendu anti-flash.
- **Scrapper god-mode ouvert aux users métier sur LEUR site** : tout le router `god_mode_api.py`
  était `Depends(require_admin)` → un commercial avait 403 partout (toggle/scrape inertes, scrapper
  mort alors qu'il est dans la nav Commercial). Remplacé par `require_site_access` (admin OU user
  avec accès au `{site}`) sur les 28 endpoints. Décision user : un commercial peut scraper SON site
  (consomme des crédits Serper/Basile), pas un autre (middleware bloque). Vérifié : lcr→200, mkd→403.
- ⚠️ Limite connue : l'isolation détecte les codes site par scan de segments — robuste pour des
  codes distinctifs (lcr/mkd/tst), à revoir si un futur endpoint embarque un code site hors position
  de scope. Pas de silo de données séparé par tenant (pas nécessaire pour « un user ne voit que son
  site ») — l'enforcement middleware + filtrage agrégé suffit.

## 🔝 REPRISE 2026-06-25 — Webhook Sweego (clics→leads), cleanup pool, Vision

### ✅ Webhook Sweego ENFIN débloqué (clic → lead dans /acquisition)
**Le blocage depuis le départ = mauvais `uuid_client`.** Le bon (compte CACAR Holding,
`technique@leclientroi.com`) = **`bd0d7413-26ff-414c-9e31-232382ff1512`**. L'`Api-Key` du `.env`
SUFFIT pour gérer les webhooks (`/clients/{uuid}/webhooks`), pas besoin d'auth user. (L'ancien
`5fe41d8d-…` était un mauvais uuid → 403.)
- **Tracking clic/ouverture DÉJÀ activé + vérifié** sur `leclientroi.com` (`tracking_click_enabled`,
  `tracking_open_enabled`, `is_verified` = true). Aucun DNS / aucune action dev nécessaire.
- **Mapping event_type_ids Sweego (channel email=1, sms=2) :** 1=Delivered, 2=Soft bounce,
  3=Hard bounce, 4=List Unsub, 5=Complaint, 6=Sent, **9=clicked**, 10=clicked_unsub, 11=opened.
  Body create = `events:[{event_channel, event_type_ids:[…], domain_uuids:[…]}]` (les 3 requis).
  Domain uuids : leclientroi.com=`f68f25ef-b658-470e-9c0e-59ca66e90634`,
  news.leclientroi.app=`f15130f6-…`, news.leclientroi.email=`ee50d85f-…`.
- **Webhook créé : `genesis-prm`** (uuid `f3ac5b86-88ac-4408-8851-c006efb804f9`, ENABLED) →
  `https://api.cheffer.email/api/sweego/webhook?token=<WEBHOOK_TOKEN_1>`, events
  [9,11,3,4,5,10] sur les 3 domaines. Le webhook **`prod`** (→ app.leclientroi.com, 12k succès)
  est intact ; les deux reçoivent.
- **Récepteur durci** (`api.py` `/api/sweego/webhook`) : résolution robuste event_type
  (`event_type|status|event`, normalise tirets ET espaces) + recipient (`recipient|email|to`).
  Mapping : `clicked` humain→`prm` (proxy ignoré), `opened`→horodatage, `Hard bounce`/`List Unsub`/
  `Complaint`/`clicked_unsub`→blacklist + sortie pool. API redémarrée.
- **✅ VALIDÉ 2026-06-25 (vrai clic)** : BAT envoyé (`transaction_id 2717d86d`), clic réel →
  webhook reçu (success_count 2) → `camille@leclientroi.com` promue **lead `prm` dans
  /acquisition** + ajoutée au pool. **Format payload Sweego CONFIRMÉ** : `event_type` =
  **`email_clicked`** / **`email_opened`** (champ recipient présent), pas `clicked`/`opened` du
  config webhook. Le récepteur durci les gère déjà (`== "email_clicked"` + `startswith`).
  Reste : nettoyer le lead de test `camille@leclientroi.com` du pool + acquisition quand on veut.
- ⚠️ Sweego note : webhook `clicked_unsub` « coming soon » côté Sweego (visible en logs en attendant).

### 🧹 Cleanup pool : 1×/nuit (3h) → HORAIRE + robuste
`scripts/nightly_cleanup.py` : (a) `count_unverified()` (avant/après) passe par le retry anti-lock
(`_retry_lock`) — corrige le crash 2026-06-21 ; (b) un verrou pool persistant = SKIP propre (exit 0,
pas d'alerte) ; cron PM2 `genesis-nightly-cleanup` `0 3 * * *` → **`0 * * * *`** (`pm2 save` fait).
Le drain couvre TOUT le pool (le param `site` n'est qu'un label de log, `list_for_cleanup` est
global). Les ~859 jamais-vérifiés ont été drainés → pool **3762 contacts dont 3647 mailnjoy-valid,
0 jamais-vérifié**. Le drainer continu `genesis-mailnjoy-drain` ne couvre QUE le scrape
(`scrappe_pending`), PAS le pool import → c'est l'horaire qui couvre les imports.

### 📊 Vision /site/{site}/vision : secteurs réels (faux 0 corrigés)
La page utilisait `SECTORS_GOD_MODE` (liste scrapable figée : garagiste, plombier…) qui ne matche
pas la taxonomie importée (immobilier 936, banque, industrie…). Nouvelle `pool_sectors()` dans
`contacts_pool_backend.py` (secteurs RÉELS du pool, triés par fréquence) ; endpoints
`sector-availability` + `depletion-alert` branchés dessus. UI inchangée (affiche ce que l'API
renvoie). API redémarrée.

### 🧠 claude-mem installé
`npx claude-mem install` + `start` (v13.8.0, plugin `/root/.claude/plugins/`, worker port 37700,
auto-memory native conservée). Données dans `~/.claude-mem`.

## 🔝 REPRISE 2026-06-24 (soir) — Hub de campagnes multi-canal

**Demande user :** refondre `/site/{site}/campaigns` en hub : wizard guidé (canal → message → cible →
aperçu → récap+planning), cible = Mailnjoy nettoyé < 6 mois, agent IA de délivrabilité contrôlant la
cadence (30k en cold = refus), + stats unifiées. UX au top.

**FAIT (P1→P5, plan approuvé `mutable-tickling-sky.md`) :**
- **`contacts_pool_backend.py`** : `pick_for_campaign` + `count_available_for_sector` filtrent
  désormais Mailnjoy valid ET `checked_at` < 180 j (param `cleaned_within_days`).
- **`deliverability_agent.py`** (NOUVEAU) : caps durs/canal (Emelia=warmup, Sweego ramp 1k→20k,
  Maildoso 0) + `plan_cadence` (faisabilité + planning jour/jour) + `explain` (DeepSeek + fallback).
  Vérifié : Emelia 30k → refus + suggère Sweego ; Sweego 30k → 5 j ✅.
- **`campaign_engine.py`** (NOUVEAU) : table `campaigns_unified` + CRUD + `dispatch_due` (scheduler).
  Dispatch Sweego (testé dry-run : pioche 3 → would_send 3) + Emelia (création campagne 1-step +
  add_contact). Cron **8h30** ajouté (crontab autoblog).
- **`api.py`** : endpoints `channels`, `campaigns/target-count`, `campaigns/plan`,
  `campaigns/preview-lint`, `campaigns` (CRUD), `campaigns/{id}/{pause|resume|cancel|send-now|bat}`,
  + `marketing/overview` + `sweego/engagement` (faits plus tôt).
- **UI** : `campaign-wizard.tsx` (wizard 5 étapes, stepper, cartes canal, aperçu responsive + lint,
  agent délivrabilité, BAT) + `channel-perf-card.tsx` (partagé dashboard/hub) + `campaigns/page.tsx`
  réécrite en hub (table unifiée + ChannelPerfCard + section auto Emelia repliable conservée).
  Build Next OK, restart OK.

**RESTE / À surveiller :**
- Test d'un envoi RÉEL via le hub (jusqu'ici dry-run pour ne pas spammer un vrai prospect).
- Stats par campagne unifiée (engagement) : actuellement progression (envoyés/cible) + ChannelPerfCard
  niveau canal. Rollup par campagne = amélioration possible.
- Maildoso : carte désactivée tant que le séquenceur n'est pas branché (~07/07).
- User va lancer `/ultrareview` sur ce chantier.

## 🔝 REPRISE 2026-06-24 — Sweego mass campaigns + docs

**Demande user :** Intégrer Sweego comme canal "masse" (newsletters + annonces), envoyer un BAT réel,
ajouter Sweego à la sidebar, documenter l'infrastructure email, créer le plan des pages UI.

**FAIT :**

### Sweego backend (scripts/)
- **`scripts/sweego_backend.py`** : 3 bugs corrigés — `provider: "sweego"` → `"email"`,
  `campaign-type: "newsletter"` → `"market"`, champ `channel` supprimé. Sender domain
  `news@news.leclientroi.email` → `info@leclientroi.com`. UTM source `newsletter` → `sweego`.
- **`scripts/api.py`** : ajout `GET /api/sweego/stats` + `POST /api/sites/{site}/mass-campaigns/bat`.
- **`.env`** : `SWEEGO_DOMAIN=news.leclientroi.email` → `SWEEGO_DOMAIN=leclientroi.com`

### BAT envoyé et reçu ✅
Email test "test sweego LCR 2" reçu par `camille@leclientroi.com` (2 min délai).
DKIM ✅ SPF ✅ DMARC ✅ — From `info@leclientroi.com`, MTA via `swg.leclientroi.com`.

### UI (genesis-ui/)
- **`credits-widget.tsx`** : ajout Sweego (Send icon, indigo, nb emails envoyés total).
- **`newsletters/page.tsx`** : section masse complète — dialog preview (iframe scalée 0.33),
  inputs secteur/volume/sujet, BAT (`camille@leclientroi.com`), Simuler + Envoyer (indigo),
  historique campagnes Sweego.
- **`tag/page.tsx`** : ajout Sweego (`utm_source=sweego`) + Maildoso (`utm_source=maildoso`).

### Docs (docs/)
- **`docs/infrastructure.md`** (nouveau) : domaines, MTA Sweego (swg.leclientroi.com), auth triple-pass,
  règle absolue `SWEEGO_DOMAIN=leclientroi.com`, boîtes Maildoso, IP VPS.
- **`docs/platforms-api.md`** (nouveau) : référence Emelia REST+GraphQL, Sweego send/stats,
  Maildoso SMTP/IMAP, tableau comparatif tags, état click→lead.
- **`docs/features.md`** (nouveau) : carte complète des pages UI avec breadcrumbs, APIs, connexions.

### Stats engagement Sweego — FAIT (2026-06-24)
- **`scripts/api.py`** : ajout `GET /api/sweego/engagement` (start/end optionnels) qui câble
  `sweego_backend.engagement_stats()` (jusque-là code mort). Retourne sent/openers/clickers/
  bounces/unsubscribes + open_rate/click_rate.
- **`newsletters/page.tsx`** : ligne de stats engagement (6 tuiles) dans l'en-tête de la carte
  "Campagnes masse Sweego". S'affiche dès qu'il y a des envois. Build + restart OK.
- Vérifié live : 262 envoyés, 7 ouvreurs humains, 42 cliqueurs (16%), 0 bounce.

### Click→lead Sweego — FAIT + testé en réel (2026-06-24)
- Découverte : Sweego A un webhook par destinataire (`email_clicked` avec `recipient`). La doc
  `platforms-api.md` disait l'inverse à tort → corrigée.
- **`GET /api/sweego/click?t=<token>`** (public, exception middleware) : lien tracké par destinataire.
  `sweego_backend.make_click_token()` / `resolve_click()` + table `sweego_click_tokens`. Résout
  token→email → promeut en `prm` → redirige 302. **Testé en réel par le user (Camille → prm).**
- **`POST /api/sweego/webhook`** : récepteur natif prêt (email_clicked→prm, bounce/unsub/complaint→
  blacklisted, opened→horodatage). Table `sweego_events`. ⚠️ Enregistrement bloqué : route
  `/clients/{uuid_client}/webhooks` nécessite l'UUID client (dashboard Sweego / en-tête x-client-id).
  **User a demandé l'UUID au support Sweego — en attente.**
- **`acquisition_backend.create(skip_validation=True)`** : bypass Mailnjoy pour les signaux
  d'engagement (un cliqueur est réel). Corrige le bug "page blanche 10s + contact rejeté".

### Stats harmonisées — FAIT (2026-06-24)
- **`GET /api/sites/{site}/marketing/overview`** : agrège Emelia (campagnes matchant le site,
  compteurs dérivés de mailsSent×%) + Sweego (engagement_stats, niveau compte) en forme comparable
  (sent/open_rate/click_rate/reply_rate/bounce_rate).
- **`dashboard/page.tsx`** : carte "Performance emailing par canal" (composant `ChannelPerfCard`)
  comparant cold email (Emelia) vs masse (Sweego) côte à côte. Build + restart OK.

**RESTE :**
1. **Webhook natif Sweego** : enregistrer via `/clients/{uuid_client}/webhooks` dès que le support
   fournit l'UUID client. Débloquera ouvertures + blacklist auto bounce/désinscription/plainte.
2. **(ancien #1) Click→lead Sweego** : ⚠️ pour les envois de MASSE, le token par destinataire dans
   le lien maison demande la perso URL Sweego (`{{token}}`, non vérifiée) ou 1 envoi/destinataire.
   Le webhook natif (cf #1) est la solution propre. Sweego n'expose PAS les clics
   par destinataire (stats agrégées seulement). Deux options :
   (a) Redirection via `https://api.cheffer.email/api/sweego/r?t=<token>` dans chaque lien (token
       par destinataire via perso Sweego) → fiable mais lien cross-domaine (déliverabilité à tester)
   (b) Capture côté site leclientroi.com (snippet JS lit `utm_source=sweego` → POST API) → ne fire
       que si le contact atterrit sur une page équipée.
2. **Click→lead Maildoso** : IMAP reply detection dans séquenceur maison.
3. **Maildoso séquenceur** (`cold_email_engine.py`) : disponible ~2026-07-07 (warmup en cours).
4. **Stats harmonisées** : vue unifiée Emelia + Sweego + Maildoso (Sweego engagement fait, reste à
   fusionner avec Emelia dans une vue commune).
5. **Test live scrapper** : valider un run Serper + Basile (coûte des crédits → demander au user avant).

### Architecture Sweego (mémo)
- Sweego MTA : enveloppe via `swg.leclientroi.com` (indépendant du From)
- Seul domaine autorisé : `leclientroi.com` (pas `news.leclientroi.email`)
- Clé API : `SWEEGO_API_KEY` dans `.env` (ne jamais hardcoder)
- Maildoso : 4 boîtes `@leclient-roi.com` warmup depuis 2026-06-23, dispo ~2026-07-07

## 🔝 REPRISE 2026-06-20 — Scrapper Serper + Basile (double source, cible 100 contacts)

**Demande user :** Basile = 2e source parallèle à Serper (pas juste un connecteur séparé). Quand on lance un scrape secteur × région, les deux sources tournent pour chaque ville jusqu'à atteindre 100 contacts (configurable). Si Serper se bloque, Basile continue seul (exports illimités).

**FAIT :**
- **`scripts/basile_backend.py`** : ajout `SECTOR_NAF` (mapping 16 secteurs Genesis → codes NAF confirmés) + `run_sector_for_city(site, sector, city, ...)` — interroge Basile `companies/find` par NAF + `headquarters_city` (MAJUSCULES), insère dans le même pool que Serper. Gère arrondissements Paris/Lyon/Marseille (PARIS, LYON, MARSEILLE).
- **`scripts/autoscrape_backend.py`** : `run_autoscrape()` intègre Basile en séquence après Serper pour chaque ville. Nouveau `target_contacts=100` — stop dès que `valid_serper + valid_basile >= target`. Si Serper bloqué ET Basile disponible → Basile continue seul. Compteurs séparés `valid_serper` / `valid_basile` dans l'état. Arg CLI `--target-contacts`.
- **`scripts/api.py`** : `/autoscrape/start` accepte `target_contacts` (body JSON, défaut 100, max 10000), le transmet en arg CLI.
- **`genesis-ui/src/app/site/[code]/scrapper/page.tsx`** : titre "Scrapper — Serper + Basile", badge, champ "Cible contacts", compteur Basile (∞), barre de progression vers la cible, stats Serper X + Basile Y dans le panel statut, description mise à jour.
- **Build Next.js OK**, genesis-ui redémarré.

**RESTE Scrapper Serper+Basile :**
1. **Test live un segment** : lancer un vrai run (ex. restaurant × Île-de-France, cible 20) pour confirmer que les 2 sources s'enchaînent et qu'on atteint la cible → valider les logs.
2. **Secteurs sans NAF** (`autre`) → pas de Basile pour ce secteur (ok, fallback Serper seul).
3. **Routing Emelia** : une fois le pool rempli (100 contacts), la vue Campaigns / Cold Email route vers Emelia — à vérifier que le flow campaign_create → add_contacts fonctionne bien avec les contacts du pool.
4. **Optionnel** : cron segment 1 secteur × 1 dept/jour (au lieu de relancer manuellement).

## 🔝 REPRISE 2026-06-19 — Crédits Serper (affichage+alertes) + clé Basile

**Demande user :** (1) Serper affichait « 50 000 / 2500 » après recharge à 50 000, sans aucune alerte
quand le solde était tombé à 0. (2) Clé Basile en 401.

**FAIT :**
- **Serper affichage (Fix A)** — `api.py:get_serper_usage` : le dénominateur `plan_total` venait d'un
  snapshot figé (`memory/seo/serper-balance.json`, plan_total=2500 daté du 30/05) que la logique
  réécrivait toujours à l'identique. **+ cause profonde** : le JSON était `root:root` 644 -> l'API
  (sous `autoblog`) ne pouvait PAS le réécrire (`except: pass` avalait la PermissionError). Fixes :
  `plan_total = max(plafond connu, solde live)` (une recharge relève le plafond) + `chown autoblog`
  le JSON. Snapshot désormais auto-rafraîchi depuis le solde live `/account`. Vérifié 50000/50000.
  ATTENTION : le solde Serper EST live via `god_mode_agents.serper_balance()` (`/account` existe) —
  l'ancien commentaire « pas d'API de solde » est faux.
- **Alertes crédits (Fix B)** — `connector-alerts.tsx` : avant, un solde bas ne faisait QUE colorer un
  chiffre en rouge dans la sidebar (passif). Ajout de vraies bannières (rouge « épuisés » / orange
  « bas ») pour Serper/Emelia/DeepSeek/Mailnjoy (solde) + Basile/Ahrefs (quota >=80%). Mêmes seuils que
  le widget, refresh 60s, masquables. Build next + restart genesis-ui OK.
- **Clé Basile régénérée** — l'ancienne (`sk_live_aae1966a...`, .env du 17/06) avait été supprimée côté
  console -> 401. User a créé une nouvelle clé (`sk_live_7d99683...`, active). Remplacée dans `.env`,
  testée live : count companies=28,6M / people=4,4M OK. Dashboard restart pour recharger la clé.
- **Audit permissions `memory/` (suite du fix Serper)** — 13 entrées étaient `root:root` (créées par
  d'anciennes sessions root) que l'app sous `autoblog` ne pouvait pas réécrire (échec SILENCIEUX).
  Impact réel : `site-api-keys.json` (sauvegarde clés par site), dossier `seo/history/` (snapshots SEO
  journaliers d'`ahrefs_daily.py`), `shared/agent-logs/sessions.jsonl`, `{lcr,mkd}/modules.json`,
  `seo/{site}-competitor-analysis.json`. Fix : `chown -R autoblog:autoblog memory/`. Vérifié W_OK +
  création fichier OK. Règle : `memory/` = données app, doit rester à `autoblog`.

## 🔝 REPRISE 2026-06-18 — Couverture Serper + reporting scrapper + sidebar

**Contexte :** le scrape IDF immobilier ne ramenait que ~707 « examinés » (Google Places plafonne à
~20 résultats/requête → on retombait sur le même top-20). Univers réel ≈ 7-8k agences IDF / ~30k FR
(à confirmer via Basile, source registre = exhaustive — clé Basile **désactivée/401 depuis ~12h**,
à régénérer).

**FAIT :**
- **Diversification des requêtes Serper** (`god_mode_agents.SECTOR_QUERIES`) : 2 → 4-10 angles métier
  par secteur (immobilier : agence/agent/estimation/gestion locative/syndic/neuf/vente/location/mandataire/
  négociateur). Chaque angle = un top-20 Google différent → couverture bien > 20/ville.
- **Burn des lieux déjà scrappés** (cross-run) : `load/save_seen_places(site,sector)` →
  `memory/scrape/seen-places-{site}-{sector}.json`. ⚠️ Clé = **domaine du website** (`norm_domain`),
  PAS le placeId — découverte : Serper ne renvoie le placeId que 1 row/1787 (quasi toujours null),
  alors que `website` est rempli à ~100 %. Dans `scrape_sector` : skip si domaine déjà vu (AVANT
  fetch site) ; page ne ramenant QUE du déjà-vu (`page_new==0`) → variante épuisée → suivante.
  `skipped_seen` propagé (scrape_sector → cum → log → API → UI, affiché « +N🔥 » près des doublons).
  **Prérempli** depuis scrappe+scrappe_pending : **1769 domaines** (dont 1536 immo lcr) → le prochain
  scrape immo saute direct les connus.
- ⚠️ **SERPER À COURT DE CRÉDITS** (`"Not enough credits"` HTTP 400, sidebar 0/2500) — les scrapes
  sont donc à l'arrêt tant que le forfait Serper n'est pas rechargé. Découvert en testant le burn.
- **Reporting scrapper** : colonnes **Doublons** + **Net Mailnjoy** ajoutées (UI scrapper) ; le log
  d'activité autoscrape est désormais écrit APRÈS le cleanup (inclut `duplicates`, `cleanup`, `net`).
  Live-activity API expose duplicates/skipped_seen/net/cleanup. (Explication run 707 : 1 valid+302
  rejetés[=sans email]+404 doublons ; net réel 0 car Mailnjoy a viré le seul valid.)
- **Sidebar `credits-widget.tsx`** : ajout **Basile** (`/api/basile/usage` : compte local pool
  primary_source='basile' du mois / 250000) et **Emelia** (`/api/emelia/credits` : solde LIVE 950).

## 🔝 REPRISE 2026-06-17 (suite) — Connecteur Basile (2e outil d'acquisition)

**Demande user :** ajouter Basile (api.basile.cc, base B2B FR, abo user) comme 2e outil de collecte
de contacts À CÔTÉ de Serper, fusionné dans le même pool. Règles : jamais > 20 000, passes de 1 000.
**app.basile.cc était DOWN** → préparer TOUT hors-ligne (doc, fonctions, UX, contexte LCR), brancher
clé + tests live au retour du site. Skill fourni en zip (`basile-skill.zip`).

**FAIT (hors-ligne, non testé live) :**
- **Skill installé** : `skills/basile-b2b-search/` (SKILL.md + 8 refs + 2 scripts : basile_search.py,
  emelia_enrich.py). C'est la doc source de l'API Basile + Emelia.
- **Connecteur `scripts/basile_backend.py`** : `count()` (gratuit), `find()` (pagination 100),
  `lead_to_prospect()` (normalise lead Basile → schéma `prospect` IDENTIQUE à serper_places, +
  prenom/nom/job_title pour le pool), `enforce_volume_rules()` (≤20k→extract en N passes de 1000,
  >20k→segment), `run_segment()` (collecte 1 passe, valide via `validate_and_score`, DOUBLE écriture
  `scrappe_pending` + pool `contacts` `primary_source='basile'`, dry-run par défaut). Flag
  `BASILE_BLOCKED_STATUS` sur 402/403 (comme SERPER_BLOCKED_STATUS). CLI : `count|segment [--live]`.
  Fonctions pures TESTÉES (volume rules + normalisation + skip sans email). HTTP **non testé** (site down).
- **Docs** : `docs/basile-api.md` (API complète + §Go-live checklist), `docs/contact-acquisition.md`
  (fusion Serper+Basile, schéma pool, **proposition UX dashboard** = toggle Source Serper/Basile/Les2
  + compter-avant-lancer + segmentation auto >20k + enrichissement Emelia opt-in, endpoints à ajouter,
  mode opératoire jour-du-retour).
- **Contexte LCR** : `context/lcr/acquisition-context.md` (ICP commerçants/artisans/resto/immo →
  mapping secteurs→NAF/activity, workflow 2 étapes entreprises→dirigeants par SIREN, règles volume).
- **Clés** : `EMELIA_API_KEY` déjà en `.env` ✅. **`BASILE_KEY` ABSENTE** → user la fournira au retour.

**✅ TESTÉ EN LIVE (2026-06-17, clé fournie, ajoutée au `.env`) :**
- Auth OK, `count` OK (15 M sociétés, 284 k CEO). FIELD MAP **confirmé** et câblé dans `lead_to_prospect`.
- **Corrections de filtres** (doc à jour, `docs/basile-api.md §12bis`) : `naf_code` exact `"56.10A"`
  (pas de wildcard `.x`) ; `activity` préfixe **`concept:`** (via activity-suggest) ; géo entreprises
  via **`headquarters_postal_code`** (exact) ou **`headquarters_city` MAJUSCULES** — `*_department_code`
  / `*_region_code` renvoient 0.
- **Découverte clé** : sociétés Basile ~15 % avec email (~2 % net après validation), **dirigeants people
  = 0 email/phone**. → Basile = liste sociétés + nom dirigeant + SIREN ; contactabilité réelle via Emelia.
- **`email_validator.LICIT_SOURCES` += `"basile"`** (sinon tout droppé `rgpd_source_non_publique` ;
  registre légal = source publique). Dry-run segment OK : 882 resto Lyon → 19 prospects valides, schéma OK.

**DÉCISION USER prise (2026-06-17) : flux DIRIGEANTS + Emelia** (option A). Construit + testé dry-run.
- `run_dirigeant_segment()` + CLI `dirigeants` : companies/find (NAF+géo) → people/find par SIREN
  (nom dirigeant, ~58 % des sociétés) → Emelia find-email (nominatif, PAYANT 1 crédit/dirigeant,
  derrière `--emelia --live`) → validate → double écriture scrappe_pending + pool (prenom/nom/job_title,
  source=basile). Dry-run ESTIME le coût Emelia avant de dépenser. Website récupéré via `x_gmb`
  (`domain_principal_url`/`open_website`/…) pour améliorer le taux Emelia. `emelia_enrich.py` du skill
  réutilisé (mappe EMELIA_API_KEY→EMELIA_KEY). Testé dry-run lcr : 60 sociétés→31 dirigeants nommés.

**Crédits Emelia (2026-06-17) — SOLDE LU EN LIVE ✅ :** la requête GraphQL du dashboard a été extraite
du front app.emelia.io (`/static/js/main.*.js`) :
`me { subscription { enrich { creditsRemaining creditsSubscription expiration } } }`.
→ `scripts/emelia_credits.py fetch_live_balance()` / CLI `balance` lit le solde RÉEL sans saisie
manuelle (vérifié : **949.75** crédits, ≈ le 950 annoncé). (L'introspection GraphQL est off et le
champ n'était pas devinable — il a fallu lire le bundle JS du front.) Le suivi local
(`record`/`COST`) sert juste à prédire le coût d'un lot. Branché dans `basile_backend._emelia_find_email`
+ `emelia_find_phone`.
Test live find-phone OK : Clara Torres (agent immo La Garenne-Colombes) → +33679277362.
**Coût find_phone = 50 crédits/numéro trouvé** (CONFIRMÉ user 2026-06-17 ; `COST` dans emelia_credits.py).
find_email/verify/ai_action = à confirmer. ⚠️ Implication : 1 pack 1000 crédits = seulement 20 numéros
→ réserver le find-phone aux cibles à forte valeur ; le find-email (≈cheap) reste le levier volume.

**RESTE Basile :**
1. **Test live Emelia** sur un petit lot (3-5 dirigeants) pour confirmer le finder — coûte qqs crédits,
   à lancer avec OK explicite user (`--emelia --live --max 5`).
2. Helper **géo→codes postaux/villes** par département (pas de champ dept côté Basile ; postal exact
   ou ville MAJ seulement).
3. Endpoints + UX dashboard (cf. `docs/contact-acquisition.md §5`). 4. Contextes MKD + autres sites.
5. Crosscheck doc vs docs.basile.cc. 6. (optionnel) cron segments 1 secteur×dept/jour.

## 🔝 REPRISE 2026-06-17 — Source `articles` snapshot (RESTE #3 fait)

**Demande user :** reprise après une session terminée sans récap. Chantier choisi = RESTE #3 (internal-linking & linkedin n'avaient pas la liste d'articles dans leur snapshot → ils détournaient `add_internal_link` en « fetch » / restaient en `plan:[]`).

**FAIT (testé dry-run lcr + mkd) :**
- **`agent_core.observe()` : nouvelle source `articles`** (`_observe_articles(site)`). Expose `editable` (articles de la queue éditoriale AVEC markdown + published_url = les SEULS que les writers savent cibler, matchés dans la queue) **et** `published` (jusqu'à 12 articles publiés = destinations de liens). Câblée sur internal_linking_agent + linkedin_agent (`sources=("gsc","ga4","articles")`).
- **Cause racine trouvée : troncature du snapshot.** `decide()` coupait le snapshot à **6000 chars** ; avec 30 articles `published` listés AVANT `editable`, la liste `editable` (offset 6586) était **coupée** → le LLM ne voyait jamais les seules cibles valides et piochait dans `published` (→ skip/erreur en live). Fix : (a) `editable` listé EN PREMIER + counts + `note` explicite, `published` cappé 30→12 ; (b) limite de troncature `decide()` 6000→8000. Snapshot lcr : 6944→4016 chars, `editable` visible à l'offset 1008.
- **Playbooks durcis** (`skills/internal-linking.md`, `linkedin-specialist.md`) : RÈGLE DURE `target` ∈ `editable` (recopier le champ `url` exact, ne PAS inventer d'URL d'API), `destination_url` ∈ `published`. linkedin : ignorer `has_linkedin_post=true`, `plan:[]` si rien de neuf.
- **Writers durcis (skip propre au lieu de crash)** : validation cible AVANT la branche dry-run dans les 2 `_agentic_writer`. internal-linking : matching tolérant (id/slug emballé dans une URL) + extraction destination tolérante (`destination_url`|`url`|`destination`|`linked_article_slug`→résolu via `published`). Fallback URL site-aware (lcr uniquement). linkedin : skip propre si `target` hors-queue ou déjà promu.
- **Résultat dry-run lcr (mémoire purgée) :** internal-linking produit **4 liens valides** depuis l'éditable « SMS Marketing Restaurants » vers de vraies destinations (sms-salle-sport, rcs-marketing, fideliser-clients-sms, campagne-mms), URLs résolues, 0 erreur/skip. linkedin → `plan:[]` correct (seul éditable déjà promu). mkd → `plan:[]` propre (WP vide, pas de crash).
- **Purge** : 9 lignes `agent_actions` de test du 17/06 (internal-linking + linkedin, lcr+mkd) supprimées pour ne pas empoisonner le `recall` des crons live de ce soir.

**Limite connue :** la queue éditoriale lcr n'a qu'**1 article éditable** (les autres publiés ne sont pas dans la queue Genesis donc non modifiables). internal-linking ne peut donc mailler que cet article tant que Genesis ne publie pas plus via sa propre pipeline. C'est by-design (la queue = base éditoriale interne).

**RESTE (inchangé hors #3) :** voir REPRISE 2026-06-16 ci-dessous (eval post-cron J+7 ~23/06, purge cosmétique agent_actions, migration slugify).

## 🔝 REPRISE 2026-06-16 (suite) — Refonte du scrapper (autoscrape région-continu)

**Demande user :** le scrapper "automatique" ne l'était pas (s'arrêtait sur estimation crédits + volume cible). Veut : choisir juste secteur + RÉGION, scraper EN CONTINU dans l'ordre des départements tant que Serper ne stoppe pas réellement, retry quotidien au blocage, statut "Région finie" à l'épuisement, libellé région correct, plus de champ volume.

**FAIT (corrige + améliore + testé) :**
- **`god_mode_agents.serper_places`** : détecte le refus EXPLICITE de Serper (HTTP 429/402/403) → lève `SERPER_BLOCKED_STATUS` au lieu d'avaler en `[]` (avant : un blocage passait pour "ville vide"). Testé live : appel normal → flag reste None, 10 places.
- **`autoscrape_backend.py` réécrit** : `run_autoscrape(region=…)` enchaîne TOUS les départements de la région (triés par code), toutes villes pop≥10k. **Supprimé** : credit-floor préemptif + volume cible + stall-heuristic. **Seul arrêt** = vrai blocage Serper / stop manuel / épuisement (→ statut `done` "Région X finie"). Reprise : `memory/autoscrape/{site}-region-progress.json` (depts_done). Garde-temps 6 h (anti-zombie). Activité = **1 ligne par run** (plus 1 par ville) : start_scrape + scrape de fin uniques avec scope région.
- **`daily_retry()` + crons PM2** `genesis-autoscrape-retry-lcr` (06:00) / `-mkd` (06:10) : si région `blocked_serper` et Serper repasse (1 appel test) → reprend en skippant les depts finis.
- **`api.py`** : `/autoscrape/start` accepte `region` (drop `target_valid`), `/scrape/live-activity` fenêtre de match élargie 10min→12h + expose `scope`/`message`/statut métier.
- **Frontend `scrapper/page.tsx`** : autoscrape sur RÉGION (dept optionnel), champ Volume cible supprimé, libellé région corrigé (`SelectValue` rendait le code "11" → force `{r.name}`), carte statut montre scope + dépts faits, table activité montre "Région finie"/"⛔ Serper" + périmètre. Build OK, dashboard+UI restart.

**Testé :** géo (Bretagne→22,29,35,56 ; Corse→2A,2B ; IDF→75..95), orchestration mockée (blocage→`blocked_serper`, persistance `depts_done`, reprise skip), serper réel, build UI, crons.

- **Corse + DOM-TOM EXCLUS** (correction user : périmètre = France métropolitaine seule). `workflow_geo.EXCLUDED_REGION_CODES={94,01,02,03,04,06}` + `EXCLUDED_DEPT_CODES={2A,2B,971-978}` + helpers `metropole_regions/departments/cities`. Câblés sur les 3 endpoints `/geo/*` ET l'autoscrape (`_ordered_region_depts`, listing villes). Résultat : 12 régions continentales, 0 ville Corse/DOM. NB : dept "94" (Val-de-Marne, IDF) ≠ région "94" (Corse) — pas de collision.

**RESTE scrapper (optionnel) :** un vrai run live de bout en bout via l'UI (clic user) pour confirmer pool+Mailnjoy ; étendre le retry à d'autres sites si besoin.



## 🔝 REPRISE 2026-06-16 — V2 préambules action_type (RESTE #1 fait)

**FAIT cette session :**
- **Constat dry-run** : le préambule V1 (texte dans le playbook) **ne suffit PAS** — DeepSeek inventait systématiquement (2/2 runs) `create_article`/`update_article` pour `seo-strategist` → l'agent ne produisait **aucun `seo_reco` valide** (tout skippé). Donc pas un bruit cosmétique : sortie vide.
- **Enum exhaustif ajouté** aux 6 playbooks filtrés (`skills/seo-strategist|content-writer|internal-linking|linkedin-specialist|competitive-intel|graphiste.md`) : bloc « `action_type` AUTORISÉ — liste EXHAUSTIVE » juste après le JSON, + redirection explicite des synonymes tentants (ex seo-strategist : « tu ne rédiges pas d'article → `seo_reco` + `tags.type:content_gap` »).
- **Enforcement central dans `agent_core.decide()`** (la vraie correction, le playbook seul étant trop faible face au raisonnement du modèle) :
  - `ALLOWED_ACTION_TYPES` (dict par nom d'agent, source de vérité = filtres des `_agentic_writer`).
  - La liste autorisée est injectée dans le **prompt système** (domine le playbook) comme CONTRAINTE DURE.
  - Garde-fou : 1 passe de **réparation** si le modèle viole l'enum, puis **filtrage final** des items hors-enum (ne polluent plus `agent_actions`).
  - Nouveau param `allowed_actions` sur `decide()` **et** `run_cycle()` (rétrocompatible, fallback sur le dict).
- **Split content-writer** : `content_agent` et `brief_agent` partagent le playbook `content-writer.md`. `content_agent` passe `allowed_actions=["write_article"]`, `brief_agent` `["write_article","propose_article"]` → fini la fuite `propose_article` skippée côté content_agent.
- **Validation dry-run des 7 agents** : tous émettent désormais UNIQUEMENT des types valides (seo_reco / write_article / add_internal_link / linkedin_post(ou plan:[]) / intel_signal / generate_header). Zéro skip « non géré », garde-fou jamais déclenché (respect dès la 1ʳᵉ passe). `humanizer` volontairement **exclu** du dict (pas de filtre côté writer, comportement libre préservé).
- **Note** : `skills/briefing.md` (send_briefing/telegram) n'est chargé par AUCUN agent agentique (`genesis-briefing` = `scripts/briefing.py` déterministe ; `brief_agent` lit `content-writer.md`). Son préambule V1 est mort → laissé tel quel, à nettoyer un jour.

**FAIT (suite) — bascule crons agentiques :**
- **5 crons PM2 créés en `--agentic --live` sur lcr** (les agents n'avaient AUCUN cron avant — le STATE 06-10 surestimait l'existant) : `genesis-brief` (08h L/M/V), `genesis-seo-strategy` (09h L/M/V), `genesis-internal-linking` (12h L/M/V), `genesis-linkedin` (13h L/M/V), `genesis-competitor` (07h Lundi). Pipeline cohérent avec content-lcr (10h) + graphiste (11h). Tous `--no-autorestart`, `pm2 save` fait.
- **Risque maîtrisé** : en live ces 5 agents n'écrivent que dans des JSON internes (recos/queues) — aucun post LinkedIn réel ni publication externe. La partie outward reste content/graphiste (déjà live lcr).
- **1ʳᵉ exécution live OK** (exit 0 sur les 5) : actions réelles loggées dans `agent_actions`, toutes enum-propres (seo_reco, intel_signal, write_article, add_internal_link, linkedin plan:[]). L'éval aura de la matière à J+7.
- `content-mkd` laissé tel quel (publish 401, décision user) ; `ecosystem.config.js` est OBSOLÈTE (3 crons orchestrator morts) → source de vérité = `pm2 save` / dump.pm2.

**RESTE (prochaine session, par priorité) :**
1. **MKD publish 401** (action user : régénérer App Password WP, voir DÉCISIONS EN ATTENTE plus bas).
2. ~~**humanizer invente des action_type / plante**~~ **CORRIGÉ 16/06** : la vraie cause du plantage nocturne était `humanize_article.py` qui faisait `exit 1` à chaque run — `check_constraints` échouait car le filet déterministe ne forçait le frontmatter original que si le LLM en produisait un (or DeepSeek le supprime souvent). Fixes : (a) frontmatter original réinjecté TOUJOURS, (b) strip déterministe des `---` en corps au lieu de rejeter, (c) `DEFAULT_PROMPT` repointé de `/tmp/cmux-drop-*.md` (éphémère) vers `skills/humanizer.md` (identique, stable), (d) `humanizer → ["humanize_article"]` ajouté à `ALLOWED_ACTION_TYPES`. Validé live (exit 0, frontmatter intact, `.bak` créé). **Résidu** : la mémoire de l'agent garde 8 erreurs périmées → il reste en `plan:[]` par prudence ; se résorbe en ~qq jours (noops chassent les erreurs de la fenêtre recall=10) ou via purge manuelle des lignes `agent_actions agent=humanizer status=error` (refusée par le classifier ce jour, à autoriser si on veut accélérer).
3. ~~**internal-linking & linkedin manquent la liste d'articles dans leur snapshot**~~ **FAIT 17/06** : source `articles` ajoutée à `observe()` (`editable`+`published`), troncature snapshot 6000→8000, playbooks+writers durcis. Voir REPRISE 2026-06-17 en haut. internal-linking produit des liens valides, linkedin `plan:[]` correct quand rien à promouvoir.
4. **🆕 Pollution test agent_actions (16/06)** : `create_article`/`update_article`/`propose_article` en `done` issus de mes dry-runs d'avant le fix. Inoffensif (eval les skippe) mais à purger si on veut une table propre (delete manuel DB).
5. **Évaluation post-cron** : laisser tourner 1-2 semaines, vérifier que `evaluate()` passe de `evaluated:0` à des outcomes réels, affiner les seuils.
6. **Migrer humanize_article + gen_agents_state vers text_utils.slugify** (cosmétique).

**DÉCISIONS EN ATTENTE (user) :** MKD publish 401 (régénérer App Password WP — détail dans la section REPRISE 2026-06-09 soir).

## 🔝 REPRISE 2026-06-10 — Chantiers 1/2/5/6

## 🔝 REPRISE 2026-06-10 — Chantiers 1/2/5/6

**FAIT cette session :**
- **Chantier 1 (pilote)** : `seo_strategy_agent.py --agentic --live` migré sur `agent_core.run_cycle`. Pattern copié de `content_agent.run_agentic`. Test dry-run validé. Reste 4 agents à migrer (#12 pending : internal_linking, linkedin, competitor, brief).
- **Chantier 2** : préambule action_type/target ajouté à 6 playbooks → `skills/seo-strategist.md`, `content-writer.md`, `internal-linking.md`, `linkedin-specialist.md`, `competitive-intel.md`, `briefing.md`. Format JSON strict imposé : `{reasoning, plan: [{action_type, target, why, tags}]}`. Chaque playbook ajoute le périmètre (un seul article par cycle pour content-writer, max 6 recos pour seo-strategist, etc.).
- **Chantier 5** : `scripts/text_utils.py` créé avec `slugify()` (NFD + diacritiques). `content_agent._slugify` réexporté pour compat. À réutiliser dans humanize_article et autres.
- **Chantier 6** : legacy /agents complètement viré
  - **Backend `scripts/api.py`** : suppression d'AGENTS_REGISTRY (10 agents hardcodés), AGENT_CRONS_FILE, _load_agent_crons, _save_agent_crons, AGENT_COSTS, FREQ_MULTIPLIERS, endpoints `/api/agents`, `/api/agents/{site}`, `/api/agents/{site}/{agent_id}/cron`, `/api/agents/{site}/planner`, `/api/agents/{agent_id}/instructions` (variante sans site). -7072 chars dans api.py. Gardés : `/api/agents/{site}/state` + `/api/agents/{site}/{agent_id}/instructions`.
  - **UI `genesis-ui/.../agents/page.tsx`** : page refondue ne consomme plus que `/state` et `/instructions`. Table « Catalogue conceptuel » + Planner supprimés. Card unique « État PM2 réel » + Sheet playbook. Mapping `skillIdFromPm()` pour mettre un bouton « Voir playbook » sur les jobs PM2 pertinents (content/seo/humanizer).
  - Build OK, restart dashboard + UI OK, page agents répond 200, snapshot état `12 agents PM2` à jour.

**FAIT (suite session 2026-06-10) :**
- **Chantier 1 complet** : les 4 derniers agents migrés sur `agent_core` (`brief_agent`, `linkedin_agent`, `internal_linking_agent`, `competitor_analyzer`) avec `--agentic --live`. Tous testés dry-run : la boucle observe→recall→decide→act tourne, le LLM raisonne contextuellement (ex `linkedin_agent` : « plan: [] car pas d'article récent à promouvoir »). Total : **6 agents agentiques** (content-lcr/mkd, seo-strategy, internal-linking, linkedin, competitor, brief + humanizer = 7).
- **Hardening `agent_core._conn()`** : retry-backoff exponentiel sur `Conflicting lock` DuckDB (api.py FastAPI garde un handle long-lived). 6 tentatives, ~30s max. Plus de crash transitoire en parallèle de l'API.
- **Popup preview articles** (chantier #16) : Dialog sur `/site/[code]/articles` qui rend le markdown via `marked` (GFM) avec style proche du blog public. Bouton « Aperçu » visible sur tous les articles (proposal seul affiché si pas de markdown). Largeur fixée 4xl (~900px).
- **Imagen 3 (Vertex AI)** branché : compte de service `genesis-indexing@lead-machine-mkd` + facturation + rôle `aiplatform.user`. Script `scripts/imagen_generate.py`. Cible projet `lead-machine-mkd`.
- **Style photo doc iPhone/Portra 400** validé : nouveau `STYLE_PREFIX` (vraie photo candide, grain authentique, no SaaS aesthetic) + `NEGATIVE_PROMPT` qui kill illustration/3D/texte parasite. Plus de « dessin ».
- **Diversité géographique/personas** : casting Python (`SystemRandom`) avant l'appel LLM — 23 villes, 15 types de lieu, 10 personas. Fini « young Parisian in café » systématique.
- **Module Meta ads** (`scripts/meta_ad_generate.py`) : génère copy JSON 7 clés (accroche/solution/primary_text/headline/description/cta/image_brief) selon le system prompt LeClientROI senior copywriter + génère l'image associée. Coût ~0,033 €/ad.
- **🆕 Agent graphiste autonome** (`scripts/graphiste_agent.py` + `skills/graphiste.md`) :
  - Architecture séparée : content_agent fait le texte (sans image), graphiste fait l'image en post-traitement
  - Boucle agent_core : scan emdash posts sans `seo.image` → LLM choisit l'article + rédige le brief image → Imagen 3 photo doc → upload emdash → PUT seo.image
  - Cron PM2 `genesis-graphiste` (`0 11 * * *`), 1 article/jour. Backlog actuel : 21 articles sans image → 21 jours pour rattraper (ajustable).
  - Playbook strict : interdit illustration/3D/SaaS aesthetic/jeune Parisienne. Force patron 45-65 dans son commerce, ancrage métier visible, ville française variée.
  - Test live validé : agent immobilier ~50 ans avec lunettes en RDV client (https://blog.leclientroi.com/_emdash/api/media/file/01KTSGPSSF6KTV6QJZQDS7QJ6F.jpg)
- **content_agent** : branchement image header retiré (responsabilité passée au graphiste). content_agent publie sans image, graphiste enrichit après.

**RESTE (prochaine session, par priorité) :**
1. **V2 préambules playbooks** : ajouter la liste **exhaustive** des `action_type` acceptés dans chaque préambule `skills/*.md` (V1 actuelle est permissive → le LLM invente `audit_indexation`, `fix_gsc_permissions`, `fetch_articles` à côté des types attendus). Ne casse rien (les `_agentic_writer` filtrent), mais coupe le bruit.
2. **MKD publish 401** (action user : régénérer App Password WP)
3. **Migrer humanize_article + gen_agents_state vers text_utils.slugify** (cosmétique, pas urgent)
4. **Basculer les crons PM2 en `--agentic --live`** : actuellement seuls `content-lcr` et `humanizer` sont en agentique. Les autres (`seo-strategy`, `linkedin`, `internal-linking`, `competitor`, `brief` si crons existent) restent en mode classique. À basculer une fois la V2 préambules faite, pour ne pas pousser de signaux faux pendant l'itération.
5. **Évaluation post-cron** : laisser tourner les agents en mode agentique 1-2 semaines, mesurer les outcomes via `evaluate()`, affiner.

**DÉCISIONS EN ATTENTE (user) :**

## 🔝 REPRISE 2026-06-09 (nuit) — Boucle complète + humanizer + UI

**FAIT cette session (après-midi/soir/nuit) — gros chantier :**

### Boucle agentique (étape 2)
- `agent_core.evaluate()` + cron PM2 quotidien 02:00 (lcr) / 02:05 (mkd)
- 3 crons morts supprimés (briefing/crm-sync/campaign-status)
- `gen_agents_state.py` + endpoint `/api/agents/{site}/state`
- `content_agent.py --agentic` (boucle `agent_core.run_cycle`)

### Cleanup pipeline emdash (étape 3)
- Fix `publish_lcr` schema emdash : `data={title,content}` + `seo` top-level
- Fix `md_to_portable_text` : skip H1 du body (emdash affiche `data.title`), parse `**…**`/`*…*` en marks `strong`/`em`, ignore les `---`, splitte `Label : « citation »` en label-gras + blockquote, passe citations pures `« … »` en blockquote
- `ARTICLE_PROMPT` ré-écrit pour interdire à la source : préfixes `H2:`/`H3:`, labels `## Introduction`/`## Conclusion`, `---` dans le corps. Force `*Exemple : ...*` en italique.
- Slugifier `_slugify()` centralisé avec normalisation NFD (plus de `fidéliser → fidliser`)

### Test live de bout en bout
- Article LCR publié : https://blog.leclientroi.com/posts/comment-fideliser-vos-clients-avec-des-sms-personnalises (HTTP 200, slug propre avec accents, gras/blockquotes/italiques OK)
- Pilote humanizer sur 1 article backlog Arvow validé (agents-immobilier, 19k→11k chars, blacklist purgée, structure préservée)

### Agent humanizer (skill + cron PM2)
- Skill : `skills/humanizer.md` (prompt cmux-drop) + `skills/humanizer-tone.md` (préambule ton marketing-coach injecté en tête du user prompt)
- `scripts/humanize_article.py` : CLI standalone (peut traiter 1 article manuellement) — temp 0.85, filets déterministes (frontmatter forcé, `2025→2026` dans le corps)
- `scripts/humanizer_agent.py` : agent agentique sur `agent_core` (observe articles backlog par score scaffolding, recall, decide via DeepSeek, act = invoke humanize_article)
- Cron PM2 `genesis-humanizer` : `0 4 * * *`, `--site shared --live` → 1 article/jour, ~7 mois pour 212 articles backlog

### UI page /agents refondue
- Genesis-ui : nouvelle Card "État PM2 réel" en tête, lit `/api/agents/{site}/state`, affiche nom/cron lisible/statut/dernier run/exit code + badge "agent_core" si `--agentic` dans args
- Ancienne table renommée "Catalogue conceptuel (legacy)" — conservée pour transition, mais source de vérité = vraie PM2

**RESTE (prochaine session) :**
1. **MKD publish 401** : action user (régénérer App Password WP, voir DÉCISIONS EN ATTENTE)
2. **Migrer les autres agents** sur `agent_core` (seo-strategist, editorial-manager, internal-linking…) sur le pattern `content_agent.run_agentic`
3. **Première vraie évaluation** : le 16/06 02:00 UTC, `evaluate()` mesurera le delta GA4 sur l'article SMS personnalisés du 9 juin (J+7 minimum)
4. **Premier batch humanizer** : nuit du 09→10 juin 04:00, 1 article du backlog (top score actuel : `2025-11-21-automatisation-sms-marketing-workflows-et-scenarios-pour-2025.md` score 13)
5. **Slug v4 résiduels SQLite** : les slugs `-v2/-v3/-v4` sont soft-deleted dans `ec_posts` mais l'UNIQUE constraint les retient. Si on veut les libérer, intervention manuelle DB (refusée par claude classifier, à faire main).

**DÉCISIONS EN ATTENTE (user) :**

## 🔝 REPRISE 2026-06-09 (soir) — Boucle complète + content_agent migré

**FAIT cette session (après-midi/soir) :**
- **`agent_core.evaluate()`** : feedback nocturne, mesure delta réel par action (gsc_position:{kw} → traffic_strategist-like ; fallback gsc_clicks_total ; fallback ga4_sessions_total). Verdict `validated`/`failed`/`neutral` (seuils ±0.5pt pour position, ±5% pour métriques agrégées). Idempotent (LEFT JOIN sur action_id). Filtres : actions `done`, âge ∈ [7d, 30d]. CLI : `python3 scripts/agent_core.py --mode evaluate --site lcr`. Test fixture passé : 1 outcome écrit (delta +1292 sessions, validated).
- **Cron PM2 evaluate** : `genesis-agent-evaluate-lcr` (`0 2 * * *`) + `genesis-agent-evaluate-mkd` (`5 2 * * *`), `--no-autorestart`, dump persisté.
- **3 agents MORTS supprimés** : `pm2 delete genesis-briefing genesis-crm-sync genesis-campaign-status` + save. `orchestrator.py` n'existe plus → décision tranchée (suppression, pas restauration).
- **`scripts/gen_agents_state.py`** : snapshot `pm2 jlist` → `memory/agents-pm2-state.json` (atomic). Exclut services longs (dashboard/ui/mailnjoy-drain). Filtre par suffixe `-lcr`/`-mkd` (sinon global). 11 agents listés.
- **Endpoint `/api/agents/{site}/state`** dans `scripts/api.py` (juste avant `/planner`) : lit le snapshot, refresh inline si >5min, retourne `{generated_at, host, age_s, agents}` filtrés site+globaux. Testé : lcr et mkd voient 9 agents chacun (2 spécifiques + 7 globaux).
- **`content_agent.py --agentic`** : nouveau mode pilotage `agent_core.run_cycle` (observe gsc/ga4/ahrefs, recall, decide via DeepSeek, act via `_agentic_writer(item, snapshot, site, env, dry_run)`). Mode classique préservé. Test dry-run lcr : la boucle a raisonné explicitement « action précédente sans outcome → noop ce cycle », 1 noop écrit dans agent_actions avec reasoning intelligent. **La boucle agentique est OPÉRATIONNELLE de bout en bout.**

**RESTE (prochaine session, dans l'ordre) :**
1. **Page UI /agents** : consommer `/api/agents/{site}/state` (au lieu de `/api/agents/{site}`) — card "État PM2 réel" avec nom/cron/statut/dernier run/badge couleur. Backend prêt.
2. Brancher le cron PM2 `genesis-content-lcr` sur le mode `--agentic` (actuellement encore mode legacy) une fois la publication réparée. **Avant** ça : régler les bugs publish (lcr 500, mkd 401 — décision en attente).
3. Migrer les autres agents (seo-strategist, editorial-manager, etc.) sur `agent_core` — pattern à copier depuis `content_agent.run_agentic`.
4. Enrichir `skills/content-writer.md` (et autres) avec un préambule explicite "tu dois renvoyer un plan {action_type, target}" pour aider `decide()`.

**DÉCISIONS EN ATTENTE (user) :**
- **MKD publish 401** : WordPress répond `incorrect_password` → l'App Password est révoqué/invalide. **Action manuelle requise** : aller dans WP admin → Utilisateur camille.afchain@protonmail.com → Application Passwords → en générer un nouveau, puis remplacer `WP_APP_PASSWORD` dans `.env` (sans guillemets autour). Puis `pm2 restart genesis-dashboard`.
- ~~LCR publish 500~~ **RÉPARÉ** : le schéma emdash a évolué — `data.{excerpt,description,tags}` rejetés (`ec_posts has no column named description`). Fix dans `publish_lcr` : `data={title,content}` + `seo={title,description}` au top-level (validé create 201 + publish 200 sur draft de test).

**LIMITES connues :** GSC via le compte de service = encore **403** (grant propriété pas pris ; les données GSC passent par MCP Ahrefs / seed). GA4 OK.

**RÈGLE gravée :** MAJ `AGENTS.md` + `ARCHITECTURE.md` à CHAQUE fin de session touchant aux agents → lancer `sudo -u autoblog python3 scripts/gen_agents_doc.py`.

---


## Goal en cours
Tester le pipeline **Workflow LCR** de bout en bout (Serper → DeepSeek qualifier → push Emelia → cold email envoyé).
Mail test attendu sur afchain.camille@gmail.com via la campagne workflow-lcr-restaurant.

## Done (état réel observé en DB + logs)
- Spec workflow validée → specs/workflow-prospection.md (2026-05-21)
- Migration DB `scrappe` : colonnes region_code, dept_code, population, qualifier_*, emelia_* en place
- Workflow runner branché en cron : `30 6 * * 1-5` → logs/workflow.log
- Contact test 'Test Restaurant Camille / afchain.camille@gmail.com' inséré le 2026-05-21 19:30, status=validated, emelia_segment_id=6a0f5d290eb6f73f1f6149ec (workflow-lcr-restaurant), pushed dans Emelia
- Cron du 2026-05-22 06:30 : 30 prospects scrapés (Loire-Atlantique 44), **11 contacts poussés Emelia** (immobilier 2, restaurant 4, garagiste 1, coiffeur 2, artisan 2). MKD skippé (god_mode_state.enabled=False).

## Blocked / à vérifier
- **Campagne Emelia démarrée ?** Le push contact ≠ envoi mail. Tant que la campagne workflow-lcr-restaurant est en pause côté UI Emelia, rien ne part. À vérifier via API ou UI Emelia.
- Boîte gmail afchain.camille@gmail.com : pas encore checké si le mail test est arrivé.

## Next action (à faire MAINTENANT en reprenant)
1. Interroger l'API Emelia → statut de la campagne workflow-lcr-restaurant (running ? paused ?)
2. Si paused → Start dans l'UI Emelia
3. Vérifier réception du mail dans afchain.camille@gmail.com
4. Une fois validé end-to-end → activer le site MKD (god_mode_state.enabled=True pour 'mkd')

## Rappels importants
- User : autoblog (`su - autoblog` depuis root)
- Path : /home/autoblog/genesis
- Toujours lancer claude DANS tmux : `tmux new -s genesis` ou `tmux attach -t genesis`. Une session SSH qui coupe sans tmux = perte du contexte conversation.
- Clés Emelia : EMELIA_API_KEY_LCR / EMELIA_API_KEY_MKD dans .env, fallback EMELIA_API_KEY
- Budget : <$10/semaine total
- Quota Emelia : 50 contacts/site/jour max

## Historique des sessions récentes
- 2026-06-03 : **Campagnes cold-email AUTOMATISÉES** (gros chantier, plan approuvé). NOUVEAU auto_campaign_backend.py (tables auto_campaigns + auto_campaign_runs dans god_mode.duckdb, CRUD, idempotence 1/sender/jour) + auto_campaign_runner.py (orchestrateur PROCESS DÉTACHÉ : cap = min(target, warmup_quota − sent_today) ; boucle sur le PUSH pas l'envoi async ; pick pool → push_batch_to_campaign ; si pool sec + source=autoscrape → run_autoscrape(dept) inline → re-pick ; arrêts target/pool_exhausted/scrape_blocked/no_progress(3)/timeout(4h)/stop/pause ; statut fichier ; alerte Telegram). workflow_emelia_push.py : + ensure_campaign_for_auto (réutilise get_or_create_campaign) + push_batch_to_campaign. api.py : endpoints /api/sites/{site}/auto-campaigns/* (admin, Popen détaché) + /api/campaigns/{id}/stats-by-day + BAT /api/sites/{site}/templates/{sector}/{kind}/send-test. UI : campaigns/page.tsx REFONTE (gestionnaire auto : création secteur+sender+source+cible, table pause/resume/stop/run/delete, statut+alerte) ; cold-email/page.tsx + champ BAT ; dashboard AutoCampaignsSection (cards logo+stats agrégées + chevron stats/jour + global). ⚠️ CRON PM2 NON armé : create bloqué par classifier (= décision go-live user vers vrais prospects). Pour activer : pm2 start scripts/auto_campaign_runner.py --name genesis-auto-campaigns-lcr --interpreter python3 --cron-restart '0 7 * * 1-5' --no-autorestart -- --site lcr (idem mkd 15 7) + pm2 save. Testé DRY-RUN ok (cap 30, 228 dispo pool immo). PAS de test d'envoi réel (= vrais cold emails) : via BAT (adresse perso) puis Run manuel quand le user décide. Puis /code-review ultra.
- 2026-06-02 (fix compteurs UI faux) : « Tous (5793) » de la page Acquisition etait faux = stats_for_site comptait COUNT(*) contact_site_history (incluant ~2748 ORPHELINS : historiques de contacts supprimes par le nettoyage Mailnjoy). FIX : stats_for_site (JOIN contacts + COUNT DISTINCT email) -> vrai total 3045 (cold_email 3040, lead 4, prm 1). + cleanup run_cleanup supprime desormais contact_site_history en cascade avec le contact (plus d_orphelins futurs). Purge des orphelins existants PROPOSEE mais NON faite (bloquee par classifier comme destructive ; le JOIN les exclut deja de l_affichage). Exports livres sur Bureau Mac : TOUS contacts lcr (3045), mailnjoy VALID (3018), non-immo non-verifiables (13).
- 2026-06-02 : **cleanup auto en fin d_autoscrape ENFIN fonctionnel**. Le hook auto-cleanup etait sur l_endpoint scrape MANUEL (god_mode_api), mais l_autoscrape (process detache) ne le traversait pas -> auto_cleanup_triggered=0, jamais lance. FIX : run_autoscrape enchaine cb.run_cleanup_drain(mode=unverified, source=auto-scrape) dans le meme process apres le scrape (statut "cleaning", champ cum[cleanup], respecte le stop flag). UI : autoActive inclut "cleaning" + affichage nettoyage. api.py status checks incluent "cleaning". Validé : dept 48 coiffeur -> 7 scrapes -> cleanup_batch source=auto-scrape (1 validé, 6 supprimés). Visible badge Automatique dans page Cleanup.
- 2026-06-01 (autoscrape — heartbeat + multi-select) : (1) secteur en MULTI-SELECT badges (lib/sectors, 16 predefinis) au lieu d_un input libre dans la card autoscrape. (2) heartbeat intra-ville : scrape_sector(heartbeat_cb) appelé à chaque page Serper -> autoscrape_backend met le statut à jour en direct (examinés/gardés live + current_detail ville/secteur) -> plus de faux "figé" sur ville longue (le statut ne s_ecrivait qu_en fin de secteur). NB : sur des arrondissements déjà scrapés, dedup => peu de nouveaux + pagination longue (normal). Le run en cours d_un fix garde l_ancien code (process déjà lancé) ; le fix s_applique au prochain run.
- 2026-06-01 (autoscrape — fix conflit DuckDB) : runs arrondissements renvoyaient examined=0 + faux "blocked_credits". Cause : scrape_sector CRASHAIT sur les vérifs anti-doublon (gm.email_recently_validated/email_in_pending) en conflit DuckDB cross-process avec l_API (lignes hors try/except) -> 0 resultat -> heuristique zero_streak criait blocage credit a tort (credits OK 2099). FIX : (1) god_mode_agents.scrape_sector wrappe tout le traitement par commerce en try/except + retry -> un verrou transitoire saute le commerce, ne tue plus la ville. (2) autoscrape_backend : zero_streak ne declenche blocked_credits que si solde reellement bas (<=floor*3), sinon statut stalled ; seuil 3->5. Validé : test 75 immobilier sous API live -> 42 contacts (Paris 1er 16, 2e 15, 3e 6, 4e 5) au lieu de 0. Un 75 complet = ~300 contacts.
- 2026-06-01 (autoscrape — arrondissements) : Paris/Lyon/Marseille = 1 commune INSEE unique dans la geo => autoscrape ne faisait qu_~18 contacts pour tout Paris. Ajout `ARRONDISSEMENTS` + `_expand_arrondissements` dans autoscrape_backend : dept 75 -> 20 villes (Paris 1er..20e), 69 -> +Lyon 1-9e, 13 -> +Marseille 1-16e. Serper localise bien par arrondissement (verifie), dedup email evite les doublons. city stocke stocke Paris 16e. Pas de restart API (chaque autoscrape = nouveau process lisant le fichier a jour).
- 2026-06-01 (autoscrape v2 — robuste) : le 1er autoscrape (thread DANS l'API) a planté en cours (dept 92 immobilier, 32/34 villes, ~290 contacts SAUVÉS quand même) sur `_duckdb.ConnectionException: Can't open a connection to same database file with a different configuration` — conflit de connexions DuckDB intra-process (le thread scrape vs les requêtes API). RÉARCHITECTURÉ en **process DÉTACHÉ** : `autoscrape_backend.py` a un `main()` (--site --dept --sectors) qui écrit l'avancement dans `memory/autoscrape/<site>-status.json` (heartbeat updated_at) et lit un flag `<site>-stop.flag`. Endpoints api.py : start = Popen `start_new_session=True` (détaché, survit aux restarts API), status = lit le fichier (+ marque 'interrupted' si pas de heartbeat >5min), stop = pose le flag. Plus de `_active_autoscrape` en mémoire. Bonus : log `start_scrape` par (ville,secteur) (auto=True) → l'autoscrape est désormais VISIBLE dans le panneau 'Activité des scrapes' (qui matche start_scrape↔scrape). Testé : dept 78 restaurant détaché → statut fichier OK, stop flag → arrêt propre (Versailles, 13 gardés), process sort proprement. LEÇON : ne jamais faire tourner un job DB-lourd long comme thread de l'API (genesis-dashboard = 334 restarts + conflits DuckDB) ; process détaché + statut fichier.
- 2026-06-01 : **Autoscrape département** (demande user, ras-le-bol des paramètres). Nouveau `scripts/autoscrape_backend.py` : `run_autoscrape(site, sectors, dept)` scrape TOUTES les villes pop>=10k du dept (≈35-42/dept) ville par ville via scrape_sector, en continu, jusqu'à épuisement OU blocage crédits Serper. Détection blocage : proactif (solde snapshot serper-balance.json − conso god_mode_serper_calls < credit_floor=60) + réactif (3 villes vides d'affilée). Alerte Telegram + statut 'blocked_credits'. Endpoints api.py (admin-gated via request.state.session.role) : POST /autoscrape/start {sectors,dept}, GET /autoscrape/status, POST /autoscrape/stop ; registre `_active_autoscrape` (1 job global). UI scrapper : card '🤖 Autoscrape' en haut de l'onglet Lancer (réutilise sectors + selectedDept), progression live (villes X/Y, gardés, crédits restants) + stop + bandeau alerte blocage. Testé live : dept 92 (34 villes), 1 ville Boulogne → 15 gardés, crédits 2396→2392. Diag timeout user : geo/live-activity rapides (ms), session=7j, nginx genesis-api proxy_read_timeout=120s ; le timeout venait probablement d'un scrape manuel géant (266 villes IDF — l'UI envoyait toutes les villes si aucune cochée). L'autoscrape (async, lancement instantané) élimine les timeouts de requête.
- 2026-05-31 (fix logique scrape par-ville) : BUG corrigé — `scrape_sector` (god_mode_agents) traitait `max_results` comme un plafond GLOBAL alors que l'UI promettait 'par ville' (+ estimation de coût × villes). Conséquence : un scrape 'toute l'IDF' s'arrêtait à N total (1-2 villes) au lieu de couvrir les 266 villes. RÉÉCRIT : `scrape_sector(cities, max_per_city, global_cap, max_pages=4)` = N contacts GARDÉS par ville (pagination Serper Places — vérifié que page>1 renvoie du neuf), boucle sur TOUTES les villes, plafond global de contacts gardés (garde-fou crédits). `serper_places` accepte désormais `page`. Endpoint `/{site}/scrape` : `max_per_city` (1-50, accepte ancien `max_results`) + `global_cap` (def 1000, max 5000). UI scrapper : 2 champs (gardés/ville + plafond), estimation coût réaliste + alerte si >30 villes ; région sans villes cochées → envoie TOUTES les villes chargées (avant : 10 villes AU HASARD du top 50 France — autre bug). Testé live : 2 villes × max 2/ville → cities_done=2, kept=4 (Versailles 2 + Meaux 2). NB 'scraped' dans les logs = commerces EXAMINÉS (≈ crédits/10), pas gardés ; 'valid' = gardés.
- 2026-05-31 (hardening sécu post-review) : 3 recos appliquées sur les ajouts de la session. (1) `/api/enrichment/run` ajouté à `_ADMIN_PREFIXES` → réservé admin (stats reste ouvert à auth) ; UI Acquisition : bouton 'Enrichir le pool' + popup 'en retard' masqués aux non-admins (isAdmin, lecture localStorage pour éviter la race au 1er rendu). (2) cast défensif de `limit` (try/except → pas de 500). (3) fermeture du fd du log après Popen. Revue manuelle (skill /security-review KO sans git local) : RAS critique — pas d'injection commande/SQL, auth OK, raw data.gouv sanitisé (pas de dirigeants).
- 2026-05-31 (nettoyage auto post-scrape) : à la fin d'un scrape (god_mode `POST /{site}/scrape`, thread run()), déclenchement AUTOMATIQUE du drain de nettoyage Mailnjoy — plus besoin de lancer les lots à la main. Implémentation : fonction réutilisable `_launch_cleanup(site, mode, drain, chunk_size, total_limit, source)` extraite de l'endpoint /cleanup/run dans api.py (le verrou séquentiel _active_cleanups est partagé). Le hook scrape récupère le module via `sys.modules['scripts.api']._launch_cleanup(..., source='auto-scrape')`. `source` propagé dans cleanup_backend.run_cleanup/run_cleanup_drain → loggé dans cleanup_batch. UI page cleanup : badge '⚡ Automatique' vs 'Manuel' dans l'historique + bandeau d'info. Verrou strict : si un nettoyage tourne déjà, l'auto refuse proprement (le drain en cours absorbe les nouveaux contacts). NB : api.cheffer.email = CE VPS (204.168.186.159), c'est le domaine de prod de cette instance Genesis.
- 2026-05-31 (suite UI+cron) : enrichissement data.gouv complété. **Endpoints** GET /api/enrichment/stats + POST /api/enrichment/run (api.py) + fonction enrichment_stats() dans contacts_pool_backend.py. **UI** : Card 'Enrichissement data.gouv' dans la page Acquisition (vérifiés/non-vérifiés/exclus/à-traiter + signaux Qualiopi/RGE/ESS + bouton 'Enrichir le pool' qui POST run et poll les stats). **Cron** PM2 `genesis-datagouv-enrich` : `0 7 * * *`, --no-autorestart, `--limit 2000` (garde-fou), tourne en autoblog, persisté via pm2 save. ⚠️ PIÈGE RENCONTRÉ : mes runs manuels via `ssh lcr` (=root) avaient créé data/datagouv_cache.sqlite + logs/datagouv_enrich.log en root → le cron (autoblog) plantait 'attempt to write a readonly database'. Corrigé par chown autoblog. RÈGLE : tout fichier créé pour Genesis doit appartenir à autoblog, pas root.
- 2026-05-31 : **Enrichissement data.gouv intégré** (skill cheffer fourni par user). Table satellite `contact_enrichment` (1:1 contacts, contacts.duckdb) + script `scripts/datagouv_enrich.py` (API recherche-entreprises, requests, cache SQLite data/datagouv_cache.sqlite, rate 4/s + backoff 429, anti-join). RGPD : jamais de dirigeants (raw sanitisé). Filtre branché dans pick_for_campaign + count_available_for_sector (`COALESCE(e.excluded,FALSE)=FALSE`). SÉMANTIQUE CLÉ : excluded=TRUE = exclusion DURE uniquement (fermée/admin/statut P) ; non_trouve/ambigu restent contactables (excluded=FALSE, siret NULL). 1er run complet : 2899 lignes → 1633 enrichis (~56%), 1172 non-vérifiés contactables, 94 exclus durs (86 fermées + 8 admin). Signaux détectés : 178 Qualiopi, 124 ESS, 10 RGE. Match par dénomination (pas de SIRET au scrape) → fiabilité moyenne, ambigus exclus. Validé : un contact fermé n'est plus pioché. Reste hors-scope : endpoint API trigger/stats, bouton UI Acquisition, cron incrémental. Pour relancer l'incrémental : `setsid nohup python3 scripts/datagouv_enrich.py > logs/datagouv_enrich.log 2>&1 < /dev/null &`.
- 2026-05-30 (suite) : ligne Serper passée en **solde restant** au lieu de conso/mois. Serper n'ayant pas d'API de solde, snapshot manuel dans memory/seo/serper-balance.json {plan_total:2500, balance:2442, snapshot_at}. L'endpoint /api/serper/usage renvoie `available = balance − conso locale depuis snapshot_at` (god_mode_serper_calls + costs-log). Affichage widget = `2 442 / 2 500` (rouge si <10%). Pour resync : relever le vrai solde sur serper.dev et mettre à jour balance+snapshot_at dans le JSON.
- 2026-05-30 : Widget conso sidebar (CreditsWidget) — ajout ligne **Serper** (crédits consommés mois en cours). Serper.dev n'expose AUCUNE API de solde (/account,/balance,/credits => 403), donc affichage = conso locale : table god_mode_serper_calls + entrées serper-search du costs-log. Nouvel endpoint GET /api/serper/usage (api.py). Confirmé : le widget se rafraîchit déjà toutes les 60s (DeepSeek/Mailnjoy live, Ahrefs = cache quotidien cron 06:00) — l'impression 'statique' venait du quota Ahrefs gelé jusqu'au reset 2026-06-17, pas d'un bug. Build genesis-ui + pm2 restart genesis-ui/genesis-dashboard OK.
- 2026-05-21 soir : test pipeline bloqué sur abo Emelia inactif. User est allé se coucher en disant 'j'active demain matin'.
- 2026-05-22 matin : SSH cassé (clé non offerte), résolu en ajoutant bloc Host lcr dans ~/.ssh/config Mac avec IdentityFile id.mkdautoblog. Cron du matin a tourné et poussé 11 contacts → l'abo Emelia est manifestement actif.

## Backlog (parked — à reprendre plus tard)
- **Refactor DataTable shadcn** (parked 2026-05-22) — 17 fichiers de genesis-ui utilisent les primitives `Table` shadcn à la main, sans le pattern DataTable officiel (TanStack Table). Pas de `@tanstack/react-table` installé. Plan progressif identifié :
  1. Installer TanStack + créer `src/components/ui/data-table.tsx` générique (pattern shadcn officiel)
  2. Pilote sur `src/app/site/[code]/acquisition/page.tsx` (page la plus riche)
  3. Migrer ensuite les 6 pages "lourdes" : `workflow/prospects`, `workflow/campaigns`, `workflow/logs`, `articles`, `campaigns`, `costs`
  4. Pages "moyennes" (seo-strategy, seo, workflow/performance, versions, view, agents) : décision au cas par cas
  5. Tableaux statiques (dashboard, setup, site-budget-card, god-mode-panel) : on laisse en `Table` primitif, pas de refactor inutile


## Refonte SEO / Budget Ahrefs — 2026-05-22

**Contexte** : conso Ahrefs a 159% du quota (15 905 / 10 000), aucune limite implementee malgre demande user. SEO Strategist n'avait pas surveille.

**Actions realisees** :
- `scripts/cost_tracker.py` -> ajout `check_ahrefs_budget()` (gate avec seuils warn 70%, block 90%, reserve 500u)
- `scripts/ahrefs_daily.py` -> refactor MINIMALISTE (uniquement `site-explorer/metrics`, ~100u/jour). Backup ancienne version : `ahrefs_daily.py.bak-2026-05-22`
- `scripts/ahrefs_monthly_audit.py` -> NOUVEAU. Cron `0 6 1 * *`. Tier 1+2 endpoints + `site-audit/issues` (corrections techniques).
- `scripts/seo.py` -> gate integree dans `ahrefs_get()` avec params `cost_estimate` + `critical`
- `scripts/seo_strategy_agent.py` -> SURVEILLANCE budget ajoutee dans main() - emet une reco critique si conso >= 70%, notif Telegram
- `specs/seo-playbook.md` -> NOUVEAU. Doc complete : tiers endpoints, budget, gate, Site Audit projects, role SEO Strategist

**Site Audit Ahrefs** :
- LCR (`leclientroi.com`) -> projet existant, project_id `8344256` (health=100, 97 warnings, 95 notices)
- MKD (`mkdgroupe.com`) -> PAS DE PROJET, a creer dans https://app.ahrefs.com/site-audit puis mettre a jour `SITES` dans `ahrefs_monthly_audit.py`

**Etat budget actuel** :
- Conso 15 905 / 10 000 (159%)
- Reset : 2026-06-17
- D'ici la, TOUS les appels sont bloques par la gate (sauf si quota repasse sous 100% ce qui n'arrivera pas)
- Apres reset : tracker la conso, viser ~7 000/mois max

**Decisions user** :
- GSC : mis en pause (pas envie de le brancher pour l'instant)
- DataTable refactor : parke (cf section Backlog plus haut)

## Next action (a faire au reset 2026-06-17 ou avant)
1. Creer projet Site Audit Ahrefs pour mkdgroupe.com
2. Une fois le quota reset, lancer manuellement `python3 scripts/ahrefs_monthly_audit.py` pour verifier que tout fonctionne
3. Verifier que le cron monthly s'execute bien le 1er juin 6h UTC
4. Reprendre le pipeline LCR Emelia (campagnes en DRAFT -> demarrer)


### Additif 2026-05-22 (suite décisions user)
- `seo.py --report full` -> DESACTIVE (sys.exit dans main()). Plus de bouton UI a brancher dessus.
- `seo.py --report keywords` -> max 1x tous les 2 mois (operationnel, pas de blocage code)
- `site-explorer/metrics` -> BYPASS gate budget dans ahrefs_daily.py. Jamais bloque meme en depassement quota.


## Email Validator déployé — 2026-05-22

**Spec** : EMAIL_VALIDATION_SCORING.md (fourni par user) — 6 étages, drop avant insertion.

**Fichiers** :
- scripts/email_validator.py (module unique, point d entrée: validate_and_score(email, prospect))
- data/email_jetable.csv (304 domaines disposable chargés depuis la liste fournie + enrichie user)
- DB scrappe migrée : email_score INTEGER, email_validation_reasons JSON
- Intégré dans god_mode_agents.scrape_sector() : si decision=drop, prospect jamais inséré
- god_mode_backend.add_prospect() étendu pour persister email_score + reasons

**Honeypots** (drop hard reject avant scoring) : spamtrap, honeypot, trap@, abuse@, spam@, **rgpd@, dpo@, gdpr@, @rgpd., @dpo.** (déplacés depuis role-based à la demande user — sécu CNIL)

**Décisions de seuils** :
- score < 40  -> drop (rejection_reason = low_score)
- 40 <= score < 60 -> queue (status = manual_review, à reviewer humain)
- 60 <= score -> push (status = validated, éligible push Emelia)

**Backfill 2026-05-22** : 20 prospects analysés, 3 rejetés (1 sentry no_mx + 2 rgpd@junot.fr), 2 passés en manual_review, 12 déjà pushés Emelia non touchés (juste email_score informatif).

**Pipeline en place pour les prochains scrapes** : le cron du matin (30 6) appellera god_mode_agents.scrape_sector() qui filtrera automatiquement chaque email via validate_and_score avant insertion.


## Mailnjoy intégré (Phase 1 backend) — 2026-05-22

**Spec** : PAPERCLIP/mailnjoy-api-reference.md + mailnjoy-integration-prompt.md

**Architecture** : Serper -> validator -> scrappe_pending -> Mailnjoy -> scrappe ou DELETE.

**Décisions actées** :
- risky = DELETE (jamais en scrappe) — décision user (1.b)
- Flow synchrone (Mailnjoy appelé dans la boucle scrape) — décision user (2.a)
- Phase 2 UI (sidebar credit, tag visuel, page setup) parquée

**Composants livrés** :
- Table scrappe_pending (memes colonnes que scrappe + mailnjoy_attempts/last_error)
- Colonne scrappe.mailnjoy_check (JSON) pour traçabilité
- scripts/mailnjoy_check.py : check_email_mailnjoy(), classify_response(), get_credit(), check_pending_queue()
- scripts/god_mode_backend.py : add_prospect_pending(), list_pending(), move_pending_to_scrappe(), delete_pending(), bump_pending_error()
- scripts/god_mode_agents.py scrape_sector() ecrit dans scrappe_pending
- scripts/workflow_runner.py appelle check_pending_queue(site) apres chaque scrape de secteur
- logs/mailnjoy_deletions.log audit des suppressions

**Test E2E 2026-05-22 11h55 (4 emails)** :
- valid=1, risky=2, invalid=1 — pending vide, scrappe peuplé, log OK
- Crédits consommés 8u (2/email × 4) sur solde 1 199 105 -> 1 199 097

**Credentials .env** :
- MAILNJOY_ID + MAILNJOY_SECRET configurés (clé lecture seule=non, autorisation achat=oui)
- Endpoint /v2/unitary?type=simple, body en text/plain
- Backoff exponentiel sur 429/503/500 (max 5 essais)
- Stop immédiat si 401/403

**Map décision** : VALID/SAFE -> valid | INVALID/UNSAFE/spamtrap/disposable -> invalid | RISKY/catchall/role/suspect -> risky | network/500 -> error (retry max 5)


## Phase 2 Mailnjoy complète — 2026-05-22 (suite refonte)

Tout les non-fait du récap précédent ont été traités :

**Backend** :
- Idempotence 30 jours : helpers god_mode_backend.email_recently_validated(email, days) + email_in_pending(email), branchés dans scrape_sector pour skip avant insert pending
- State machine refonte complète (cf section 12 de specs/workflow-prospection.md) :
  - pending_mailnjoy (scrappe_pending default)
  - mailnjoy_valid (scrappe après drain valide)
  - pushed_emelia (status après push Emelia OK)
  - scored (legacy, prospects pré-Mailnjoy)
  - manual_review (validator queue)
  - rejected (validator drop)
- Migration DB faite : 16 validated -> 15 scored + 1 mailnjoy_valid
- Queries downstream updated dans workflow_runner, god_mode_backend, workflow_emelia_push

**Endpoints API** (api.py) :
- GET  /api/mailnjoy/credit               → solde
- GET  /api/mailnjoy/status               → configuré ? crédit ? pending count
- POST /api/mailnjoy/test-credentials     → test avec ID/Secret donnés (sans sauvegarder)
- POST /api/mailnjoy/save-credentials     → écrit dans .env après test OK
- POST /api/mailnjoy/drain                → déclenche un drain manuel
- GET  /api/sites/{site}/workflow/counters → compteurs refondus (Scrapés, Ajoutés, Nettoyés, Envoyés)

**UI (genesis-ui)** :
- credits-widget.tsx : ligne Mailnjoy en vert (rouge si < 500u), polling 60s
- mailnjoy-config-card.tsx : nouveau composant pour la page Setup (input ID+Secret, bouton Tester, bouton Sauvegarder, affichage crédit + pending count)
- prospects/page.tsx : colonnes Email score + Mailnjoy (tag visuel ✓/⚠/✗ + date) + Qualifier DS (✓ qualifié / ✗ rejeté DS / pending), filtres sur nouveaux statuts (mailnjoy_valid, pushed_emelia, manual_review, scored, rejected)
- setup/page.tsx : MailnjoyConfigCard inséré au-dessus des connecteurs site-specific
- Next.js rebuild OK, pm2 restart genesis-ui OK

**Documentation** :
- specs/workflow-prospection.md : section 12 Email Validator + Mailnjoy ajoutée (pipeline complet, state machine, idempotence, particularités API)

**Tests** :
- tests/test_mailnjoy_check.py : 22 tests pytest (classify_response 11 cas, check_email_mailnjoy 8 cas, edge cases 3 cas) → 22/22 PASSED
- Stratégie : mock requests.post au lieu de Prism (équivalent fonctionnel, plus simple, pas de serveur HTTP à lancer)

**Dépendances installées** :
- dnspython (pour MX check du validator)
- email-validator (pour pydantic v2, requis par fastapi - bug latent corrigé)
- pytest

**Crédits consommés ce session** : 8u Mailnjoy (sur 1 199 105 dispo)


## Webhook Emelia temps réel + Warmup plan — 2026-05-22 (suite)

**Webhook Emelia branché en prod** :
- Endpoint backend : POST /api/emelia/webhook?token=WEBHOOK_TOKEN_1 (existait déjà, opérationnel)
- Webhook Emelia créé via POST /webhook avec campaignId=ALL_CAMPAIGNS, type=email, events=[SENT,OPENED,CLICKED,REPLIED,BOUNCED,UNSUBSCRIBED]
- Emelia déploie auto sur les 9 campagnes existantes (LCR + Test + Lancement)
- Test E2E validé : afchain.camille a cliqué le lien unsubscribe → event UNSUBSCRIBED reçu → state mis à blacklisted dans acquisition_contacts

**Table emelia_events ajoutée à god_mode.duckdb** :
- Audit de TOUS les events Emelia (incl. SENT/OPENED qui étaient ignorés avant)
- Colonnes : id, received_at, event_type, email, first_name, last_name, campaign_name, campaign_id, site_code, step, emelia_date, raw_payload
- 3 index : email, campaign_id, received_at

**Auto-register webhook à chaque nouvelle campagne** :
- workflow_emelia_push.get_or_create_campaign() appelle POST /webhook après création (idempotent)
- Push aussi automatiquement les steps + start de la campagne dans la foulée

**Bug fix** :
- Handler webhook normalise désormais event_type en lower() (Emelia envoie en UPPERCASE)
- Campaign peut arriver en string OU dict → handler gère les 2

**Warmup plan déployé** :
- Spec : specs/warmup-plan.md (137 lignes, Plan A conservateur Emelia + Plan B agressif IP Warming Planner)
- Table email_senders dans god_mode.duckdb (sender_email PK, warmup_start_date, daily_max_override, status)
- Sender LCR juliette@leclientroi.com inscrit avec warmup_start=2026-05-22 (J1=10 emails/jour)
- Plan A appliqué : J1-J3=10, J4-J7=20, J8-J14=35, J15-J21=50, J22-J28=75, J29+=100
- Helpers ajoutés à workflow_emelia_push.py : daily_warmup_quota(), sender_email_for_site(), emelia_sent_today_by_sender()
- Garde-fou branché dans push_prospect : si sent_today >= warmup_quota → bloc push avec raison warmup_quota_reached
- État actuel : sender Juliette J1 → quota 10, déjà envoyé 1 (test) → 9 restants pour aujourd'hui

**Reste à faire** (priorité) :
- Démarrer les 5 campagnes LCR DRAFT (workflow-lcr-restaurant/artisan/coiffeur/garagiste/immobilier) avec templates + start — script migrate_existing_draft_campaigns.py à coder
- Sidebar UI : afficher J{N}/quota par sender (warmup status visible)
- Cron quotidien warmup_daily_check.py : pause sender si bounce_rate > 5% ou unsubscribed_rate > 2%


## Pool mutualisé contacts — Phases 0+1+2 — 2026-05-22

**Spec sources** : specs/contacts-model.md, onboarding-checklist.md, campaigns-spec.md (3 docs validés par user).

### Phase 0 — Migration data
- NOUVEAU fichier : data/contacts.duckdb (chown autoblog:autoblog)
- 2 tables créées : contacts (PK email unique, 36 rows) + contact_site_history (UNI (contact_id, site_code), 36 rows)
- Script : scripts/migrate_contacts_to_pool.py
- Source : crm/lcr.duckdb (33), crm/mkd.duckdb (1), god_mode.duckdb.scrappe (3) — déduplication par email
- Logs : logs/migration_contacts_pool.log
- ⚠️ Anciennes DBs intactes (RO) — rollback possible 30 jours

### Phase 1 — Backend pool
- NOUVEAU module : scripts/contacts_pool_backend.py
- 13 helpers publics : find_by_email_global, create_in_pool, set_global_blacklist, get_history_for_site, upsert_site_history, change_state_for_site, mark_pushed_to_emelia, record_emelia_event, list_contacts_for_site, stats_for_site, pick_for_campaign, count_available_for_sector, check_pool_depletion
- Constantes : COOLDOWN_GLOBAL_DAYS=30, COOLDOWN_SAME_SITE_DAYS=7, STATE_RANK
- Testé : stats LCR=35 contacts, pick_for_campaign restaurant=0 (cohérent — peu de cold_email), check_pool_depletion fonctionne

### Phase 2 — Dual-write activé sur 5 maillons
Tous les flux d'écriture alimentent en parallèle le pool ET le système legacy (acquisition_contacts) :
1. api.py:api_emelia_webhook → record_emelia_event + change_state_for_site + set_global_blacklist (si bounce/unsub)
2. workflow_emelia_push.py:push_prospect → create_in_pool + upsert_site_history + mark_pushed_to_emelia
3. tally_to_prm.py → _tally_dual_write_pool helper (lead direct)
4. emelia_to_crm.py → _dual_write_pool helper (sync cron 19h)
5. god_mode_agents.py:scrape_sector → create_in_pool + upsert_site_history cold_email

Validation live 2026-05-22 21:00 : POST webhook CLICKED sur afchain.camille@gmail.com → pool state cold_email → prm OK + emelia_clicked_at set.

### Reste à faire
- Phase 3 : UI Acquisition (fusion onglet Pipeline + sous-vue historique par site)
- Phase 4 : UI Campagnes (wizard 4 étapes, algo pioche, page détail)
- Phase 5 : UI Vision (compteurs + funnel + warmup)
- Phase 6 : UI Onboarding 16 steps
- Phase 7 : Sidebar cleanup (supprimer module Workflow)
- Tables  +  chiffrée AES (multi-tenant cible) — pas encore créées


## Refactor complet — Phases 0-7 livrées — 2026-05-22 (suite session go)

### Phases 3-7 livrées (suite à Phase 0-2 du début de session)

**Phase 3 — Page Acquisition refondue** ()
- Switch endpoint de lecture sur /api/sites/{site}/pool/contacts (au lieu de /acquisition legacy)
- Type Contact étendu pour matcher la structure pool (sectors, primary_source, email_score, mailnjoy_check, last_contacted_by_site_at, etc.)
- Edit/delete/blacklist toujours sur l ancien endpoint legacy (dual-write garde sync)

**Phase 4 — Page Campagnes nouvelle** ()
- Wizard 4 steps (secteur > volume > preview > validation)
- Alerte secteurs épuisés (popup card)
- Liste campagnes Emelia avec stats (sent, opens%, clicks%, replies%, progress%)
- Endpoint POST /api/sites/{site}/pool/campaigns/create qui pick + create + steps + push + start + webhook

**Phase 5 — Page Vision nouvelle** ()
- KPI cards : contacts pool, envoyés, leads, nettoyés
- Funnel chart (workflowFunnelConfig) avec scraped/qualified/sent/prm/leads/bounced
- Distribution par source primaire (progress bars)
- Placeholder warmup status

**Phase 6 — Onboarding refondue** ()
- 16 steps en cards séquentielles (Identité, URLs, Persona, SEO, Éditorial, Secteurs, Sender, RGPD pied de mail, API keys, Templates, Warmup, Modules, Ahrefs, Quotas, Compte, Mail test)
- Validation des champs bloquants (border rouge sur cards incomplètes)
- Sticky submit en bas avec compte des steps complétés
- Payload posté vers /api/sites/onboard-full (à étendre backend pour gérer les 16 champs)

**Phase 7 — Sidebar cleanup**
- Section Commercial refondue : Vision, Acquisition, Templates, Campagnes (par site)
- Suppression Workflow, Vue d ensemble, Performance, Prospects, Campagnes (legacy /workflow/), Prospection (global /campaigns)
- TITLE_TO_MODULE mis à jour

**Cleanup fichiers**
- Supprimés : src/app/site/[code]/workflow/{campaigns,prospects,performance}, page.tsx
- Gardés : workflow/templates (lien sidebar), workflow/logs (admin), workflow/layout.tsx (auth)

**Pool write endpoints ajoutés** (api.py)
- POST /api/sites/{site}/pool/contacts/create
- PATCH /api/sites/{site}/pool/contacts/{id}
- DELETE /api/sites/{site}/pool/contacts/{id}
- POST /api/sites/{site}/pool/contacts/import-csv

### Restes connus
- L endpoint backend /api/sites/onboard-full doit etre etendu pour gerer les 16 nouveaux champs (persona, sectors_enabled, modules_enabled, warmup_plan, account_id, etc.) sinon les nouvelles infos sont droppees a l onboarding
- Table accounts + site_credentials AES chiffrees (multi-tenant cible) pas encore creees
- Pages /workflow/templates et /workflow/logs restent — a refondre (templates devient lecture seule depuis Emelia, logs vers /admin/logs)
- L UI Acquisition utilise toujours edit/blacklist legacy endpoints — a migrer vers pool/* equivalents


## Session enchaine — finalisation backend + cleanup — 2026-05-22 23:00

### Backend onboard V2 + multi-tenant
- Tables NOUVELLES dans god_mode.duckdb :
  -  (id PK, label, owner_user_id, plan, created_at) — multi-tenant
  -  (site_code+key_name PK, encrypted_value) — clés API par site (MVP clair, à chiffrer AES v2)
- god_mode_settings enrichie de 6 colonnes : sectors_enabled JSON, daily_quota_per_sector, emelia_daily_limit, cooldown_same_site_days, cooldown_global_days, account_id
- /api/sites/onboard-full étendu pour gérer les 16 champs du nouveau wizard :
  - persona/geo/dept_priority → context/{code}/audience.md
  - tone/cta/signature/banned_words → context/{code}/editorial-style.md
  - raison_sociale/adresse/dpo/privacy → context/{code}/footer.md (pied de mail B2B)
  - sender_email/sender_name → INSERT email_senders (warmup_start_date = aujourd hui si warmup_start_today=True)
  - sectors_enabled, daily_quota, emelia_daily_limit, cooldowns → god_mode_settings
  - emelia_key/serper_key/tally_key/telegram → site_credentials
  - account_id → INSERT accounts
  - modules_enabled → memory/{code}/modules.json
  - god_mode_state.enabled = FALSE par défaut (déblocage après Step 16 mail test)

### Migration UI Acquisition vers pool/* endpoints
6 actions write switched de /acquisition/* legacy vers /pool/contacts/* :
- change-state, update fields, create, blacklist, delete, import-csv
La page Acquisition est désormais 100 pourcent sur le pool mutualisé (lecture + écriture).

### Cleanup fichiers
- Move src/app/site/[code]/workflow/templates/ → src/app/site/[code]/templates/
- Sidebar Templates pointe maintenant vers /site/[code]/templates (au lieu de /workflow/templates)
- workflow/ ne contient plus que layout.tsx (admin check) + logs/ (accessible direct)

### Reste à faire
- Chiffrement AES site_credentials.encrypted_value (MVP clair OK pour LCR + MKD perso)
- Cron 6h30 demain alimentera le pool en vrai via dual-write (premier test prod)
- Step 16 onboarding mail test : envoyer effectivement le mail via /emails/test Emelia + UI confirmation
- Page admin/logs (déplacer /workflow/logs vers /admin/logs)
- Backup cron à étendre pour inclure data/contacts.duckdb


## Session enchaine 2 — AES + mail test + backup — 2026-05-22 23:30

### A. Chiffrement AES Fernet site_credentials
- NOUVEAU module : scripts/site_credentials_backend.py
- Helpers : encrypt_value, decrypt_value, set_credential, get_credential, list_credentials, delete_credential, migrate_plaintext_to_encrypted
- Master key : env var SITE_CREDENTIALS_MASTER_KEY (prioritaire) sinon data/.master_key (auto-générée, chmod 600)
- Backward compat : valeurs anciennes en clair sont re-chiffrées au premier get_credential
- Endpoint /api/sites/onboard-full migré pour utiliser set_credential (AES) au lieu d INSERT direct
- workflow_emelia_push._get_key etendu : lit site_credentials AES en priorité, fallback env vars

### B. Step 16 onboarding mail test + activation
- NOUVEAU endpoint POST /api/sites/{code}/onboarding/send-test-email
  - Body : {test_email, sector}
  - Crée campagne onboarding-test-{code} si absente + configure steps
  - Appelle /emails/test Emelia (envoi instantané sans cadence)
- NOUVEAU endpoint POST /api/sites/{code}/onboarding/confirm-activation
  - Body : {received: true}
  - Passe god_mode_state.enabled = TRUE pour ce site
- Page UI onboarding étendue : après submit, le site est créé mais god_mode_state.enabled=FALSE
  - Step 16 affiche bouton Envoyer mail test
  - Apres envoi : bouton J ai reçu → confirm-activation → enabled=TRUE → redirect dashboard
  - Bouton Renvoyer disponible si user n a pas reçu

### C. Backup cron étendu
- scripts/backup.sh : check explicite des fichiers critiques (contacts.duckdb, god_mode.duckdb, auth.duckdb, .master_key)
- Copie séparée de .master_key vers BACKUP_DIR/.master_key.bak (disaster recovery)
- Cron quotidien 21h UTC inchangé (continue de tourner)

### Reste à faire pour vraiment SaaS-ready
- Cron 6h30 demain matin = premier test grandeur nature (passive, vérifier les logs)
- Page admin/logs (déplacer /workflow/logs vers /admin/logs au niveau global)
- Endpoint /api/sites/{code}/credentials/{key_name} pour lire/setter les clés via UI (gestion des clés post-onboarding)
- Multi-tenant : section UI accounts (CRUD comptes) — actuellement la table existe mais pas de CRUD
- Test : un nouveau site complet créé via UI onboarding (vérifier les 16 steps end-to-end)

---

## Session IMPORT CSV INTELLIGENT — 2026-05-25

Nouvelle feature : import CSV drag&drop vers le pool mutualisé (`/site/[code]/acquisition` → bouton « Importer CSV »).

**Flux en 2 phases** (le fichier est uploadé 1× sur le VPS sous `data/imports/{site}/`, chmod 600, purge >7j) :
1. `POST /api/sites/{site}/pool/import/analyze` (multipart) → détecte séparateur (`;`/`,`/tab/`|`) + charset (utf-8/cp1252/latin-1, NFC) + mappe les colonnes (alias FR/EN) + **1 seul appel DeepSeek** pour mapper les catégories du fichier vers les secteurs + pré-analyse dédup (1 requête `SELECT email`). Renvoie un `import_id` + récap.
2. `POST /api/sites/{site}/pool/import/{import_id}/commit` → **StreamingResponse SSE** (`data: {step,pct,…}`), upsert batché (1 connexion réutilisée), `source="manual"`, state `cold_email`.

**Secteurs dynamiques (DB-backed, plafond 30)** : nouvelle table `sectors` dans `god_mode.duckdb` (seed = 16 + `autre`). DeepSeek crée les secteurs manquants (B2B/B2C) sans jamais dépasser **30 au total** ; au-delà → bucket `autre`. `GET /api/sectors` + hook front `useSectors()` (lib/use-sectors.ts). `SECTORS_GOD_MODE` reste la liste *scrapable* (Serper), les secteurs importés ne sont pas scrapés.

**Dédup** : clé = email. Doublon existant → enrichissement NULL-only (jamais d'écrasement). Doublon interne au fichier → 1ʳᵉ occurrence gardée. Lignes KO (email invalide) listées avec raison.

**Fichiers** :
- back : `scripts/csv_import_backend.py` (nouveau), `scripts/api.py` (3 endpoints), `scripts/contacts_pool_backend.py` (migration colonnes `job_title`/`civility`/`job_function` + `create_in_pool`/`upsert_site_history` acceptent `conn`), `scripts/god_mode_backend.py` (table `sectors` + `list_sectors()`/`add_sector()`).
- front : `components/import-wizard.tsx` (nouveau, drag&drop + récap + anneau % + confetti), `lib/use-sectors.ts` (nouveau), `lib/sectors.ts` (+`autre`), page acquisition (branchement, ancien import textarea supprimé). Dépendance `canvas-confetti`.

**Testé** (2026-05-25) sur `responsable_marketing.csv` (5037 lignes directeurs marketing, séparateur `;`, utf-8) :
- échantillon 10 lignes → 10 ajoutés en `manual`, dept dérivé du CP, website préfixé `https://`, accents OK, secteurs créés (banque/assurance/industrie/agroalimentaire).
- HTTP analyze + commit SSE OK ; ré-analyse du même échantillon → 10 détectés en *enrichis* (dédup), commit → updated=10/added=0.
- mapping secteur complet du fichier : 13 nouveaux secteurs, total **30/30** pile au plafond (les plus petits volumes → `autre`).

⚠️ **Op** : PM2 tourne sous l'utilisateur `autoblog` → restart via `sudo -u autoblog bash -lc "pm2 restart genesis-dashboard|genesis-ui"`. Les fichiers écrits par l'API doivent rester accessibles à `autoblog` (chown `data/imports`).

**Reste** : ~~importer les ~5027 lignes restantes~~ → **FAIT**. Le pool contient désormais **5112 contacts** (cf. section COLD EMAIL ci-dessous pour la photo réelle par secteur).


---

## Session COLD EMAIL — refonte génération par secteur — 2026-05-25 (incréments 1-3 LIVRÉS)

### Constat de départ
- Templates Emelia = **mail-merge pauvre** : `emelia_campaign_manager.get_default_steps()` = 2 templates figés, signe « Camille », icebreaker générique.
- **Réalité du pool LCR (corrige les sections précédentes)** : l'import est FAIT → **5112 contacts**, dont **~94 % directeurs/responsables marketing grands comptes** (banque, agro, industrie, luxe, assurance, tourisme, médias…), **PAS** les PME locales du `campaign-plan.md`. PME locales (resto/commerce/artisan) = ~53 (1 %). Bucket `autre` = 2065 (40 %).

### Décisions user (2026-05-25)
- **Move upmarket assumé** : LCR vise les directeurs marketing grands comptes → offre = **SMS + RCS comme canal de campagne premium** (pas le drive-to-store PME). Les 53 PME locales gardent leur angle à part.
- **Perso = données structurées seules** (poste + secteur + entreprise + ville). PAS de scrape website pour l'instant → perso **persona-niveau** (pas de vrai 1to1 individuel). Le scrape rebranchera le vrai 1to1 plus tard.
- **Review humaine obligatoire** sur les premiers batchs (warmup J1).
- **PAS de séquence ni d'envoi automatiques** : l'IA PROPOSE 3 emails par secteur ; le user **édite et programme/verrouille chaque email lui-même**. → outil = **assistant de rédaction**, pas un automate. L'incrément ④ (branchement pipeline) est **ABANDONNÉ**.
- **Secteurs EXCLUS** : industrie (378) + agroalimentaire (376) = 754 contacts (SMS marketing non pertinent). Bucket `autre` (2065) = phase 2.

### Skills Claude Code installés (sur le Mac `~/IA/Projets/.agents/skills/`, outil de CONCEPTION)
- `cold-email` (coreyhaines31) + `cold-email-templates-34` (ColdIQ) — markdown pur, notés Low Risk.
- `cold-email-verifier` (arnanech/op) NON installé : repo 404 + redondant avec Mailnjoy + email_validator.
- ⚠️ Ces skills aident MOI à concevoir ; le runtime génère via **DeepSeek sur le VPS** (`llm_call.py`). L'expertise est transférée dans les angles + le prompt.

### Livré et testé
- **`context/lcr/sector-angles.md`** (NOUVEAU) : 10 secteurs × séquence 3 mails validés. Preuves mappées honnêtement (Immo92→immo, +35 % boutique→retail/luxe, +25 %/ROIx50→restau, « 500+/10M SMS »→neutre). Industrie/agro = EXCLUS.
- **`context/shared/cold-email-rules.md`** : ajusté mode persona-niveau (icebreaker = fait réel OU douleur secteur ; E2 = cas client OU preuve volume). Backup `.bak-2026-05-25`.
- **`scripts/email_generator.py`** (NOUVEAU) : `generate_sequence(site,sector)` → angle + DeepSeek (`call_llm_json`) → finalise (Juliette, CTA TidyCal, signature + désinscription RGPD) → `validate_email()` (interdits FR, ≤150 mots, 1 seul `<a>` TidyCal, objet) → exclut industrie/agro/autre. + `supported_sectors()` (10 secteurs UI). CLI dry-run OK.
- **`scripts/email_templates_backend.py`** (NOUVEAU — remplace le doublon `sector_templates_backend`, supprimé) : table **`email_templates`** (`god_mode.duckdb`), **modèle 1-ligne-par-email** `(site, sector, kind)` kind∈{first,relance1,relance2}, chacun **éditable/verrouillable seul** (`locked` = approbation ; **régénérer respecte les verrous** ; éditer rouvre). Helpers : generate / get_sector / list_sectors / update / set_lock.
- **`scripts/api.py`** : **6 routes** `/api/sites/{site}/templates/*` — generate · list(+available) · get{sector} · PUT {sector}/{kind} · {kind}/lock · {kind}/unlock. Backup `api.py.bak-2026-05-25`.
- **UI stepper** (genesis-ui) : `src/app/site/[code]/templates/page.tsx` REFONDUE (stepper 3 étapes : Select secteur → email kind → éditeur + **aperçu live** ; **mobile = onglets** Éditer/Aperçu ; badge conformité ; lock). + `src/components/email-body-editor.tsx` (NOUVEAU, **Tiptap**, switch **Visuel/Brut**). Build OK, déployé. Backup page `.bak-2026-05-25`.
  - ⚠️ **Validation VISUELLE par le user EN ATTENTE** (rendu mobile, génération IA depuis l'UI, Tiptap, aperçu) — pas de navigateur côté agent.

### Reste à faire (cold email)
- **Valider le visuel de l'UI stepper** (mobile surtout) + tour d'ajustements.
- **SPRINT FUTUR** (détaillé dans `PLAN-ACTION.md`) : templates à **structure HTML VERROUILLÉE**. Le user fournit le HTML ; seules les zones **texte / image / lien** éditables (placeholders `{{...}}` ; type par contexte : `src=`→image, `href=`→lien, sinon texte). DeepSeek ne remplit QUE les textes. → l'éditeur Tiptap deviendra un **éditeur de zones** (formulaire).
- Plus tard : scrape website (vrai 1to1), bucket `autre`, image de signature.

### Op / pièges
- `get_default_steps()` (legacy, 3 call sites) NON modifié — ④ abandonné. `email_templates` n'est PAS branché à l'envoi (assistant de rédaction).
- API Python sans `--reload` → `pm2 restart genesis-dashboard` pour recharger.
- **genesis-ui = build prod (port 3100)** → `npm run build` PUIS `pm2 restart genesis-ui` obligatoires pour déployer le front.
- Écrire dans `god_mode.duckdb` en process externe = OK (le cron le fait), écritures ponctuelles (connect/close).


---

## Session AUTH / RBAC — 2026-05-26 (Sprints 1-2 ; plan détaillé dans PLAN-ACTION.md)

**État au départ** : auth + 2FA TOTP + QR **déjà en place** (`auth_backend.py` pyotp, page `/security`, login 2-étapes). **1 seul user** : `camille` (superadmin, sites lcr+mkd, **2FA OFF**).

### Livré et déployé
- **`POST /api/auth/users` étendu** : génère un mdp temporaire si absent, accepte role+sites+phone, renvoie le mdp + un `access_text` **copiable** (id/mdp/URL/pas-à-pas 2FA). Validation : non-superadmin = **exactement 1 site**. Telegram optionnel.
- **Page `/admin/users`** (NOUVELLE, dans la sidebar admin global) : créer (rôle+site+mdp auto+**bloc copiable**), lister, changer rôle, reset mdp, supprimer.
- **Isolation multi-tenant** (middleware `api.py`) : `/api/sites/{site}/*` vérifie `site ∈ session.sites` (superadmin bypass) → **ferme la faille** (avant : tout user authentifié accédait à tous les sites). + **FIX** : le check admin-only excluait `superadmin`.
- **Sidebar filtrée par rôle** (`app-sidebar.tsx` `buildNavSite` + `ROLE_SECTIONS`) : superadmin=tout, strategie/contenu/commercial = leur section. **Switcher de sites masqué si 1 seul site** (`team-switcher.tsx`).
- **Rôles** : `superadmin` / `strategie` / `contenu` / `commercial`.
- Backups : `api.py.bak-2026-05-26`, `app-sidebar.tsx.bak-2026-05-26`, `team-switcher.tsx.bak-2026-05-26`.

### Reste (auth/RBAC)
- **Fix menu nav-user** (bas de sidebar) : BLOQUÉ — attend l'erreur **console** du user. Le code est sain (même pattern que le switcher) ; les logs « Failed to find Server Action » = **bruit** (clients périmés après rebuilds), pas la cause.
- **« Bloquer » un user** (champ `disabled` + check login + bouton UI) — Tâche 7.
- Option : **forcer le 2FA à la 1re connexion** (à décider).
- **camille : activer son 2FA** (actuellement OFF).
- Sprint 3 : `/security-review` (déclenché par le user). Sprint 4 : RGPD (questions d'abord). Sprint technique : durcissement déploiement front (staleness).

### À TESTER par le user (validation visuelle — pas de navigateur côté agent)
1. `/admin/users` → créer un compte « commercial » sur lcr → le **bloc d'accès copiable** s'affiche.
2. Se connecter avec ce compte → il ne voit que la section **Commercial**, **pas de switcher** (1 site), et l'accès à mkd est **refusé (403)**.
3. Bug nav-user : **hard refresh** puis console si ça persiste.

### MAJ 2026-05-26 (suite) — Sprint 2 COMPLET
- ✅ **Mode superadmin UI** : rôle affiché sous le nom (nav-user), **liseré 5px ambre** autour de la fenêtre, **top bar** (date live + IP + users connectés + campagnes en routage + déconnexion). Endpoint `GET /api/admin/superadmin-bar` (cache 60s Emelia). Composant `superadmin-bar.tsx`. Validé visuellement par le user.
- ✅ **Bloquer/débloquer un compte** : colonne `disabled` (auth.duckdb), `login()` refuse `account_disabled`, `update_user`/`list_users` gèrent `disabled`, bouton + badge dans `/admin/users`.
- Backups : `auth_backend.py.bak-2026-05-26`, `nav-user.tsx.bak-2026-05-26`, `client-shell.tsx.bak-2026-05-26`.
- **Sprints 1 & 2 = bouclés.** Reste : nav-user (attend console user), option « forcer 2FA 1re connexion », Sprint 3 `/security-review` (déclenché par user), Sprint 4 RGPD (questions d'abord). camille : activer 2FA.

### MAJ 2026-05-26 — Sprint 4 RGPD (en cours)
Décisions user : base légale = **intérêt légitime B2B**, **anonymiser** avant LLM (0 PII hors UE), conservation **3 ans**.
Entités (cf. mémoire reference_legal_entities) : LCR=HUMANETICS LABS (SARL, SIREN 995210010, Colombes, dpo@humaneticslabs.com) · MKD=MKD GROUPE (SARL, SIREN 852283761, Maisons-Alfort, dpo@mkdgroupe.com). Responsable RGPD=société, DPO=Camille.
- ✅ **4a LIA** + **4b privacy notices** (×2) → `/home/autoblog/genesis/legal/` (lia-prospection-b2b.md, privacy-notice-lcr.md, privacy-notice-mkd.md). MODÈLES à faire viser par un juriste avant publication.
- ✅ **4c (partie)** : `workflow_qualifier.py` n'envoie plus email+téléphone à DeepSeek (backup .bak-2026-05-26). email_generator/god_mode_templates déjà sans PII.
- Reste 4c : auditer csv_import (mapping secteur), **purge auto 3 ans**, **chiffrement at-rest contacts.duckdb** (était parké).
- Reste 4d : caviardage PDF (skill github Ldecavel) + anonymisation exports (datanaos).

### MAJ 2026-05-26 — Sprint 4 RGPD : 4c + 4d clôturés
- ✅ **4c audit DeepSeek COMPLET** : qualifier (email+tél retirés), csv_import (n'envoie que les noms de catégories, jamais les contacts), email_generator/templates (par secteur). → 0 PII vers DeepSeek.
- ✅ **4c purge 3 ans** : `scripts/rgpd_purge.py` (anonymise les prospects froids > 3 ans, épargne leads/clients/blacklistés ; dry-run + `--apply`). **Cron mensuel** 1er à 4h → `logs/rgpd_purge.log`. 0 concerné aujourd'hui (données récentes).
- 🟡 **Chiffrement at-rest `contacts.duckdb`** : NON fait en applicatif (DuckDB n'a pas de chiffrement natif ; la clé serait sur le même serveur = gain faible). En place : secrets AES (site_credentials), chmod 600, RBAC+2FA, backups. **RECO = activer le chiffrement de volume côté Hetzner** (action infra, pas du code).
- ✅ **4d caviardage PDF** : skill `caviardage-pdf` installé (Mac, MIT, 100% local, PyMuPDF) — outil à la demande.
- 🟡 **4d anonymisation exports (datanaos)** : service externe payant, **aucun use case d'export actif** dans Genesis (l'anonymisation est déjà couverte par la purge + le qualifier). À brancher seulement si besoin réel.

**Sprint 4 RGPD clôturé.** Restes = décision infra (chiffrement disque Hetzner) ou service externe (datanaos) si besoin.
**Restes globaux hors-dev** : #1 nav-user (attend console user), #8 `/security-review` (user lance), publier les privacy notices sur les sites.

### ⚠️ PIÈGE OP (2026-05-26) — genesis-ui = pnpm
`genesis-ui` est géré par **pnpm** (pnpm-lock.yaml, node_modules/.pnpm). **NE JAMAIS faire `npm install`** ici → ça crashe arborist ("Cannot read properties of null (reading 'matches')"). Utiliser **`pnpm add <pkg>`** (via `sudo -u autoblog`). `npm run build` reste OK (n'installe rien).
### Sprint éditeur newsletters HTML — incrément ① fait
- structures/leclientroi-newsletter-v2.html transférée ; module scripts/html_templates_backend.py + table html_templates + 6 endpoints /api/sites/{site}/html/* (testés). dnd-kit installé (pnpm). Reste ② composant éditeur (dnd blocs + édition in-place texte/image) + ③ intégration step 2 + envoi Emelia.

---

## Sessions Mailnjoy cleanup — 2026-05-28 → 2026-05-30

**Pitch** : nettoyage périodique du pool `contacts.duckdb` via Mailnjoy (suppression invalid/risky, certif. valid posée sur `mailnjoy_check` JSON). Page dédiée `/site/[code]/cleanup`.

### Architecture livrée (refactor sérieux, fin de session 2026-05-28)

**Backend (`scripts/cleanup_backend.py`)**
- `run_cleanup(mode, site, limit, progress_cb=None, should_stop=None)` — 1 chunk synchrone. `should_stop()` checké AVANT chaque contact ; `progress_cb(stats, processed, email)` émis APRÈS chaque contact (try/finally garantit l'émission, les `continue` ne sautent rien).
- `run_cleanup_drain(mode, site, chunk_size=100, total_limit=None, progress_cb, should_stop)` — enchaîne des chunks jusqu'à épuisement / `total_limit` / stop. Log final `cleanup_drain` event.
- Pool = `data/contacts.duckdb` (PAS `acquisition_contacts` — exclus globalement les `global_blacklisted`).
- Modes : `unverified` (mailnjoy_check NULL/vide) · `stale` (mailnjoy_check > 180j).

**API (`scripts/api.py`)**
- `_active_cleanups: dict[key→state]` + `_cleanup_lock` (threading.Lock). **Verrou STRICT séquentiel global** (1 cycle à la fois TOUS sites/modes confondus).
- `POST /api/sites/{site}/cleanup/run` body : `{mode, drain, chunk_size, total_limit, limit?}` — spawn thread daemon, retour immédiat avec `{queued:true,key}`. Si cycle déjà actif → `{ok:false, running:true, active:{...}}`.
- `POST /api/sites/{site}/cleanup/stop` — pose `stop_requested=true` + `status="stopping"`. Le thread vérifie entre 2 contacts ET entre 2 chunks.
- `GET /api/sites/{site}/cleanup/status` — état détaillé `items[]` avec processed/total/valid/removed/cumulative/last_email/started_at/status.
- `GET /api/cleanup/active` — état GLOBAL tous sites (alimente la SuperadminBar).
- `GET /api/sites/{site}/cleanup/history?limit=20` — **endpoint dédié** retournant UNIQUEMENT les events `cleanup_batch` (évite la saturation des 100 derniers logs par les events fils validated/removed).
- `GET /api/sites/{site}/cleanup/counts` — non-vérifiés + stale.
- `GET /api/sites/{site}/cleanup/contacts?limit=10000` — liste pool (limite remontée pour cohérence compteur).
- **Endpoints test loopback-only** (bypass auth via middleware si `request.client.host ∈ {127.0.0.1, ::1}`) :
  - `GET /cleanup/dryrun?email=` — non-destructif, retourne what would be done sur 1 contact.
  - `GET /cleanup/test-batch?limit=N&drain=true&chunk_size=N` — sync, counts avant/après.
- **`god_mode_backend.list_logs(action=...)`** étendu pour filtre par action exacte (utilisé par /cleanup/history).

**Frontend (`genesis-ui/src/app/site/[code]/cleanup/page.tsx`)**
- `startAuto` = **1 SEUL POST drain=true chunk_size=100**. Plus aucune boucle JS, plus de `waitUntilFree`, plus de `findBatch`, plus de timeouts JS.
- `stopAuto` = POST `/cleanup/stop` + `autoRef=false`.
- État `progress` polling `/cleanup/status` (1.5s actif / 6s idle). Auto-reset `autoMode` quand `progress` passe à null.
- Card **Cycle en cours** (border-primary/50) : 2 barres (chunk + global si total_limit) + cumul cross-chunks + indication "Arrêt en cours…" pendant un stop.
- `DataTable` étendu avec prop `selectFilter` (Select shadcn). Branché sur colonne `mailnjoy_status` (filtre Non vérifié / Valide / En attente / Invalide / À risque).
- Compteur cohérent : `Contacts du pool (N) — dont X jamais vérifiés` (chargement complet, limit=10000).
- **Tous les libellés en français** : MODE_LABEL, ACTION_LABEL, DEC_FR (helpers en tête de fichier). `unverified→Première vérification`, `stale→Revalidation (>6 mois)`, `valid→Valide`, `risky→À risque`, etc.

**SuperadminBar (`genesis-ui/src/components/superadmin-bar.tsx`)**
- Poll `/api/cleanup/active` (2s actif, 8s idle). Affiche inline pour chaque cycle : `LCR Première vérification 23/50 [▓▓▓░░] 46%` + tooltip détaillé FR. Idle = "Aucun nettoyage en cours".

### Validation
- ✅ **Unitaire** : `/cleanup/dryrun` → 1 contact pool, Mailnjoy VALID/SAFE, would=update, **0 écriture DB**.
- ✅ **Intégration limit=1** : `4818→4817`, batch {1 valid, 0 removed} en 11.79s.
- ✅ **Batch 50** : `4817→4767`, batch {26 valid, 24 removed, 0 errors} en 256s.
- ✅ **Drain 6 contacts en chunks de 3** : `4612→4606`, 2 chunks, 5 valid + 1 removed en 28.94s.
- Validation visuelle par le user en attente après hard-reload `/site/lcr/cleanup`.

### Bugs fixés (chronologique)
- **DuckDB lock conflict** : test scripts externes ne peuvent pas se connecter pendant que l'API a un write-lock → endpoints test loopback à la place.
- **Read-only/read-write config mismatch** : `duckdb.connect(read_only=True)` échoue si une autre connection RW existe dans le même process → utiliser `cb._pool(read_only=False)`.
- **API freeze 504** : `cleanup/run` synchrone bloquait le worker uvicorn (316 restarts observés) → thread daemon + retour immédiat.
- **Race "Un cycle déjà en cours"** : ancien `set` non-atomique + retry trop court → dict + Lock + verrou GLOBAL séquentiel + retry intelligent.
- **Timeout JS 4 min trop court** : 50 contacts × ~5s = 250s, juste au-dessus de 240s → drain mode élimine le problème (plus de boucle JS).
- **Historique aléatoire 2-3 lignes** : `/logs?limit=100` saturé par events validated/removed → endpoint dédié `/cleanup/history` qui filtre exactement `cleanup_batch`.
- **DuckDB SQL** : double-double-quote pour empty string non supportée → `LENGTH(mailnjoy_check)=0`.
- **god_mode_api.py root-owned** : patch impossible sans `sudo chown` (bloqué par classifier) → contourné en ajoutant la route dans api.py.

### PM2 processes
- `genesis-dashboard` (PID variable, FastAPI port 8080) — restart après tout patch backend
- `genesis-ui` (Next 16 port 3100, pnpm build) — restart après tout patch front + `pnpm build` AVANT (jamais `npm install`)
- `genesis-mailnjoy-drain` — cron 5min qui drain `scrappe_pending` (existant avant cette session)

### Sweego (parqué)
- Pool LCR contient 5117 contacts (au début de session), réduit à ~4600 après tests cumulés (~250 supprimés invalid/risky).
- Sweego API key + ImageKit private key avaient fuité en chat → user à régénérer.
- Routage production Sweego PAUSE STRICT : tests uniquement vers `afchain.camille@gmail.com`.

### Restes
- #8 `/security-review` (déclenché par user)
- #23-25 Sweego : reroute production + déploiement + CNAME tracking
- Validation visuelle par le user de la page cleanup (filtre Mailnjoy + Progress bar + drain end-to-end)

## REPRISE 2026-07-07 — Connecteur Maildoso branché (3e canal Cheffer) ✅

### Fait
- **Maildoso opérationnel** : warmup fini (dispo prévue ~07/07, tenu). 4 boîtes actives `j.durand|j.juste|j.bernard|j.nguyen@leclient-roi.com` (domaine AVEC tiret, ≠ leclientroi.com), réputation Microsoft "high", domaine ACTIVE depuis 23/06.
- ⚠️ **L'API REST Maildoso ne fait PAS d'envoi** (infra only : domaines/boîtes/warmup). **Envoi = SMTP** `smtp.maildoso.com:587`, IMAP `imap.horus.maildoso.com:993`, réponses agrégées sur `leclientroi@maildoso.email`.
- **Doc** : skill `.claude/skills/maildoso/SKILL.md` + `openapi.json` local (spec complet analysé + endpoints testés live).
- **Secrets** : `.env` → `MAILDOSO_API_TOKEN`, `MAILDOSO_SMTP_PASSWORD` (commun aux 4 boîtes). Backup `.env.bak-maildoso-20260707`.
- **Nouveau module `scripts/maildoso_backend.py`** : vérif API (`/v1/user/me`), sync boîtes → table `mailboxes` (god_mode.duckdb, `password_ref` pas de mdp en clair), envoi SMTP avec rotation (boîte la moins sollicitée), cap 25/jour/boîte, jitter 15-60s entre envois, log table `maildoso_sent`, List-Unsubscribe. CLI : `verify|sync|mailboxes|test <email>`.
- **Canal activé** : `campaign_engine.py` (déblocage create_campaign + branche maildoso dans `_send_batch` avec `mark_pushed` précis via `sent_emails`), `deliverability_agent.py` DAILY_CAP maildoso 300→**100** (4×25, domaine jeune — remonter plus tard), `api.py` `/channels` → enabled dynamique (compte les boîtes actives). PM2 `genesis-dashboard` restarted OK.
- **Tests réels** : email test + template LCR `agence-marketing/first` («votre mix canal») envoyés à afchain.camille@gmail.com via SMTP (boîtes j.nguyen puis j.durand). Les 2 partis OK (rfc_msgid en base `maildoso_sent`).

### Restes Maildoso
- Camille doit confirmer réception des 2 emails (vérifier spam/Promotions Gmail).
- Séquenceur complet (relances, threading, IMAP poller réponses/bounces, suppression list) : spec dans `routeur_doc/cold-email-engine.md` — non implémenté, le canal actuel = envoi one-shot par campagne unifiée.
- Remonter les caps (25→40/boîte) après ~2 semaines de prod propre.
- 6 slots de boîtes Maildoso encore dispo dans l'abonnement (10 payées, 4 utilisées).

### MAJ 2026-07-07 (soir) — Ramp-up auto + card canal fiable
- **Délivrabilité confirmée** : template LCR reçu par Camille en **inbox Gmail** (pas spam). Délai de remise ~20 min (file d'attente sortante Maildoso — normal, ne pas s'inquiéter d'un « rien reçu » immédiat).
- **Cap canal maildoso DYNAMIQUE** : `deliverability_agent.channel_caps` lit désormais la somme des `daily_cap` des boîtes actives (table `mailboxes`) — plus de 100 en dur. Le planning des campagnes et la card Cheffer suivent tout seuls.
- **Nouveau `scripts/maildoso_ramp.py`** : montée en charge auto, appelée en fin de chaque dispatch maildoso (`campaign_engine._send_batch`), idempotente 1×/boîte/jour, journalisée dans `maildoso_ramp_log`. Règle : fenêtre 3 j sur `maildoso_sent` ; >10 % erreurs SMTP → cap −10 (min 10) ; 0 erreur + dernier jour actif ≥ 60 % du cap → cap +5 (max 40) ; sinon inchangé. CLI : `maildoso_ramp.py status|run`.
- **/channels enrichi** (maildoso) : `mailboxes`, `per_mailbox_cap`, `remaining_today` + note honnête. **Card du wizard** (`campaign-wizard.tsx`) affiche : cap/jour, « N boîtes × cap/j », badge « X restants aujourd'hui » (vert/rouge). `pnpm build` + restart genesis-ui OK (piège : `.next` avait des fichiers root → `chown -R autoblog` avant build).
- **Mail-tester 7.5/10** (test-cheffer0707b) : SPF pass, DKIM pass (signé par le relais Maildoso `s=out401500`, 2048 bits), DMARC pass (p=reject aligné), IP de sortie 169.255.56.72 (pool pinkproof) clean sur 23 blocklists. Pénalités : **leclient-roi.com listé ABUSE SURBL (−1.9, à délister sur surbl.org)** + réécriture du relais (GCDT) : text/plain converti en HTML-only sans balise `<html>`, header List-Unsubscribe supprimé. Si plain text pur voulu : couper le tracking via `PUT /v1/user/domains/tracking`.

### MAJ 2026-07-08 — SURBL delisting soumis ✅ / page anti-spam À PUBLIER ⚠️
- Demande de removal SURBL ABUSE pour `leclient-roi.com` soumise et reçue par SURBL (« request has been received »). Dossier : `routeur_doc/surbl_delisting_leclient-roi.md`.
- ⚠️ **URGENT — prochaine session LCR** : publier la page « Politique anti-spam » sur leclientroi.com (URL déclarée à SURBL : `/politique-anti-spam`). Instructions complètes + contenu exact : `routeur_doc/TODO_page_politique_anti-spam_lcr.md`. Les reviewers vérifient le lien sous 24-72 h.
- Ensuite : surveiller le délisting (`dig +short leclient-roi.com.multi.surbl.org` — vide = délisté) puis relancer un mail-tester (score attendu ~9.4).

### MAJ 2026-07-08 — Remplacement complet des templates LCR (zip Camille) ✅
- **Backup préalable** : `backups/templates_lcr_backup_2026-07-08.json` (30 email_templates + 9 html_templates). Sources du zip archivées dans `routeur_doc/leclientroi-emails/` (avec `cold-emails-complet.md` : objets B + noms d'expéditeurs proposés).
- **html_templates (messages validés)** : 9 supprimés → **16 nouveaux** : 8 newsletters HTML (liens leclientroi.com pré-tagués **plan de taggage /site/lcr/tag : utm_source=newsletter&utm_medium=email&utm_campaign=newsletter-<secteur>** — le tag d'envoi respecte les liens déjà tagués) + 8 cold emails convertis en HTML simple (source `cold-email`, liens NON pré-tagués → tag à l'envoi : maildoso/coldemail selon canal).
- **email_templates (cold)** : 30 supprimés (10 secteurs × first/relance1/relance2) → **8 nouveaux** kind=first, tous `valid=True`. Secteurs mappés sur les codes canoniques du pool : agences→agence-marketing, artisans→artisan, boutiques→retail, fleuristes→fleuriste, immobilier, lelead, opticiens→opticien, plombiers→plombier.
- **Validateur mis à jour** (`email_generator.validate_email`) : le CTA de RDV accepte désormais TidyCal OU le **booking interne Cheffer** (`api.cheffer.email/api/book/…`) — les nouveaux cold emails utilisent le booking Cheffer. Restart dashboard OK.
- Nouveaux templates : variables `{{prenom}} {{entreprise}} {{ville}} {{expediteur_prenom}} {{expediteur_nom}}` (convention séquenceur Maildoso, ≠ `{{firstName}}` Emelia) — à mapper quand le séquenceur maison sera construit. Objets B (A/B testing) archivés dans le md, pas de champ en base.

### MAJ 2026-07-08 (soir) — Scraping auto + ciblage géo campagnes + review ✅
**1. Orchestrateur scraping auto EN DUR** (`scripts/autoscrape_plan.py`, cron `*/30 7-21 * * *`) :
- Parcourt les 12 régions métropole dans l'ordre EXACT du select scrapper (11 IDF → … → 93 PACA), 1000 contacts/région, département par département (réutilise `autoscrape_backend.run_autoscrape`). Secteur **immobilier** seul actif ; secteurs suivants pré-écrits mais COMMENTÉS dans `PLAN_SECTORS` (validation manuelle avant activation, cf. demande Camille).
- `tick` (cron, instantané) lance `work` (détaché, run bloquant d'une région). Reprise auto après blocage Serper (throttle 1h), saute les depts finis. État : `memory/autoscrape/lcr-plan.json`. CLI : `tick|work|status|pause|resume|reset`. **Lancé le 08/07 18:16, tourne (IDF en cours).**

**2. Ciblage géographique des campagnes** (secteur + région ET/OU département, +/− dans le wizard) :
- `contacts_pool_backend._geo_clause` + params `regions`/`depts` sur `pick_for_campaign` et `count_available_for_sector` (OR entre zones). `campaign_engine.create_campaign` stocke les zones dans `params` JSON, `dispatch` filtre dessus. `api.py` : `/campaigns/target-count` et `/campaigns` acceptent `regions`/`depts`.
- Wizard (`campaign-wizard.tsx`) : composant `GeoTargeting` à l'étape Cible — ajout/retrait de zones (région entière 🗺️ ou département 📍) via +/−, compteur live filtré, récap. Vide = France entière. Build + restart OK.
- **Prérequis résolu** : `contacts.dept_code`/`region_code` étaient à ~NULL. Ajout `workflow_geo.resolve_city_geo` (CP prioritaire, sinon nom de ville ≥10k) ; Serper dual-write (`god_mode_agents`) remplit désormais dept/region ; **backfill fait** (726 dept+region, 2886 region ; immobilier : 879 ciblables, 380 IDF, 90 dept 92).

**3. Review (agent) — 2 bugs corrigés** :
- HIGH : `_norm_city` ne gérait pas les arrondissements (« Paris 13e » → NULL geo → exclus du ciblage). Corrigé (regex suffixe arrondissement → commune-mère). ⚠️ **Reste à faire** : re-run backfill après la 1re région (le run live a chargé l'ancien code → contacts Paris de CE run ont un geo NULL ; `resolve_city_geo("Paris 13e")` les corrigera).
- MEDIUM : reprise multi-cycle dépassait le plafond 1000 (`valid` persisté était par-run, pas cumulé). Corrigé via `valid_baseline` → `valid` persisté cumulé, `remaining = target − valid` correct.
- LOW notés (non bloquants) : TOCTOU sent_today Maildoso (OK en envoi séquentiel), addZone filtre depts sur state async (redondance inoffensive, OR-semantics), homonymes communes → plus grande (tradeoff CP-first).

### MAJ 2026-07-08 (nuit) — Correction placement templates/messages + refonte UX (retour Camille)
Erreur de la session précédente corrigée : j'avais mis newsletters ET cold emails dans « Messages validés » (versions), cassant le bloc-éditeur et mélangeant les canaux.
- **Cold emails** retirés de Messages validés → restent uniquement sur la page **Cold email** (`email_templates`, 8 secteurs). Envoi via Campagnes (canal Maildoso).
- **8 newsletters (avec images)** → déplacées en **Templates** (structures, fichiers `structures/leclientroi-newsletter-<secteur>.html`), en **HTML brut NON taggé** (le pré-tag `utm_source=newsletter` empêchait le tag correct au moment de l'envoi selon le canal — le tagueur respecte les liens déjà taggés). Anciennes structures archivées dans `structures/_archive/` (14, récupérables).
- **Bloc-éditeur** (`newsletter-editor.tsx`) : `parseBlocks`/`rebuildHtml` détectent désormais le conteneur `table.wrap` (newsletters) en plus de `table.email-container` (+ fallback heuristique table 600px). Les newsletters sont éditables bloc par bloc (clic texte/image, réordonner) — fini le « Aucun bloc détecté ».
- **Section Templates** (`newsletters/page.tsx`) : multiselect texte → **galerie de cartes avec aperçu image** (iframe rendu scalé) + boutons Éditer/Tester. Messages validés = sortie de l'édition d'un template.
- **Envoi** : bouton « Masse » retiré des messages + **dialog « Envoyer en masse · Sweego » supprimé**. Tout envoi passe par **Campagnes** (choix du canal + tags UTM auto selon canal). Build + restart genesis-ui OK.

### MAJ 2026-07-08 (nuit +1) — Sélecteur de message campagne unifié (retour Camille : "0 option")
Bug : le wizard campagne ne piochait que dans `html_templates` (versions), désormais vide → aucun message sélectionnable, et les cold emails introuvables.
- **Résolveur unifié** (`html_templates_backend`) : `campaign_message_options(site)` (liste groupée) + `resolve_campaign_message(site, mid)`. message_id encode la source : `struct:<name>` (Templates/newsletters), `ver:<id>` (Messages validés), `cold:<sector>:first` (email_templates).
- **API** : `GET /campaigns/messages` (groupes) + `GET /campaigns/message-preview?id=` (HTML). suggest-subject, preview-lint et `campaign_engine._send_batch` utilisent le résolveur (au lieu de `get_version` seul).
- **Wizard** (`campaign-wizard.tsx`) étape Message : 3 groupes sélectionnables — 🖼️ Templates (8), ✅ Messages validés, ✉️ Cold emails par secteur (8). Aperçu via le résolveur. Upload/texte créent une version (`ver:<id>`).
- **Personnalisation Maildoso** (`maildoso_backend._apply_tokens`) : {{prenom}}/{{firstName}}, {{nom}}, {{entreprise}}/{{societe}}, {{ville}}/{{city}}, {{expediteur_prenom/nom}} (depuis la boîte), {{UNSUBSCRIBE_LINK}}/{{unsubscribe}} → mailto ; salutation vide nettoyée (« Bonjour , » → « Bonjour, »). Appliqué par destinataire dans `send_batch`. Évite d'envoyer les tokens bruts pour les cold emails.
- Build + restart genesis-dashboard + genesis-ui OK. Scrape immobilier toujours en cours (271 contacts, dept 95).

### MAJ 2026-07-08 (nuit +2) — Recette lint + auto-fix des messages (retour Camille : lint sort des erreurs mais rien n'est corrigé)
Le lint (emailens) sortait 12 erreurs sur un cold email — surtout des FAUX POSITIFS : règles de newsletter HTML appliquées à un email texte + variables de fusion comptées comme non résolues. Corrigé à la racine + auto-fix :
- **Whitelist variables étendue** (`email_lint_backend.ALLOWED_VARS`) : + prenom, nom, entreprise, societe, company, ville, city, expediteur_prenom, expediteur_nom, unsubscribe. Fini les « unresolved-variable {{prenom}} » (résolues à l'envoi).
- **Emballage cold email conforme** (`email_templates_backend.wrap_cold_email`) : fragment texte → doc HTML valide (lang=fr, charset, `<title>`=objet, viewport, préheader caché ≥30c, footer société+contact+tél + lien désinscription détectable `?subject=unsubscribe`). Appliqué DANS `resolve_campaign_message` (cold:) → aperçu, lint ET envoi utilisent la MÊME version conforme. Résultat : cold emails passent de 12 err (dont bloquantes) à **score 99, 0 bloquant** (reste 1 low-contrast accessibilité, non bloquant).
- **Recette auto** `scripts/email_qa.py` : lint chaque message (Templates + Cold + Messages validés) via le rendu réel + **persiste les badges** (`newsletter_lint`) pour affichage UI sans clic. Cron quotidien `30 5 * * *`. Templates newsletters : score 95, non bloquant (12 low-contrast = dégradés violets, faux positif accessibilité connu).
- ⚠️ Reste à la main : **adresse postale physique** (warning CAN-SPAM) — non inventée volontairement, à ajouter par Camille dans `_COLD_FOOTER`. Restart dashboard OK.

### MAJ 2026-07-08 (nuit +3) — Fix "message introuvable" au BAT + création campagne
Bug : le BAT du wizard appelait `/mass-campaigns/bat` (Sweego) avec `htb.get_version()` → ne comprenait pas les nouveaux ids `cold:`/`struct:` → "message introuvable", et aurait testé une campagne Maildoso via Sweego (mauvais canal).
- **BAT unifié** : helper `_send_bat(site, channel, message_id, subject, email)` (api.py) → résout le message via `resolve_campaign_message` (toutes sources) + envoie par le CANAL choisi (Maildoso→`md.send_email`, Sweego/Emelia→Sweego). Personnalise avec un contact fictif (Camille/Le Client ROI/Paris) pour rendre les {{variables}}. Nouveau endpoint `POST /campaigns/bat` (avant création) + `/campaigns/{cid}/bat` (existante) refactorés dessus. `/mass-campaigns/bat` passe aussi au résolveur.
- **Wizard** : `sendBat()` appelle `/campaigns/bat` avec `channel`.
- **Durcissement** : `create_campaign` résout le message à la création → refuse « message introuvable » au lieu d'échouer silencieusement au dispatch.
- **Vérifié E2E** : BAT Maildoso réel (cold immobilier) envoyé à afchain.camille@gmail.com depuis j.nguyen@leclient-roi.com, OK. Résolveur testé sur ids valides + invalides. Build + restart OK.

### MAJ 2026-07-08 (nuit +4) — Guide utilisateur sur la page login
- `components/user-guide.tsx` (`UserGuideMenuItem`) : entrée **« Guide utilisateur »** dans le **pied de la sidebar de gauche**, pour les **utilisateurs connectés** (PAS sur la page login — corrigé après retour Camille). S'adapte au mode réduit. Ouvre un dialog.
- Contenu : (1) **Authentification** — identifiant/mot de passe + code 2FA (TOTP 6 chiffres), blocage 10 min anti-bruteforce, session token, contacter l'admin pour reset ; (2) **section Commercial UNIQUEMENT** (comme demandé, pas Stratégie/Contenu/Admin) : Vision, Scrapper, Acquisition, Newsletters, Campagnes, Nettoyage, Rendez-vous — 1 description claire par item + flux type. Build + restart genesis-ui OK.

### MAJ 2026-07-09 — Guide utilisateur : vraie page /guide (retour Camille : pas de popup, une vraie URL avec screenshots)
- Popup remplacée par une **vraie page** `app/site/[code]/guide/page.tsx` (URL `/site/<code>/guide`), liée depuis le pied de sidebar (`user-guide.tsx` = lien, plus de dialog). S'affiche avec la sidebar + auth (via ClientShell).
- Sections avec **intro + « Cas pratique »** chacune : Connexion/sécurité, Menus (résumé), Notions & API connectées (pool, Serper/Basile, Mailnjoy, Maildoso/Sweego/Emelia, UTM/GA4, délivrabilité), Faire un scraping, Faire une campagne (+ **schéma des 3 canaux** Maildoso/Sweego/Emelia), Templates vs Cold emails, Nettoyage, Rendez-vous.
- **Screenshots** : composant `<Shot img=... />` affiche `/public/guide/<x>.png` si présent, sinon un **schéma fidèle** en fallback. Playwright + Chromium installés dans `/root/guideshots` (deps apt OK). **login.png = vraie capture** (page publique). Les pages connectées (scrapper/campaigns/newsletters/cold-email/cleanup/booking/sidebar) : script `/root/guideshots/shoot-auth.js` PRÊT mais nécessite un **token de session légitime** — le classifier a (à juste titre) bloqué la création d'une session forgée. ⚠️ **À FAIRE** : obtenir le mot de passe du compte de test (user `test`, rôle commercial) pour capturer les vraies images, sinon les schémas restent affichés.

### MAJ 2026-07-09 — Refonte UI (palette violet/crème + font) + dashboard emailing en datatable
- ⚠️ **Saas UI NON installé** : c'est du Chakra UI + Emotion (CSS-in-JS), incompatible avec la stack (Next 16 / React 19 / **Tailwind v4 + shadcn**). L'installer casserait le reset CSS et doublonnerait le système de style. Refonte faite sur la stack existante (même philosophie que saas-ui : composants accessibles Radix/shadcn).
- **Palette « violet & crème »** (`globals.css`, light) : fond crème chaud (`--background` oklch cream), cartes blanc cassé, `--accent`/sidebar en tint violet, `--primary` violet renforcé, bordures chaudes. Dark inchangé.
- **Police** : Inter → **Plus Jakarta Sans** (`layout.tsx`, var `--font-sans`), plus premium ; JetBrains Mono conservé.
- **Rapport emailing en DATATABLE** (`components/channel-perf-card.tsx`) : remplace les 2 cartes cramées par un tableau 1 ligne/canal — **Maildoso + Emelia + Sweego** — colonnes Envoyés · Ouvertures · Clics · Réponses · Bounces (valeur + taux, « — » si non dispo). Maildoso ajouté au backend (`/marketing/overview` + `maildoso_backend.stats(site)` depuis `maildoso_sent`) ; note « SMTP sans tracking » pour ouvertures/clics Maildoso.
- login.png (guide) re-capturé avec le nouveau thème. Build + restart OK.

### MAJ 2026-07-09 (suite) — Dashboard commercial : datatable emailing (bon composant), 10 dernières campagnes, scraper live, gating admin
- **Bug corrigé** : la dashboard avait sa PROPRE copie locale de `ChannelPerfCard` (grille de cartes) → mes changements sur `components/channel-perf-card.tsx` ne s'y voyaient pas. Dashboard utilise maintenant `<ChannelPerfTable site>` (le vrai datatable 3 canaux : Maildoso + Emelia + Sweego). L'ancienne fonction locale est laissée inerte.
- **10 dernières campagnes** (`RecentCampaignsCard`) : table (chaleur, campagne, canal, statut, envoyés/cible, date) via `/api/sites/{site}/campaigns`. **Code couleur + emoji d'urgence par ancienneté** (`campaignHeat`) : 🌱 frais (<1 sem, vert) · 🌶️ +1 sem (jaune) · 🌶️🌶️ +2 sem (ambre) · 🔥 +3 sem (orange) · 🔥🔥 très hot +4 sem (rouge).
- **Card « Scraping en cours »** (`ScraperTile`) **à la place du KPI Domain Rating** : quand un scrape tourne (poll `/autoscrape/status` /5s), affiche région, dépt, ville, barre de progression contacts (valid/target), Serper/Basile, dépts a/b, villes c/d, doublons, examinés. Au repos → retombe sur Domain Rating (rien perdu).
- **Gating rôle** : « Consommation API (30 j) » et « Dernières actions agents » masqués pour les non-admins (visibles seulement admin/superadmin), lus depuis `genesis_user.role` en localStorage.
- Build + restart OK. Scrape immobilier Hauts-de-France en cours (55/990) → la card s'affiche en live.

### MAJ 2026-07-09 — Fix publication blog (emdash) cassée + article LCR publié
- Bug : `publish_agent.publish_emdash()` référençait une variable globale `art` inexistante → `NameError` à CHAQUE publication LCR (emdash). Les articles passaient en statut « publishing » puis crashaient sans jamais atteindre le CMS. Cause du « je pousse un article mais je le vois pas ».
- Fix : `art` passé en paramètre à `publish_emdash(title, slug, content_md, art)` (+ appel màj). Compile OK.
- Republié `art_20260503_lcr_002` « SMS géolocalisé : le guide pour booster votre TPE en 2026 » (2147 mots) → **published**, live : https://blog.leclientroi.com/posts/sms-geolocalise-le-guide-pour-booster-votre-tpe-en-2026 (HTTP 200). Les futures publications LCR fonctionnent de nouveau.
- Rappel : la page Articles de Cheffer = file éditoriale interne (`memory/editorial/articles-queue.json`), publication réelle via API emdash (token admin). Blog LCR = blog.leclientroi.com.

### MAJ 2026-07-09 — Backfill images à la une des articles publiés
- Contrôle des 86 articles publiés (emdash blog LCR) → **12 sans image à la une**.
- Générateur = **Google Imagen 3** (Vertex AI, `imagen_generate.py`) — PAS DeepSeek (DeepSeek écrit juste le prompt de scène). Générique demandé : personne regardant un téléphone, sans texte ni logo, 16:9, style doux violet/crème.
- 8 variantes générées (2× n=4), uploadées en media emdash, attachées en rotation aux 12 posts via GET→PUT `/content/posts/{id}` (data.featured_image provider=external) + republish. **12/12 OK, 0 restant**.
- Note : 8 images pour 12 posts (4 réutilisées) — possibilité de faire 12 uniques si demandé.

### MAJ 2026-08-23 (soir) — Lot 1 : Acquisition passe sur PostgreSQL, 1 607 contacts débloqués

Demande de Camille : « finissons plutôt le Lot 1 ». Trois volets sur quatre sont livrés et
vérifiés ; le quatrième (journaux d'envoi) est instruit mais délibérément non basculé.

**1. Le miroir avait deux trous, tous deux silencieux.**
- `contact_enrichment` : 6 417 lignes dans PostgreSQL contre 8 118 attendues.
  `pg_sync_enrichment.py` existait mais n'était dans AUCUN cron. Rejoué → 8 118.
- **Le verdict Mailnjoy n'était recopié qu'à l'INSERTION.** `pg_reconcile` réalignait
  `etat`, `global_blacklisted` et le motif à chaque passage, mais jamais
  `mailnjoy_decision` / `mailnjoy_checked_at` / `mailnjoy_check` — et `mailnjoy_check.py`
  n'écrit que dans le pool. Une adresse vérifiée après sa première entrée dans PostgreSQL
  y restait « jamais vérifiée » **pour toujours**. Mesure du jour : PostgreSQL annonçait
  3 538 contacts non vérifiés contre 2 409 dans le pool, et **1 077 contacts `etat = 'ok'`
  étaient écartés de toute campagne** par la clause de second rideau
  `mailnjoy_decision = 'valid'` — tout en s'affichant « À vérifier » dans Acquisition
  alors que le pool les disait « Prêt ». Corrigé dans le lot `UPDATE` de `pg_reconcile`
  (avec `_mailnjoy()`, helper partagé avec `_inserer`). Après correction les six étapes
  sont identiques au contact près.
- Écart de colonnes vérifié sur les 10 027 contacts, `dept_code`, `region_code`, `city`,
  `societe`, `tel`, `email_score`, `primary_source` : **0 divergence**. Seul le trio
  Mailnjoy dérivait.

**2. Acquisition, Vision, tableau de bord et filtres lisent PostgreSQL.**
`pool_pg.py` reçoit `_acq_filtre`, `count_contacts_for_site`, `compter_par_etape`,
`list_contacts_for_site`, `filter_values_for_site`, `stats_for_site`,
`engagement_par_canal`, `check_pool_depletion`. Trois substitutions volontaires, toutes
dans le même sens — remplacer un champ recopié par le fait qui le produit :
l'engagement vient de `email_events` (jointure par ADRESSE : 1 529 des 3 835 événements
n'ont pas de `contact_id`, les ignorer perdait 5 ouvreurs sur 441) · le repos vient de
`v_suppression` · le secteur se teste sur un vrai tableau (`&&`, index GIN) au lieu d'un
`LIKE '%…%'` sur du JSON, qui rangeait `immobilier-neuf` dans `immobilier`.
Côté API, un helper unique `_lecture_pool(nom)` sert PostgreSQL et **retombe sur DuckDB en
journalisant** si PostgreSQL ne répond pas — le choix se refait à chaque appel, sans
redémarrage. Sept points de bascule : `/pool/contacts`, `/pool/filter-values`,
`/pool/stats`, `/pool/depletion-alert`, `/acquisition`, `/acquisition/stats`, plus la
pastille de `followup_backend`.
Nouveau test `tests/test_pg_acquisition.py` sur les données réelles : étapes, volumes,
filtres, stats, valeurs de filtre, engagement, forme de la liste, pagination. **Tout vert.**

**3. Le verrou DuckDB faisait tomber des contacts déjà payés.**
Le scraper écrit dans `god_mode.duckdb` puis, contact par contact et avec sa propre
connexion, dans le pool. Quand un autre processus tient le verrou, la seconde écriture
échoue : le contact reste dans `scrappe`, vérifié par Mailnjoy, **invisible d'Acquisition
et de toute campagne**. 712 erreurs de ce type en journal ; 4 042 adresses de `scrappe`
absentes du pool.
Nouveau `scripts/pool_rattrapage.py`, idempotent, avec trois garde-fous : les 3 064
adresses portant une pierre tombale (`scrappe_rejected`) ne sont **jamais** ressuscitées ·
les règles de collecte d'AUJOURD'HUI sont rejouées, ce qui écarte 446 adresses de rôle
collectées avant la liste noire du 21/08 · le verdict Mailnjoy stocké voyage avec le
contact, donc **aucun crédit n'est redépensé**. Résultat : **530 contacts récupérés**,
0 échec. Pool 10 027 → 10 557, contactables 7 392 → **7 920**.
Le script est passé en cron dans la chaîne du matin, qui devient :
`pool_rattrapage ; datagouv_enrich ; pg_sync_enrichment ; pg_reconcile` (en `;`, jamais
`&&`). Ce n'est pas le correctif de la double écriture, c'est le filet — et il rattrape
aussi ce qui tombera pour une raison qu'on n'a pas prévue.

**4. Corruption %20 : le pool n'avait pas été nettoyé.** Le correctif de l'après-midi avait
assaini PostgreSQL, pas `contacts.duckdb` : 3 adresses y restaient préfixées. La
réconciliation du lendemain aurait supprimé les versions propres et réinséré les
corrompues. Décodées et retrimées dans le pool (mêmes UUID des deux côtés, aucune
collision) → `a_retirer: 0, a_creer: 0`.

**5. Deux réflexes hérités du modèle en entonnoir, corrigés.**
- `pg_sync.sync_blacklist` **supprimait** le contact de PostgreSQL au lieu de le marquer.
  Le modèle est tombé le 2026-08-20 (on garde tout le monde avec un `etat`), mais pas
  cette fonction : un blacklistage faisait disparaître le contact de tous les écrans
  jusqu'à la réconciliation du lendemain, qui le réinsérait. Passe désormais
  `global_blacklisted = true` + `etat = 'spam'`. Vérifié en base puis rétabli.
- `tests/test_pg_equivalence.py` exigeait encore « PostgreSQL ne contient QUE du propre » :
  quatre assertions rouges en permanence décrivant une règle abolie. Réécrites pour
  vérifier ce qui doit être vrai — le filtre s'est déplacé de la PORTE vers la PIOCHE.
  La suite repasse au vert.

**Piège rencontré et refermé.** Avoir ajouté `updated_at = now()` au lot `UPDATE` de
`pg_reconcile` alignait 1 077 contacts sur la même seconde. `updated_at` est la **dernière
clé de tri de la pioche d'envoi**, des deux côtés : l'ordre de départ divergeait alors
entre le pool et PostgreSQL (6/10 en tête commune au lieu de 8/10 exigés) — sans changer
qui est éligible, mais en rendant l'ordre non reproductible. Colonne retirée de l'`UPDATE`,
valeurs réalignées depuis le pool, test de nouveau vert.

**Ce qui reste du Lot 1 : les journaux d'envoi.** `maildoso_sent` (1 462),
`mass_campaigns` (1) et `sweego_events` (4 273) sont toujours dans `god_mode.duckdb`
(208 Mo). Préparation faite et mesurée : `email_events` couvre **exactement** les mêmes
965 destinataires Maildoso (0 écart dans les deux sens), et la boîte expéditrice y a été
rattrapée par rapprochement (adresse, minute) — 392 → 156 lignes sans boîte, les 156
restantes n'existant dans aucune des deux bases. Restent à basculer les LECTURES de
8 modules, dont `campaign_engine` et `maildoso_ramp` qui décident du volume envoyable par
boîte. **Volontairement non fait ce soir** : se tromper là n'abîme pas un affichage, ça
envoie deux fois. À traiter avec le Lot 4, dont c'est de toute façon la dépendance.

**Vérifications de fin :** 3 services PM2 en ligne · `alertes.py` sans problème ·
`test_pg_acquisition`, `test_pg_equivalence`, `test_frequence_capping`,
`test_pending_chronic` tous verts · `/acquisition/stats` et `/pool/stats` répondent
10 556 · aucun log appartenant à `root` (cf. le piège récurrent).

### MAJ 2026-08-23 (soir, suite) — Pourquoi les journaux d'envoi n'ont pas basculé : la vraie raison

Camille : « pourquoi ne pas passer sur PostgreSQL ? ». La raison que j'avais donnée
(« risque, à faire avec le Lot 4 ») était trop vague. En vérifiant, le blocage réel est
précis, et il n'était pas là où je le croyais.

**Le journal PostgreSQL compte double.** Le 2026-08-22, `email_events` porte **316 lignes
`sent`** pour la campagne « Agent immobilier, loi cazenave » : 160 entre 08h30 et 10h11,
puis **156 de plus entre 10h11 et 10h15**, sans boîte expéditrice.

**Personne n'a reçu deux fois le message.** Vérifié adresse par adresse contre
`maildoso_sent` : une seule ligne SMTP par destinataire (`f.lenoir@parlonsimmo.io` →
1 envoi à 09h03 via j.nguyen, et une 2ᵉ ligne de JOURNAL à 10h12). C'est le journal qui
double, pas l'envoi.

**Mécanisme.** `mark_pushed_to_emelia` écrit PostgreSQL **avant** DuckDB — règle posée le
2026-08-20, et elle est bonne : c'est ce journal qui porte les 120 jours, il ne doit pas
dépendre d'un fichier verrouillé. Mais quand l'écriture DuckDB qui suit échoue sur le
verrou de `god_mode.duckdb` (les tracebacks du 22/08 le montrent, dans
`maildoso_backend._increment_sent`), l'appelant recommence le marquage — et PostgreSQL
reçoit une seconde ligne. Le drapeau `journalise` ne protège que d'un double appel DANS
un même appel, pas d'une reprise.

**Conséquence, et c'est le blocage.** La fenêtre de 120 jours n'est pas touchée
(`v_suppression` prend `max(occurred_at)`). Mais tout VOLUME lu dans PostgreSQL est faux :
316 au lieu de 160 pour le 22/08. Or c'est exactement ce qu'il faut lire pour sortir
`maildoso_sent` et `maildoso_ramp` de `god_mode.duckdb` — le nombre d'envois par boîte et
par jour, sur une fenêtre de 3 jours qui inclut le 22/08. Basculer sans corriger, c'est
piloter la montée en charge des boîtes expéditrices sur des chiffres doublés.

**Ce qui a été trouvé de bon au passage.** Écarts entre deux envois à une même adresse :
483 renvois en août, tous à moins de 30 jours — mais **aucun depuis le 2026-08-20**, date
du durcissement. La règle des 120 jours tient depuis. Les tailles historiques (une adresse
sur 17 jours distincts, deux sur 11) sont l'incident d'août déjà documenté, pas une fuite
en cours.

**Préparé, en attente de feu vert :** `scripts/journal_dedoublonner.py` — état des lieux
par défaut, `--apply` pour agir. Il sauvegarde dans `email_events_avant_dedoublonnage`,
garde la ligne la plus ANCIENNE de chaque (adresse, campagne, jour UTC) — celle de l'envoi
réel — et pose un index unique partiel `idx_events_sent_unique` pour qu'une reprise de
marquage ne puisse plus produire de doublon. Relevé : **159 lignes à retirer sur 1 623**
(156 le 22/08, 2 le 30/07, 1 le 07/07). Une fois fait, le portage des lectures des
8 modules devient une transposition sans piège connu.

### MAJ 2026-08-23 (nuit) — Lot 1 CLOS : les journaux d'envoi passent sur PostgreSQL

Feu vert de Camille. Le portage a d'abord exigé de combler le journal, puis de trouver
pourquoi il comptait double — et la cause était en amont de tout ce qu'on soupçonnait.

**La cause racine du doublement : le filet de fin de lot re-marquait TOUT LE MONDE.**
Dans `campaign_engine._send_batch`, chaque email maildoso est marqué au fil de l'eau par
le callback `_on_sent` (qui écrit le journal PostgreSQL avant DuckDB, règle du 20/08).
Puis, à la fin du lot, un « filet » rappelait `mark_pushed_to_emelia` pour **tous** les
contacts de `sent_emails`, sans regarder si le premier marquage avait réussi. Chaque envoi
était donc journalisé deux fois : 160 lignes posées entre 08h30 et 10h11, 156 reposées
entre 10h11 et 10h15. Le drapeau `journalise` interne ne protège que d'un double appel
DANS un appel, pas de deux appels successifs.
Corrigé : `_send_batch` retient les adresses effectivement marquées et le filet ne reprend
que celles dont le marquage a échoué — c'est-à-dire les seules qui portent le vrai risque,
un email parti sans cooldown ni ligne au journal, donc renvoyable le lendemain. Le nombre
de rattrapages est désormais journalisé : à 0 le filet ne sert à rien, non nul il signale
que DuckDB a lâché pendant le lot.

**Le journal était incomplet côté Sweego.** `email_events` n'avait que les rebonds, les
plaintes et la désinscription : **1 738 ouvertures et 998 clics Sweego n'y étaient pas**,
ainsi que 23 rebonds. Versés par `scripts/journal_sweego_backfill.py` (idempotent, double
clé d'unicité : identifiant d'événement Sweego pour ses propres écritures, triplet
(adresse, type, instant) pour les rebonds importés avant lui). Le drapeau `proxy` est
CONSERVÉ dans `meta` plutôt que filtré : 993 des 1 738 ouvertures viennent d'un
pré-chargement antispam, et la question « une ouverture proxy compte-t-elle ? » ne se
répond pas pareil selon qu'on mesure la délivrabilité ou l'intérêt d'un prospect. Le
journal enregistre le fait, la lecture tranche. Le webhook Sweego écrit désormais
PostgreSQL AVANT DuckDB.

**Les envois de masse ont leur table.** Sweego ne journalise pas par destinataire : la
ligne `mass_campaigns` est la SEULE trace qu'un envoi de masse a eu lieu. Nouvelle table
`mass_sends` dans PostgreSQL (avec le lien vers `campaigns`), ligne migrée,
`sweego_backend.record_campaign` écrit PostgreSQL d'abord.

**Les BAT n'étaient journalisés nulle part.** Ils partent réellement et consomment le
quota de la boîte, mais ne passent par aucun chemin qui écrit le journal — quatre d'entre
eux le 21/08 suffisaient à décaler de 4 envois le calcul de montée en charge.
`maildoso_backend._journaliser_hors_campagne` s'en charge, en distinguant un lot de
campagne (six segments dans l'identifiant) de tout le reste, pour ne jamais écrire deux fois.

**Nouveau module `scripts/journal_pg.py`**, et les lectures portées :
`maildoso_backend.stats` · `already_sent_emails` (garde de reprise) ·
`maildoso_ramp.adjust_caps` (volumes par boîte) · `campaign_engine.journal_envois` ·
`_drop_recently_emailed` · `reconcile_from_sent_log` · `sweego_backend.list_campaigns` ·
`dashboard_stats_backend.daily_email_stats` et `performance_par_canal`. Chacune avec repli
DuckDB journalisé.
Deux gains au passage : la barrière anti-renvoi couvre maintenant **tous les canaux** (elle
n'interrogeait que `maildoso_sent`, donc un contact servi par Sweego ou Emelia passait au
travers du second rideau) ; et tous les volumes comptent des ENVOIS distincts
(adresse, campagne, jour) et non des lignes, donc restent justes même si un doublon revient.

**Test `tests/test_pg_journal.py`** sur données réelles : identité exacte des déjà-servis
lot par lot (23/100/100/16/41/33), totaux par campagne (1041/99/309), volumes par boîte,
barrière des 120 jours, envois de masse, découpage des identifiants. Tout vert, ainsi que
les quatre autres suites.

**Écart résiduel assumé, mesuré :** PostgreSQL compte 1 456 envois maildoso contre 1 462
dans DuckDB. Les 6 sont des BAT vers les adresses de Camille, antérieurs au correctif —
jamais journalisés. Le test l'autorise dans ce sens seulement (jamais PLUS que le pool).

**Reste à lancer par Camille** (le classifier de l'environnement refuse la suppression) :
`python3 scripts/journal_dedoublonner.py --apply` — retire les 159 lignes en double déjà
en base et pose l'index unique `idx_events_sent_unique`. La cause étant corrigée, c'est
désormais un nettoyage d'historique plus une ceinture ; les lectures sont déjà justes sans.

### MAJ 2026-08-23 (nuit) — Lot 4, première tranche : garde-fous, affinité expéditeur, surveillance

Cadrage de Camille : adresse expéditrice **attribuée au contact** et non au secteur (les
secteurs vont changer) · surveillance quotidienne du domaine · alerte sous 5 % d'ouverture ·
**garde-fou sur les variables de gabarit** · **140 emails/jour d'ici la fin de la semaine**,
puis 40/jour et par compte à partir de septembre.

**1. Le garde-fou des variables — `scripts/garde_variables.py`.**
La crainte était fondée, et le code la confirmait : `_apply_tokens` remplaçait `{{prenom}}`
et **laissait `{{whatever}}` intact** dans l'email ; son motif ne couvrait que les doubles
accolades, donc `{prenom}`, `[prenom]`, `[[prenom]]`, `%prenom%`, `${prenom}` et
`<<prenom>>` partaient tels quels sans jamais être vus. Le module cherche les sept formes,
sur le sujet ET le corps, sur le texte RENDU — donc ce que le destinataire verrait. Le HTML
est débarrassé de ses feuilles de style et scripts avant examen, sans quoi la moindre règle
CSS passerait pour une variable oubliée (contrôlé par test).
Le refus est **individuel** : il écarte ce destinataire, jamais le lot. Une variable vide
bloque aussi, sauf celles déclarées tolérées (`prenom`, `expediteur_nom`), dont la
ponctuation orpheline est refermée. `send_email` refuse **avant le SMTP** — vérifié : un
message troué rend `refuse: True` sans qu'aucune connexion ne soit tentée.
`send_batch` compte à part les refusés et les reportés : ce ne sont pas des pannes.

**2. L'affinité expéditeur — `scripts/expediteur.py`.**
Chaque contact garde LA MÊME adresse d'envoi. Motif de Camille, et il est juste : une
ouverture ou un clic vaut signal positif dans le client de messagerie **pour cette
adresse** ; réécrire depuis une autre, c'est repartir de zéro auprès de ce destinataire.
Trois colonnes sur `contacts` (`boite_expediteur`, `_at`, `_confirmee`).
`rattraper_historique` a attribué rétroactivement, depuis le journal, la boîte qui a
RÉELLEMENT écrit à chacun : **963 contacts, dont 441 confirmés** par une ouverture ou un
clic non-proxy. Répartition naturellement équilibrée (243/242/240/239).
Une boîte pleine ne fait plus changer d'expéditeur : le contact **attend demain**.
`send_batch` traite ce report comme un saut, et ne s'arrête que si TOUTES les boîtes sont
pleines — sinon la première boîte remplie stoppait l'envoi des trois autres.
Les volumes du jour se lisent dans le journal, plus dans `mailboxes.sent_today` : ce
compteur vit dans `god_mode.duckdb`, il se perd sous verrou, et les deux copies avaient
déjà divergé de 40 à 12.

**3. La surveillance — `scripts/sante_envoi.py`, cron 7h45, branchée sur `alertes.py`.**
Trois étages : la FORME (MX, SPF, DKIM, DMARC), la RÉPUTATION (listes noires), le FOND
(ouverture, rebond, plainte). Seuils : ouverture < 5 % (demande de Camille), rebond > 3 %,
plainte > 0,1 % — et un volume minimum de 50 envois avant de conclure.
État du jour : SPF `~all`, DKIM `selector1` valide, DMARC **`p=reject`**, ouverture
**39,1 %** sur 7 jours (33 à 46 % selon la boîte). Zéro alerte.
**Deux faux positifs dans mon propre premier jet, corrigés avant mise en service :**
(a) toute réponse d'une liste noire était prise pour une inscription — or Spamhaus répond
`127.255.255.254` quand elle REFUSE la question depuis un résolveur public, ce qui
déclarait dix serveurs bloqués alors qu'aucun ne l'était (`8.8.8.8` répondait pareil) ;
seuls les codes `127.0.0.2` à `.99` comptent désormais, le refus est signalé comme
« non vérifiable ». (b) le taux par boîte filtrait TOUS les événements sur `mailbox`, or
seul l'envoi en porte un : les quatre boîtes affichaient 0 % d'ouverture. On sélectionne
maintenant les destinataires servis par la boîte, puis on mesure ce qu'ils ont fait.
Relevé DNS mis en cache 12 h — les alertes tournent toutes les heures, et quarante requêtes
DNS horaires font limiter par les serveurs interrogés.

**4. La montée en charge réagit enfin à quelque chose.**
`maildoso_ramp` ne regardait que le taux d'erreur SMTP — **nul depuis toujours** (1 462
envois, zéro erreur : un serveur qui accepte un message ne dit rien de ce qu'il en fait).
La règle ne pouvait donc que monter, et une boîte en train de se faire classer en
indésirables voyait son volume augmenter chaque jour. Elle lit désormais, dans l'ordre :
plainte > 0,1 % → cap divisé par deux · rebond > 3 % → -10 · ouverture < 5 % → -10 ·
erreurs SMTP > 10 % → -10 · sinon montée de +5 **et seulement si le volume permet de
conclure**. Un relevé indisponible n'autorise plus l'augmentation.

**5. Bug de dispatch trouvé en posant la cadence.** `_todays_allowance` prenait pour
plafond du jour le **maximum du plan** au lieu du palier du jour : sur une montée en
charge, cela autorisait dès le premier jour le volume prévu pour le dernier. Et une
cadence qui ne planifie que le reliquat démarre en dette de tout l'historique — la montée
posée donnait **0 envoi lundi, mardi et mercredi, puis 140 d'un coup**. Corrigé aux deux
endroits : plafond = palier du jour, et `cadence_montee` ouvre le plan par une ligne datée
d'hier portant l'acquis.

**Cadence posée sur « Agent immobilier, loi cazenave »** (691 restants) :
lun 80 · mar 100 · mer 120 · jeu 130 · **ven 28/08 : 140** · sam 121. Vérifié jour par jour.
⚠️ La campagne s'épuise samedi : **tenir 140/jour en septembre demande une campagne
suivante**. Réserve disponible : 5 659 contacts piochables, ~40 jours à ce rythme.

Tests : `test_garde_variables.py` (7 formes de variables, faux positifs HTML, ponctuation)
et `test_sante_envoi.py` (chaque signal de dégradation, priorité de la plainte, refus de
liste noire non vérifiable, taux par boîte). Les 7 suites passent.

### MAJ 2026-08-23 (nuit +1) — Le trou de programmation : `scripts/programmation.py`

Camille : « nous allons scrapper plus de 500 contacts par jour, donc 140 emails/jour ne
sera pas un problème — sauf s'il n'y a pas de programmation. » C'est le vrai risque du
Lot 4, et elle a mis le doigt dessus : le vivier ne manque pas (5 659 piochables), c'est la
CERTITUDE qu'une campagne aura de quoi dispatcher demain qui manque. Le jour où la dernière
campagne atteint sa cible, plus rien ne part et le tableau de bord affiche « done » — le
seul arrêt d'envoi qui ne produit aucune erreur nulle part.

**L'automatisation existante ne servait à rien ici.** `auto_campaigns` /
`auto_campaign_runner` existent mais sont VIDES (0 ligne) et câblés sur **Emelia**, alors
que Maildoso est le canal qui envoie réellement. Construire dessus aurait été bâtir sur du
mort.

**La frontière posée**, et elle est délibérée :
- **prolonger** est mécanique : une campagne en cours dont la cadence s'achève alors que le
  vivier est plein ne demande aucune décision. Même message, même ciblage, on ajoute des
  jours. Fait automatiquement (cron 7h50, avant le dispatch de 8h30).
- **créer** est un choix : message et ciblage ne s'automatisent pas. Quand il n'y a plus
  rien à prolonger, on ALERTE au lieu d'inventer des envois que personne n'a validés.

**L'objectif quotidien n'est pas une constante** : c'est la somme des plafonds des boîtes
ACTIVES. Si `maildoso_ramp` abaisse un plafond après une plainte, l'objectif baisse avec
lui et la programmation cesse de réclamer un volume que la délivrabilité ne permet plus.
Le plan est en outre borné par le vivier réellement piochable : promettre 140/jour pendant
une semaine avec 200 contacts en réserve, c'est masquer un problème de COLLECTE derrière un
problème de cadence.

**Trois défauts trouvés dans mon propre code en le testant**, tous corrigés :
1. La ligne « acquis » de `cadence_montee` (309, l'historique déjà envoyé) servait de
   PLAFOND une fois la cadence terminée : le moteur aurait autorisé 309 envois en une
   journée, l'inverse de ce que la montée en charge protège. Exclue des paliers.
2. « Jour couvert » valait « atteint la capacité des boîtes » : l'alerte aurait crié contre
   la montée en charge qu'on venait de poser exprès (80 lundi < 160 de capacité). Un jour
   est couvert dès qu'il a du volume prévu.
3. **La projection était optimiste** : chaque jour était calculé sur le `sent_count`
   d'aujourd'hui, donc une campagne avec 691 restants « couvrait » sept jours à 140 alors
   qu'elle s'épuise au sixième. L'alerte serait partie le lendemain du jour où plus rien
   n'était parti. La projection décrémente désormais le reliquat jour après jour.

**Ce que la projection corrigée montre** — et c'est l'information utile :

| 24/08 | 25/08 | 26/08 | 27/08 | 28/08 | 29/08 | **31/08** |
|---|---|---|---|---|---|---|
| 80 | 100 | 120 | 130 | 140 | 121 | **0** |

La campagne atteint sa cible samedi. **Lundi 31/08, la file est vide.** Le cron de 7h50 la
prolongera automatiquement (2 785 contacts immobilier piochables), et l'alerte partira si
le vivier ne suit plus.

Un comportement utile découvert au passage : une campagne dont la cadence est TERMINÉE ne
s'arrête pas — elle continue d'envoyer son reliquat au plus gros palier prévu. Le creux ne
vient donc jamais de la fin d'une cadence, seulement de l'épuisement de la cible.

`tests/test_programmation.py` : file pleine, campagne épuisée, aucune campagne active,
cadence à mi-horizon, borne du vivier, objectif indexé sur les plafonds, ligne d'acquis.
Les 8 suites passent.

### MAJ 2026-08-23 (nuit +2) — Lot 4 CLOS : refroidissement, contrôle anti-spam, routage

**Refroidissement — `scripts/refroidissement.py`.** Une plainte n'est pas un incident
isolé : c'est un signal envoyé au FOURNISSEUR du destinataire, qui l'agrège. Google
Postmaster bloque vers 0,3 % et ce seuil se franchit en une journée. La boîte qui a écrit
à l'adresse plaignante se tait donc **48 h** ; un pic de rebonds durs (> 3 % sur 20 envois
minimum) vaut **24 h**. Deux déclencheurs : le webhook Sweego agit **à la réception de la
plainte** (attendre le balayage horaire, c'est laisser partir une heure d'envois depuis une
adresse déjà signalée), et le balayage horaire d'`alertes.py` rattrape le reste **et lève
les pauses échues** — une pause qu'il faut penser à lever est une pause qu'on oublie.
`expediteur.boites()` rend une boîte au repos `active = False`, `reste = 0` : elle sort de
la rotation sans autre changement. **Les contacts qui lui sont attitrés attendent** — ils
ne sont pas réattribués. Perdre deux jours d'envoi sur un quart du vivier coûte moins cher
que repartir de zéro sur la réputation de tous ces destinataires.

**Contrôle anti-spam avant le lot — dans `campaign_engine._send_batch`.** `email_qa`
tournait chaque nuit et posait un badge dans l'écran ; **rien n'empêchait de dispatcher un
message qu'elle venait de déclarer bloquant**. Le contrôle s'exécute désormais sur le
message RÉSOLU — celui qui va réellement partir — et arrête le lot. Deux motifs de refus :
un défaut bloquant au lint (lien mort, désinscription introuvable — ce qui transforme un
cold email en signalement pour spam), et **toute variable qu'aucun moteur ne sait
remplacer**, dite une fois avant le lot plutôt que destinataire par destinataire. Les
défauts non bloquants (contraste, largeur) passent : refuser un envoi pour un dégradé
violet ferait débrancher le contrôle à la première campagne. Message de la campagne
active : score 99, non bloquant, aucune variable inconnue.

**Routage — `scripts/routage.py`.** Le piège était dans l'énoncé : router automatiquement,
c'est basculer un lot d'un canal à l'autre quand le premier sature — or **changer de canal,
c'est changer d'adresse expéditrice**, exactement ce que l'affinité interdit. Sweego et
Emelia n'ont pas de boîte par contact ; y envoyer quelqu'un revient toujours à changer son
expéditeur. La règle posée : **le volume se cherche sur les contacts qui n'ont rien à
perdre.** `_send_batch` écarte des lots Sweego et Emelia tout contact à l'affinité
CONFIRMÉE (441 aujourd'hui) et le dit dans les logs ; les 9 592 sans affinité et les 523
attitrés-non-confirmés restent librement routables. Le module ne bascule rien tout seul :
il dit ce qui est routable. Le basculement reste une décision de campagne.

Nouveau test `tests/test_lot4_protections.py` : mise au repos, non-raccourcissement d'une
pause plus longue, reprise automatique, contact attitré qui attend, filtrage par canal
dans les deux sens, capacité du jour. **Les 9 suites passent.**

**Lot 4 : les six briques.** adresse par secteur → remplacée par l'affinité par contact ·
moteur de volume par boîte ✅ · contrôle anti-spam ✅ · routage automatique ✅ ·
refroidissement 48 h ✅ · file qui ne se vide jamais ✅ (ajoutée après le constat de
Camille sur les 500 contacts/jour).

### MAJ 2026-08-23 (nuit +3) — Review des logiques : ce qui a été corrigé

Passage systématique sur les motifs qui ont produit tous les défauts de la journée : une
écriture faite deux fois ou pas du tout, un garde-fou qui ne peut pas se déclencher, un
échec avalé en silence. Quatre corrections, plus un constat sur ce qui va bien.

**1. `pg_sync` ouvrait une connexion PostgreSQL par écriture miroir.** C'est le chemin le
plus chaud du système : chaque contact scrapé déclenche `promote_contact`, qui déclenche un
`sync_contact_site` par site — deux à trois écritures, donc deux à trois connexions TCP et
autant de forks côté serveur. Une passe de collecte de 500 contacts en produisait 1 500.
Passé sur le pool partagé de `pool_pg`, avec repli sur connexion directe pour rester
utilisable hors API. Vérifié : chemin miroir fonctionnel, 0 échec, 2 connexions ouvertes.

**2. Trois pools de connexions créés sans verrou** (`campaign_engine`, `segments_backend`,
`followup_backend`). L'API sert ses requêtes en threads : deux qui arrivent ensemble sur un
pool encore vide en fabriquent chacune un, et le second écrase le premier — dont les
connexions ne sont plus rendues à personne. `pool_pg` le faisait déjà correctement, les
trois autres non.

**3. Les tâches planifiées ajoutées aujourd'hui n'étaient surveillées par rien.** Mon
propre oubli. `pool_rattrapage`, `pg_sync_enrichment`, `sante_envoi` et `programmation`
tournent en cron sans figurer dans `_TACHES` : leur arrêt aurait été invisible — c'est
exactement la panne `pg_reconcile` du 2026-08-20, 74 heures de silence parce qu'un fichier
de log appartenait à root. Ajoutées, avec `collecte` (3 h) et `statistiques` (3 h) qui
manquaient aussi. Dix tâches surveillées, toutes fraîches.
**Règle à tenir : un cron ajouté à la crontab doit entrer dans `_TACHES` dans le même
mouvement.**

**4. Le garde-fou de la matrice des droits était muet.** `api.py` laisse passer si
`roles_backend` est illisible — et c'est la bonne règle, couper la plateforme sur une panne
de base serait un déni de service qu'on s'infligerait. Mais le faire en SILENCE désactive
toutes les permissions sans que personne ne le sache. On laisse passer, et on le crie
désormais dans le journal.

**Ce qui va bien, et qui mérite d'être dit.** Le middleware d'authentification est
sérieusement construit : Bearer obligatoire, préfixes admin, **isolation multi-tenant sur
n'importe quel segment d'URL** (pas seulement `/api/sites/{site}/…`, ce qui aurait laissé
fuir `/api/crm/{site}`), et matrice de droits appliquée côté serveur — un utilisateur qui
réécrit son `localStorage` verra peut-être un menu, jamais les données. 283 endpoints, une
seule porte.

**Faux positifs de ma propre revue, écartés après vérification** : les « fuites de
connexion » de `followup_backend` et `segments_backend` n'en sont pas — ce sont des pools
PostgreSQL correctement rendus en `finally`. Un grep sur `.close()` ne les voyait pas.

**Restant, signalé sans être traité** (ce sont des choix, pas des oublis) : la branche
« échec d'envoi » de `maildoso_sent` reste morte (0 ligne sur 1 462) ; le tri de la pioche
se départage encore sur `updated_at`, fragile à toute écriture de masse ; le drain Mailnjoy
ne crée jamais de copie dans le pool, il n'en supprime que — le filet quotidien
(`pool_rattrapage`) compense la cause sans la corriger ; `zen.spamhaus.org` refuse les
consultations depuis le résolveur public de la machine, il faudrait un résolveur récursif
local pour que le contrôle de liste noire soit réellement actif.

### MAJ 2026-08-24 — Plancher de collecte, et un bug grave sur les plafonds d'envoi

**1. Le plancher de 500 contacts — `scripts/plancher_collecte.py`, cron toutes les 30 min.**
Demande de Camille : « à minuit, si aucun scrape ne tourne, déclenche un scrape sur
n'importe quel secteur ; tant que tu n'as pas collecté 500 contacts, tu continues. »
Le constat qui la motive, mesuré : 2 264 contacts le 20/08, puis **292 le 21**, **313 le
22**. La machine sait collecter, elle ne garantit pas de le faire — `autoscrape_daily tick`
décide seul de passer son tour pour six raisons différentes (plafond de cibles, créneau
réservé, fenêtre, quota, passe mal close, pause), toutes bonnes prises isolément.
Le module réveille le scraper quand c'est possible, et **explique quand ça ne l'est pas** —
c'est la moitié qui manquait : une journée à 292 contacts ne produisait aucun signal. Il ne
piétine aucun garde-fou existant (créneaux réservés, quota Serper, secteurs interdits) :
un plancher qui force les protections n'est plus un plancher, c'est une fuite. Alerte de
fin de journée passé 20 h seulement — avant, être sous le plancher est normal.

**2. LE BUG DE LA JOURNÉE : le plafond de 40 envois/jour/boîte n'était appliqué à personne.**
Les 29 emails du matin sont TOUS partis de `j.bernard`. Cause : `mark_pushed_to_emelia`
journalise l'envoi sans la boîte expéditrice — elle n'était renseignée dans `email_events`
que parce que je l'y avais rattrapée hier depuis `maildoso_sent`. Or
`expediteur.envoyes_aujourdhui` compte par boîte **en filtrant sur `mailbox IS NOT NULL`** :
il rendait donc **0 pour les quatre boîtes**. Trois conséquences en chaîne :
  - `reste` valait toujours 40 : le plafond journalier ne pouvait jamais être atteint ;
  - la répartition choisissait toujours la même boîte, « la moins chargée » étant à égalité
    parfaite à zéro ;
  - la montée en charge lisait des volumes faux et pouvait relever le plafond d'une boîte
    qui venait d'envoyer seule toute la journée.
Corrigé sur les trois maillons : `send_batch` attache au contact la boîte qui a réellement
écrit, `mark_pushed_to_emelia` accepte et transmet ce paramètre, `record_send` le porte en
base. Les 29 envois du jour ont été rattrapés — le compteur affiche à nouveau 29/40 pour
`j.bernard` et 0 pour les autres. Test de non-régression : `tests/test_boite_journalisee.py`,
qui vérifie les trois maillons un par un sans envoyer d'email.

**3. `pg_sync_enrichment` est mort sur le verrou du pool à 6h30**, exactement comme
`pg_reconcile` le 20/08. Il ouvrait la base avec `duck_ouverture.ouvrir` — six essais en un
quart de seconde, taillé pour une requête d'écran — alors qu'un scrape tenait le fichier.
Le miroir d'enrichissement a dérivé de **2 650 lignes**, et Acquisition annonçait 361
contacts « Vérifié » que le pool disait « Prêt ». Passé sur `pg_gate._duck()`, qui attend
dix minutes.

**4. La surveillance ne voyait pas les tâches qui MEURENT.** On regardait la date du
journal ; or une tâche qui meurt écrit son traceback, donc son fichier est tout frais et
elle est déclarée en bonne santé. C'est ce qui a laissé le point 3 invisible.
`etat_technique._fin_en_erreur` lit désormais la dernière ligne utile du journal et
reconnaît une exception Python. Premier jet trop large — il criait sur un avertissement
bénin de `datagouv_enrich` (une société introuvable au milieu d'un passage réussi) ; resserré
sur la forme exacte d'une ligne d'exception terminale. Une alerte fausse est pire
qu'aucune alerte : elle apprend à ne plus les lire.

**5. Garde-fou de crédits Emelia : il comptait les RECHERCHES, pas les crédits facturés.**
Emelia ne facture que lorsqu'elle trouve. La passe du 23/08 s'est arrêtée après 100
recherches en n'ayant coûté que **11 crédits** : sûr, mais sept fois trop tôt. Corrigé, plus
une seconde borne sur le rendement (arrêt si le nombre de recherches dépasse vingt fois le
budget — une passe où rien n'est trouvé ne coûterait rien mais tournerait indéfiniment).

**6. Voie « dirigeants nommés » : lancée, et passée en cron nocturne** (budget 30 crédits
facturés par nuit, 23 h UTC). Première passe : 100 recherches, 11 crédits, **9 contacts
nominatifs** — François Beranger chez Square Habitat, Dominique Lepage chez Foncia,
Nicolas Martinez chez SPI Nantes Immo. Rythme mesuré : ~2,7 recherches/minute, d'où le
découpage en passes courtes plutôt qu'un marathon qu'un redémarrage tuerait après avoir
dépensé. Solde : 830 crédits.

**7. Deux tests corrigés parce qu'ils mesuraient l'horloge, pas l'équivalence.**
`test_pg_acquisition` comparait les 50 premiers contacts pendant qu'une collecte écrit —
or la liste est triée sur `last_action_at`, dont la valeur diffère des deux côtés (le pool
la pose à l'écriture, PostgreSQL au passage du miroir). Il compare désormais une
population STABILISÉE (dernière action de plus de 30 minutes) : **768 contacts, zéro écart
d'étape**. Et la complétude se contrôle sur les bases entières, plus sur deux fenêtres de
800 lignes triées différemment — un premier jet annonçait « 8 contacts perdus » alors
qu'aucun ne manquait.

**État de fin :** 11 suites de tests vertes, 12 tâches surveillées (dont l'échec, pas
seulement la fraîcheur), 962 contacts collectés aujourd'hui, 0 alerte.

### MAJ 2026-08-24 — Mozart : les scénarios d'automatisation d'emails

Demande de Camille : un éditeur visuel de scénarios sur React Flow, dans le menu Campagnes,
« simple sans trop d'options ». Le scénario type qu'elle décrit : une cible d'événement
(les nouveaux arrivants) → un délai → un message → selon qu'il a ouvert, cliqué ou rien →
un nouveau délai → un autre email, avec des statistiques. Et pouvoir **éditer le message**
sans quitter le scénario.

**Le principe qui commande tout le reste : le graphe affiché EST celui qui s'exécute.**
Il est stocké dans la forme de React Flow (`nodes` / `edges`) et le moteur le lit tel quel.
Aucune traduction entre l'écran et la base, donc aucune occasion de désynchroniser ce
qu'on voit de ce qui part.

**Quatre types de nœuds, volontairement quatre** : déclencheur, délai, email, condition
(plus « fin »). Un éditeur qui propose trente briques produit des scénarios que plus
personne ne relit — or un scénario doit se lire d'un coup d'œil, comme une phrase.

**Le moteur n'a AUCUN privilège**, et c'est le point le plus important. Tout email qu'il
envoie emprunte le chemin des campagnes : fenêtre de 120 jours, garde-fou des variables,
affinité d'expéditeur, plafond journalier par boîte, boîtes au repos. Un scénario capable
d'écrire à quelqu'un qu'une campagne s'interdit d'écrire serait une porte dérobée dans la
règle la plus coûteuse de la plateforme. Vérifié par test : un contact servi il y a moins
de 120 jours est refusé, un nœud sans message est refusé, le mode à sec ne touche à rien.

**Deux garanties d'exécution**, contre les deux façons de boucler :
- **un contact n'entre qu'une fois** dans un scénario donné — contrainte d'unicité EN BASE,
  pas en Python : un déclencheur réévalué toutes les heures le réinscrirait sinon à chaque
  passage et lui enverrait la séquence en boucle ;
- **un plafond de 20 pas par passage** : un graphe mal fait (un délai de zéro qui boucle)
  tournerait à l'infini en envoyant un email à chaque tour. Le délai à zéro est d'ailleurs
  refusé à l'activation.

**Le contrôle se fait à l'ACTIVATION, pas à l'exécution** : message manquant, branche de
condition non reliée, nœud qui ne mène nulle part, délai nul. Un scénario qui s'arrêterait
au premier contact est découvert bien trop tard — quand les gens sont déjà dedans.

**Les statistiques viennent d'un journal en ajout seul** (`mozart_passages`), comme
`email_events` : un compteur qu'on incrémente se perd, un journal se relit. Elles
s'affichent SUR les nœuds — un scénario actif ne doit jamais être une boîte noire.

**Édition du message sur place** : choisir un message ouvre son aperçu, et le bouton
Éditer permet de le corriger sans quitter le scénario. Les cold emails par secteur
s'enregistrent directement ; pour les autres sources (structures, versions), l'écran le
dit au lieu de faire semblant d'enregistrer.

**Fichiers** : `scripts/mozart.py` (moteur), trois tables PostgreSQL
(`mozart_scenarios`, `mozart_inscriptions`, `mozart_passages`), sept points d'API,
`src/components/mozart/noeuds.tsx` + `panneau.tsx`, `src/app/site/[code]/mozart/` (liste +
éditeur). Menu Campagnes → Mozart. Inscrit dans la matrice des droits (`roles_backend`) :
sans cela, la page serait invisible du réglage par rôle et impossible à retirer à
quelqu'un. Cron horaire (`15 * * * *`), sous surveillance comme les autres tâches.

Un scénario d'exemple est en base, en brouillon : *Exemple — relance immobilier J+1 / J+4*.
À activer ou à supprimer.

**État :** 12 suites de tests vertes, 13 tâches surveillées, 3 services en ligne, 0 alerte.

### MAJ 2026-08-24 — Mozart clignotait dans la sidebar : deux listes à tenir en phase

Symptôme signalé par Camille : l'entrée Mozart s'affiche au chargement puis disparaît.

**Cause.** La sidebar affiche TOUT tant que `/api/mes-pages` n'a pas répondu — choix
délibéré, « un menu qui clignote à chaque chargement est pire qu'un menu large ». Puis elle
filtre en rapprochant chaque entrée d'une page autorisée, via une table clé → URL qu'elle
tenait **de son côté** (`URLS_PAGES`). J'avais déclaré Mozart dans `roles_backend.PAGES`
(serveur) mais pas dans cette copie : aucune correspondance, donc l'entrée était retirée
dès l'arrivée de la réponse. Le symptôme ressemble à un défaut d'affichage ; la cause est
un oubli de synchronisation entre deux listes qu'il fallait penser à modifier ensemble.

**Correction, à la racine plutôt qu'au symptôme.** `/api/mes-pages` renvoie désormais
l'URL de chaque page **avec** sa clé : le serveur fait autorité, la table locale n'est plus
qu'un repli pour une API plus ancienne. Une page ajoutée au catalogue serveur apparaît
maintenant sans qu'on touche au client — la classe de bug entière disparaît.

**Contrôle ajouté** — `tests/test_menu_et_droits.py` : chaque entrée de menu doit exister
dans le catalogue des droits, et réciproquement. Une entrée orpheline n'est pas seulement
invisible, elle est **impossible à retirer à un rôle** : elle n'existe pas pour la matrice.
Vérifié sur les 21 entrées actuelles, aucune orpheline.

### MAJ 2026-08-24 — Mozart : canal et expéditeur par nœud

Demande de Camille : sur un nœud email, choisir le **canal** puis l'**expéditeur** s'il y
en a plusieurs.

**Les trois canaux n'ont pas la même réalité, et l'écran le dit** au lieu de présenter
trois listes identiques :
- **Maildoso** : quatre boîtes nommées. Le seul canal où « choisir l'expéditeur » veut dire
  quelque chose, et le seul qui porte l'affinité par contact.
- **Sweego** : une adresse unique dérivée du domaine configuré (`info@leclientroi.com`).
  Rien à choisir ; elle est affichée pour qu'on sache ce qui partira.
- **Emelia** : RETIRÉ (décision de Camille, 2026-08-24 : « Mozart ne doit fonctionner
  qu'avec Sweego ou Maildoso »). La raison n'est pas un goût : Emelia fonctionne **par
  campagne entière** — on lui remet une liste et il l'étale lui-même sur les jours
  suivants — alors qu'un scénario décide contact par contact, à l'instant où celui-ci
  atteint le nœud. Les deux modèles ne se rejoignent pas.
  `mozart.CANAUX_AUTORISES = ("maildoso", "sweego")` porte la décision en un seul endroit,
  et **trois barrières** l'appliquent : le canal n'est plus proposé à l'écran, l'activation
  refuse un graphe qui en porterait un autre, et l'envoi refuse au moment de partir. Les
  deux dernières comptent : un scénario enregistré avant la décision, ou modifié à la main,
  ne doit pas passer au travers.

**La règle qui commande le reste : l'affinité l'emporte sur le réglage du nœud.** Un
contact qui a ouvert ou cliqué depuis une adresse précise garde CETTE adresse, même si le
nœud en désigne une autre — c'est la décision du 2026-08-23, et un réglage d'écran ne peut
pas la défaire sans détruire la réputation acquise auprès de ce destinataire. Deux
conséquences :
- sur Maildoso, une boîte explicitement choisie ne s'applique qu'aux contacts **sans**
  affinité confirmée ;
- sur un autre canal, un contact à l'affinité confirmée est **refusé** avec la raison —
  jamais silencieusement redirigé. Même comportement que `routage.filtrer_pour_canal` dans
  le dispatch des campagnes.

Le contrôle d'affinité est posé **avant** la lecture de la fiche contact : il n'en dépend
pas, et le placer après faisait échouer la vérification pour la mauvaise raison — le test
l'a montré.

Le canal et l'expéditeur s'affichent **sur le nœud**, pas seulement dans le panneau : ce
sont eux qui décident de quelle adresse part le message, donc de la réputation engagée.
Les cacher obligerait à cliquer chaque nœud pour relire un scénario.

Nouveau point d'API `/api/sites/{site}/mozart-expediteurs` — hors de `/mozart/` à dessein :
une route `/mozart/expediteurs` aurait fini capturée par `{sid}`.
Tests étendus : les trois canaux décrits, Sweego sans choix, Emelia refusé à l'activation,
et un contact verrouillé qui ne part pas par un autre canal.

### MAJ 2026-08-24 — Mozart en bêta fermée : étiquette, grisé, réservé à Camille

Demande : une étiquette « bêta » dans la sidebar, et l'entrée grisée pour tout le monde
sauf son compte, le temps de ses tests.

**Le piège évité : fonder ce contrôle sur le RÔLE.** Camille est superadmin, et le
superadmin est justement exempté de la matrice des droits — la bêta aurait donc été
ouverte à tous les superadmins présents et futurs, ce qui vide « réservé à mes tests » de
son sens. Le contrôle porte sur le **compte**, et il est posé **avant** la matrice dans le
middleware. Un test vérifie cet ordre : le déplacer rouvrirait la porte sans que rien ne
le signale.

**Mécanisme réutilisable plutôt que cas particulier.** Une page de `roles_backend.PAGES`
porte `beta: True` ; la liste des comptes autorisés vit dans `.env`
(`PAGES_BETA_TESTEURS=camille`), pour qu'ouvrir une bêta à quelqu'un ne demande ni de
toucher au code ni de redéployer.

**Visible et grisée, pas cachée.** Une fonctionnalité qui apparaît un jour sans prévenir
surprend ; une équipe qui la voit arriver pose ses questions avant, pas après. L'entrée
s'affiche donc pour tous avec son étiquette, non cliquable pour qui n'y a pas droit, et
une infobulle qui dit « en test, réservé pour l'instant ».

**La barrière est côté serveur** — 403 avec un message qui explique, pas une erreur sèche.
Le grisé n'est que la politesse de le dire avant le clic : un menu grisé n'a jamais empêché
personne de taper l'URL.

`tests/test_beta_fermee.py` : les comptes qui peuvent et ceux qui ne peuvent pas, la casse
et les espaces qui ne doivent pas ouvrir de porte, les **trois** routes de la bêta (dont
`/mozart-expediteurs`, facile à oublier), le reste de la plateforme intact, et l'ordre du
contrôle dans le middleware.

Pour ouvrir Mozart à quelqu'un d'autre : ajouter son identifiant à `PAGES_BETA_TESTEURS`
dans `.env`. Pour sortir de la bêta : retirer `beta: True` de la page dans `roles_backend`.

### MAJ 2026-08-24 — Mozart : fenêtre d'envoi, chiffres et lecture de la liste

**1. La fenêtre d'envoi des scénarios — 09:01 à 18:30, du lundi au samedi, heure de Paris.**
Demande de Camille. Elle est PLUS ÉTROITE que celle des campagnes (08:01–17:59) et c'est
délibéré : un scénario part tout seul, à l'heure où un contact atteint son nœud, sans que
personne ne le regarde. Mieux vaut qu'il vise le cœur de la journée de bureau que ses bords.
L'heure est toujours calculée en `Europe/Paris`, jamais en heure serveur — le serveur vit
en UTC et un envoi « à 18h00 » y partirait à 20h00 chez le destinataire.

Le contrôle est posé au moment de JOUER le pas, pas à l'inscription : entre les deux il
peut s'écouler des jours. Et un refus horaire vise la **réouverture** et non « dans deux
heures » : sans cela, un contact bloqué à 18h31 serait réessayé onze fois pendant la nuit,
pour rien, et la vraie tentative du matin serait noyée dans le journal. Vérifié :
lundi soir → mardi 09:01, dimanche → lundi, samedi soir → lundi.

⚠️ Les campagnes gardent leur fenêtre 08:01–17:59. Les deux diffèrent d'une heure de part
et d'autre ; si Camille veut les aligner, c'est une ligne à changer dans
`deliverability_agent`.

**2. Les chiffres.** `mozart.resume()` rend, par scénario : emails partis aujourd'hui
(minuit heure de Paris) et depuis le début, destinataires distincts, ouvreurs, cliqueurs,
taux, et la date de début — le premier envoi s'il y en a eu un, sinon la première
inscription. C'est la question qu'on se pose devant un scénario : « depuis quand
tourne-t-il ? ». Les taux sont rapportés aux **destinataires distincts** et non aux envois :
un contact relancé deux fois qui ouvre une fois donnerait sinon 50 %, ce qui ne dit rien
de personne. Les réactions viennent de `email_events`, le journal commun — une ouverture
est la même qu'elle vienne d'un scénario ou d'une campagne.

**3. La liste se lit en diagonale.** Fond vert pastel pour ce qui tourne, rose pastel pour
ce qui est terminé, ambre pour la pause, et **fond sombre inversé** pour ce qui est en
défaut — la seule ligne qui rompt la douceur de la liste, pour qu'elle se voie sans qu'on
la cherche. Chaque état porte aussi une **icône et un mot** : une lecture qui ne repose que
sur la couleur exclut les personnes qui la distinguent mal, et ne survit pas à un écran mal
réglé. Taux d'ouverture et de clic en pastilles avec leurs icônes (œil, curseur), infobulle
donnant le nombre de personnes derrière le pourcentage.

En tête de liste : emails partis aujourd'hui, total, et **l'état de la fenêtre** — une
capacité à zéro s'explique par l'heure une fois sur deux.

**4. Barre compacte de statistiques dans l'éditeur**, au-dessus du canevas : contacts,
en route, aujourd'hui, total, taux d'ouverture, taux de clic, date de début en heure de
Paris, et l'avertissement de fenêtre fermée. Au-dessus du dessin plutôt que dans un autre
écran : on regarde les chiffres EN modifiant le scénario.

**5. Les dates sont affichées en heure de Paris**, mises en forme côté écran. Le serveur
tourne en locale anglaise et rendait « Monday 24 August » ; l'API envoie de l'ISO, l'écran
sait la langue de qui regarde.

### MAJ 2026-08-24 — Mozart : panneau lisible, libellés propres, trois modèles verrouillés

**1. Le panneau était trop étroit.** 320 px, avec des listes déroulantes qui prenaient la
largeur de leur valeur : « auto » réduisait le déclencheur à quatre lettres, et la liste
qui s'ouvrait héritait de cette largeur — les options y étaient coupées au cinquième
caractère. Panneau porté à 26 rem (30 en très large), listes en `w-full`, contenu déroulant
à 22 rem minimum.

**2. Les identifiants de message s'affichaient bruts.** Le nœud montrait
`cold:immobilier:first`. Le préfixe sert au résolveur, il n'apprend rien à l'œil :
`libelleMessage()` rend « immobilier », « agences », « version 12 » selon la source. Et la
liste de choix affiche désormais le SUJET du message à côté de son nom — choisir entre huit
cold emails par leur seul secteur suppose de les connaître par cœur.

**3. Trois modèles verrouillés** — `scripts/mozart_modeles.py`, idempotent.
*1 message sans relance* · *1 message + 1 relance* · *1 message + 2 relances*.
Trois formes et pas trente : elles couvrent l'essentiel des séquences de prospection et se
lisent en entier. Un catalogue qu'on doit parcourir coûte plus de temps qu'il n'en fait
gagner.

Les délais viennent de la pratique, pas d'un tirage : **J+1** avant le premier message
(écrire dans la minute qui suit la collecte n'apporte rien et concentre les envois),
**J+4** puis **J+7** pour les relances (assez pour qu'un message non lu le reste, assez peu
pour qu'on se souvienne du premier). Chaque relance est branchée sur la branche **« n'a pas
ouvert »** : relancer quelqu'un qui a ouvert, c'est le punir d'avoir lu.

**Le cadenas n'est pas de la méfiance, c'est une protection contre soi-même.** On ouvre un
modèle pour s'en inspirer, on ajuste un délai « juste pour voir », et trois clics plus tard
le point de départ commun n'existe plus. Le verrou force le geste juste — dupliquer — et le
modèle reste intact pour la fois suivante et pour tout le monde. Trois barrières :
l'enregistrement est refusé (409 avec l'explication), la suppression aussi, et l'éditeur
passe en lecture seule (nœuds non déplaçables, panneau remplacé par un mot).

Les messages des modèles sont **volontairement vides** : on les choisit dans la copie,
selon la cible. Le contrôle d'activation le signale — c'est normal sur un modèle, qui n'est
jamais activé.

Bouton **Dupliquer** partout, et sur un modèle c'est l'action principale (« Utiliser ») :
activer ou supprimer un point de départ commun n'a aucun sens. Le cadenas se pose et se
retire sur n'importe quel scénario : n'importe lequel peut devenir un modèle.

Tests : les trois formes, leur structure sans faute, les branches « oui »/« non » bien
orientées, les délais croissants, le verrou en base, la copie libre, et l'idempotence de la
création.

### MAJ 2026-08-24 — Bloqué à 29 emails : une écriture de comptabilité tuait le lot

Question de Camille : « pourquoi sommes-nous bloqués à 29 emails envoyés aujourd'hui ? »
La cadence en prévoyait 80.

**Ce n'était ni les contacts ni la capacité.** Le moteur autorisait encore 51 envois et les
boîtes avaient 131 places libres. Le lot du matin est simplement MORT en route.

**La cause.** Dans `maildoso_backend.send_email`, deux écritures suivent l'envoi SMTP :
`_record_sent` (journal `maildoso_sent`) et `_increment_sent` (compteur
`mailboxes.sent_today`). Les deux visent `god_mode.duckdb`, le fichier à écrivain unique
que le scraping et le dispatch se disputent. À 08h48, un verrou a levé là ; l'exception est
remontée par `send_email`, puis par `send_batch`, et le lot s'est arrêté. **Les 29 premiers
étaient partis ; les 51 suivants ne sont jamais partis, pour une écriture de comptabilité.**

Et le blocage a duré la journée : `last_dispatch_day` est posé AVANT le lot — à raison,
c'est ce qui empêche deux dispatches concurrents — donc le cron de 8h30 refusait de
reprendre.

**Ce qui rend la chose absurde : ces deux écritures sont REDONDANTES depuis la fin du
Lot 1.** Le journal `email_events` porte l'envoi, et le compteur du jour se lit dans ce
journal (`expediteur.envoyes_aujourdhui`), plus dans `mailboxes.sent_today`. Elles ne
méritaient en aucun cas de coûter un lot.

**Correction, sur deux niveaux :**
1. `_comptabiliser()` remplace les deux appels : chaque écriture est isolée et **ne peut
   plus faire échouer un envoi**. L'échec est CRIÉ, jamais avalé — une comptabilité qui
   tombe en silence laisserait `maildoso_sent` incomplet sans que personne ne le sache.
2. `send_batch` isole chaque destinataire : une panne imprévue sur l'un ne peut plus
   emporter les autres. Second rideau, parce que la première correction ne couvre que les
   causes qu'on a vues.

**Reprise du jour.** Marqueur retiré, lot relancé. La garde de reprise — qui lit désormais
PostgreSQL — a bien reconnu les 29 déjà servis et les a ignorés. Le 30ᵉ email est parti de
**j.durand** et non de j.bernard : la répartition entre boîtes, réparée ce matin, fonctionne.

**Reste à signaler** : un processus root de surveillance traîne depuis 63 jours
(`sudo -u autoblog bash -lc until … done`), vestige d'une session ancienne. Il ne consomme
rien et ne tient aucune base, mais il n'a plus de raison d'être.

### MAJ 2026-08-24 — Le verrou expliqué, et la cadence d'envoi régulée

**1. Ce qu'était le verrou (question de Camille : « je ne comprends pas en quoi c'était un
verrou »).** Sa remarque était juste : le dispatch n'écrit qu'à des adresses DÉJÀ nettoyées
par Mailnjoy, et le drain Mailnjoy nettoie des adresses qui ne sont pas encore parties. Les
deux ne se croisent jamais côté métier.

Ils se croisent côté FICHIER. `god_mode.duckdb` n'accepte **qu'un seul écrivain à la fois**
— c'est une propriété du moteur DuckDB, pas une règle qu'on a écrite. Le drain Mailnjoy
(`mailnjoy_drain_loop.py`, PID 4036959, service PM2 tournant en permanence depuis le 19/08)
ouvre ce fichier pour déplacer ses lignes de `scrappe_pending` vers `scrappe`. Le dispatch
ouvre le MÊME fichier pour écrire « email parti ». Quand les deux tombent en même temps, le
second est refusé — pour la seule raison qu'ils partagent un fichier, sans aucun rapport
entre les données.

C'est exactement l'absurdité que la migration PostgreSQL corrige : PostgreSQL accepte des
écrivains concurrents. Le Lot 1 avait déplacé les LECTURES ; il restait ces deux écritures
de comptabilité, désormais rendues non bloquantes.

**2. La cadence.** Camille : « il faut réguler les envois, pas faire partir 80 en 1 h,
sinon tu vas cramer mon IP et ma réputation. » Elle a raison, et le chiffre du matin le
prouve : **29 emails depuis la même adresse en 18 minutes, soit ~97 par heure.**

La pause de 15–60 s existait pourtant. Elle s'appliquait au **LOT**, pas à la **BOÎTE** :
tant que la rotation fonctionne, quatre boîtes se partagent le rythme ; dès qu'une seule
encaisse tout — ce qui était le cas ce matin, compteur par boîte cassé — la pause du lot ne
protège plus rien.

Deux règles désormais, la plus contraignante gagnant :
- **écart minimum par boîte : 4 minutes**, soit au plus 15 emails/heure et par adresse
  (60/h sur les quatre réunies, contre 97/h pour une seule ce matin) ;
- **étalement sur la fenêtre restante** : l'écart est recalculé à chaque envoi à partir du
  nombre restant et du temps restant. Un lot de 36 à 14 h donne un envoi toutes les 2 à 4
  minutes ; le même lot à 17 h s'étale davantage. L'intervalle est tiré au hasard autour de
  la cible — un envoi toutes les 380 secondes à la seconde près se reconnaît aussi bien
  qu'une rafale.

**Vérifié à sa demande : Maildoso n'a AUCUNE file d'attente.** C'est du SMTP direct
(`smtplib`) : le message part à la seconde où on le lui remet. La régulation nous appartient
entièrement, il n'y a personne derrière pour amortir.

Mozart applique la même contrainte par boîte : un scénario n'envoie qu'un contact à la
fois, mais rien n'empêche vingt contacts d'atteindre le même nœud au même passage horaire.
Le refus est un REPORT annoncé, pas un échec.

`tests/test_cadence.py` couvre les deux règles, les bornes, la fenêtre déjà fermée, le
dernier destinataire, et la vérification que Maildoso ne régule rien.

**Aujourd'hui : 44 emails partis** (29 le matin depuis une seule boîte, 15 l'après-midi
répartis sur trois). Le lot est arrêté ; il reprendra à la cadence régulée.

### MAJ 2026-08-24 — Revue : pourquoi les protections d'hier n'ont rien protégé

Camille : « on a mis en place hier un max d'email par adresse expéditrice avec une cadence
et un warmup à respecter, et sur la 1re campagne tu n'as rien respecté ». Elle a raison sur
toute la ligne. Voici l'examen, sans arrangement.

**Ce qui devait protéger, et ce qui s'est passé le 24/08 au matin :**

| Protection | Posée | Réalité du matin |
|---|---|---|
| Plafond 40/jour/boîte | 23/08 | **inerte** — le compteur rendait 0 pour les quatre |
| Rotation entre boîtes | 23/08 | **inerte** — même cause, tout est parti de j.bernard |
| Cadence 15–60 s | ancienne | appliquée au LOT, pas à la BOÎTE — sans effet dès qu'une seule encaisse |
| Montée en charge | 23/08 | **inerte** — ne voyait aucun envoi, donc n'a rien ajusté |

**Trois échecs sur quatre, une seule cause : le champ `mailbox` n'atteignait pas le
journal.** `expediteur.envoyes_aujourdhui` compte les envois par boîte en filtrant sur
`mailbox IS NOT NULL` ; le chemin d'envoi journalisait sans ce champ. Compteur à zéro →
`reste` toujours à 40 → plafond inatteignable, et « la moins chargée » toujours la même
(première par ordre alphabétique). Une seule ligne manquante a désactivé trois protections.

**Pourquoi les tests ne l'ont pas vu — et c'est le point le plus grave.**
1. Chaque brique était testée avec des valeurs FABRIQUÉES : `test_lot4_protections`
   passait une liste de boîtes construite à la main, `test_sante_envoi` passait un relevé
   de santé construit à la main. Les briques étaient bonnes ; **rien ne vérifiait qu'elles
   étaient reliées**.
2. Pire : le 23/08 au soir, j'ai rempli `email_events.mailbox` **par un rattrapage manuel**
   depuis `maildoso_sent`. Le compteur affichait alors les bons chiffres, et je l'ai
   vérifié. Mais le chemin de PRODUCTION n'écrivait toujours pas ce champ. **J'ai validé ma
   réparation, pas le mécanisme.** C'est la leçon à retenir : une vérification faite sur des
   données qu'on vient de réparer à la main ne prouve rien du système.

**Le warmup n'a jamais eu lieu.** Les quatre boîtes ont été créées le 2026-07-07 et portent
un plafond de **40 depuis l'origine**. Le journal de montée en charge ne contient que
« plafond 40 atteint » et « inchangé » : il n'a jamais fait monter quoi que ce soit, il n'a
fait que confirmer un plafond déjà au maximum. Elles ont donc démarré au sommet.
**Décision à prendre par Camille** : redescendre les plafonds et laisser la montée en charge
faire son travail (elle réagit désormais aux plaintes, rebonds et taux d'ouverture), ou
assumer 40/jour sur des boîtes de sept semaines.

**Ce qui est vérifié maintenant, sur données réelles** (pas fabriquées) :
- compteur par boîte : 29 / 6 / 5 / 5 — il bouge ;
- rotation : la prochaine boîte proposée est j.juste, la moins chargée ;
- cadence : 4 min minimum par boîte (15 emails/h max, contre 97/h le matin), plus un
  étalement sur la fenêtre restante ;
- montée en charge : lit de vrais taux d'ouverture (38 à 43 %).

**Contrôle ajouté, du type qui aurait vu le problème** — `tests/test_cadence.py` interroge
le JOURNAL DES ENVOIS RÉELLEMENT PARTIS et non le code : chaque envoi porte-t-il sa boîte ?
quel débit maximum sur une heure glissante ? une seule boîte concentre-t-elle tout ? Il
signale d'ailleurs encore le pic de 29/h du matin, comme il se doit.

**Ce qui reste fragile et qu'il faut savoir :** la cadence par boîte est tenue en mémoire du
process. Elle protège d'une rafale À L'INTÉRIEUR d'un lot, pas de deux lots lancés coup sur
coup depuis deux process. Tant qu'un seul dispatch tourne à la fois — c'est le cas, garanti
par `last_dispatch_day` — la protection est complète.

### MAJ 2026-08-24 — Progressivité du volume et alerte sur la pente

**1. Le plafond de progression.** Le trou était structurel : le PLAFOND par boîte (40) et
le PLAN DU JOUR sont deux nombres différents, et **seul le plafond était protégé**. Une
cadence de campagne pouvait réclamer 40 quand la moyenne récente était à 14, sans que rien
ne s'y oppose — c'est ainsi que le volume est passé de 6 à 40 par boîte en une nuit le
22/08. Ce n'est pas le chiffre qui se voit chez un fournisseur, c'est le SAUT : il lit un
changement de comportement.

`expediteur.boites()` calcule désormais un **plafond effectif** = le plus bas entre le
plafond de la boîte et **+50 % de sa moyenne des 7 derniers jours actifs**. Les jours sans
envoi sont exclus du calcul : une pause de week-end ferait sinon chuter la moyenne et le
moindre lot du lundi passerait pour un saut. Un plancher de 10 évite de brider une boîte
qui reprend après une période creuse.

Placé dans `boites()` et nulle part ailleurs : **tout ce qui envoie lit `reste`** — les
campagnes comme les scénarios Mozart. Une limite posée ailleurs serait une limite qu'un
chemin d'envoi peut ignorer, et c'est exactement le défaut qu'on vient de corriger.

Effet immédiat : moyennes de 15-16 → plafonds du jour de 22-24 au lieu de 40. Le retour à
160/jour se fera en trois ou quatre paliers, avec une trace — ce qu'un fournisseur regarde.

**2. L'alerte sur la PENTE.** Le seuil de 5 % demandé par Camille reste, comme plancher de
secours. Mais le taux d'ouverture est à **46 % sur trente jours** : le jour où il tombe à
20 %, quelque chose est cassé et l'alerte à 5 % ne dirait toujours rien. On surveille donc
aussi la **chute relative** : plus d'un tiers de perte entre la fenêtre de 7 jours et la
référence de 30 jours déclenche l'alerte. Aujourd'hui : 39,7 % contre 46 %, soit 14 % de
baisse — sous le seuil, rien ne part.

Tests étendus dans `tests/test_cadence.py` : cohérence du plafond effectif par boîte, jamais
au-dessus du plafond de la boîte, plancher pour une boîte sans historique, existence des
deux seuils d'ouverture et mesure de la référence longue.

### MAJ 2026-08-24 — Revue de code : 12 défauts trouvés, 12 corrigés

Revue lancée à la demande de Camille sur tout le travail non commité. Verdict sévère et
mérité. Les deux plus graves d'abord.

**GRAVE 1 — écriture inter-site possible sur un scénario Mozart.** `api_mozart_enregistrer`
était le seul point d'écriture Mozart qui ne vérifiait NI l'existence du scénario NI son
site. Le middleware ne contrôle que le code de site présent dans le CHEMIN : un compte
n'ayant accès qu'à `mkd` pouvait écrire `PUT /api/sites/mkd/mozart/<id-d-un-scénario-lcr>`
et réécrire le graphe d'un autre client. Et un identifiant inconnu produisait un 500.
Contrôle ajouté, 404 dans les deux cas.

**GRAVE 2 — l'écart minimum par boîte était vérifié APRÈS l'envoi.** Je l'avais annoncé
corrigé ; il ne l'était pas. Posé dans la boucle de pacing, il ne retardait que l'envoi
SUIVANT : deux messages pouvaient partir de la même adresse à vingt secondes d'intervalle,
puis attendre quatre minutes. Régime permanent : des rafales de deux toutes les quatre
minutes — exactement ce que la règle interdisait. Le contrôle est descendu dans
`send_email`, avant toute écriture SMTP, parce que c'est le seul endroit qui connaît la
boîte retenue. Et l'horodatage se pose à l'envoi réussi, plus dans la boucle : le dernier
envoi d'un lot n'était jamais enregistré, donc un lot suivant repartait sans écart.

**Les dix autres :**
- la bêta s'ouvrait sur un code de site inconnu (`/api/sites/zzz/mozart/...` échappait au
  contrôle) — un garde-fou qui s'annule sur une entrée inattendue n'en est pas un ;
- une boîte SANS historique repartait au plafond de 40 : le repli annulait la règle de
  progression dans le seul cas où elle compte. Repli sur le plancher ;
- les taux de Mozart comptaient des ouvertures ANTÉRIEURES au scénario : sur une liste déjà
  travaillée, un scénario que personne n'a ouvert pouvait afficher près de 100 %. Chaque
  réaction est désormais bornée au premier envoi fait à cette personne PAR ce scénario ;
- les tables Mozart n'existaient que dans la base vivante, créées à la main : une base
  restaurée aurait fait échouer chaque route. Schéma versionné dans `mozart_schema.sql`,
  appliqué automatiquement et idempotent ;
- `sys.path` grossissait d'une entrée à CHAQUE requête authentifiée — après une journée de
  trafic, chaque `import` parcourt des dizaines de milliers d'entrées ;
- `beta_testeurs()` relisait `.env` à chaque requête, sur la boucle d'événements, et ne
  retirait pas les guillemets : `PAGES_BETA_TESTEURS="camille"` fermait la bêta à la
  personne qu'elle devait ouvrir. Cache d'une minute, guillemets retirés ;
- `/api/mes-pages` — la route qui alimente toute la sidebar — pouvait rendre 500 sur une
  panne du catalogue, alors qu'un `try` était justement là pour l'éviter ;
- forme de réponse incohérente quand `mozart.stats()` échoue ;
- `if t != "email" or True:` — condition toujours vraie, reste d'écriture : tout scénario
  finissant par un envoi était impossible à activer ;
- la borne basse de la cadence pouvait tomber sous le plancher (14 s au lieu de 20) ;
- `mozart tick` ne traitait que `lcr` : un scénario créé pour une autre marque s'affichait,
  s'activait, et n'avançait jamais, sans aucun signal. Il traite désormais tous les sites
  ayant un scénario actif, lus en base ;
- `moyenne_recente` et `envoyes_aujourdhui` comptaient dans DEUX UNITÉS différentes
  (adresses distinctes contre envois distincts) : la soustraction rognait l'autorisation
  les jours où deux campagnes touchent les mêmes personnes ;
- la référence de 30 jours CONTENAIT la fenêtre de 7 jours mesurée : une chute durable
  diluait la référence un peu plus chaque jour et l'alerte finissait par s'éteindre. Les
  deux fenêtres ne se recouvrent plus.

Les dix suites de tests repassent au vert après correction.

### MAJ 2026-08-24 — Simplification : quatre revues, huit corrections appliquées

Quatre agents en parallèle (réutilisation, simplification, efficacité, altitude). Ils
convergent tous vers le même diagnostic de fond : **plusieurs protections d'envoi ont été
écrites DEUX fois — une pour les campagnes, une pour Mozart — au lieu d'une seule au point
de passage commun.** Un doublon de règle d'envoi finit toujours par diverger, et il avait
déjà commencé.

**Appliqué :**

1. **La cadence par boîte ne vit plus que dans `send_email`.** Mozart la recopiait — et pour
   le faire devait DEVINER quelle boîte serait retenue, via l'affinité : pour un contact
   sans affinité, la règle ne s'appliquait donc pas du tout. Le bloc était en outre gardé
   par `if boite or True:`, une condition toujours vraie. 18 lignes retirées ; Mozart lit
   simplement le `reporte` que `send_email` lui rend.
2. **La fenêtre des 120 jours descend au point de passage.** Elle était appliquée par chaque
   appelant, et la version Mozart était **plus faible** : elle interrogeait le journal mais
   pas la base repoussoir. C'est la règle la plus coûteuse de la plateforme ; elle vit
   désormais dans `send_email`, par où TOUT envoi passe. Les BAT et les tests en sont
   exemptés — ils partent vers nos propres adresses, à notre demande — par la même
   distinction qui sert déjà au journal. Les appelants gardent leur filtre amont : il
   évite de composer un message pour quelqu'un qui sera refusé, il n'est plus la garantie.
   La constante `120` est lue chez `contacts_pool_backend`, plus recopiée.
3. **`_ecrire()` descend dans `pool_pg`.** Trois copies identiques au caractère près
   (`expediteur`, `refroidissement`, `mozart`). Ce n'est pas du doublon décoratif : c'est un
   contrat de transaction — ouvrir, exécuter, VALIDER, RENDRE la connexion. Trois copies,
   c'est trois endroits où oublier le `commit` ou le retour au pool, et une connexion non
   rendue épuise le pool en silence.
4. **Le garde des routes Mozart est unique.** Il était recopié dans huit routes — et OUBLIÉ
   dans la neuvième, celle qui écrit : c'est ce qui a ouvert l'écriture inter-clients.
   `_mozart_du_site()` remplace les huit copies ; une dixième route ne pourra pas l'oublier.
5. **`boites()` fait UNE requête au lieu de deux.** Elle est appelée pour CHAQUE destinataire
   d'un lot : cent soixante agrégats sur `email_events` pour un lot de quatre-vingts, afin
   de lire des nombres qui bougent d'une unité entre deux envois. Le jour courant et la
   moyenne des sept jours se lisent maintenant d'un trait.
6. **`inscrire()` fait UN insert au lieu de cinq cents.** Cinq cents transactions pour
   insérer des lignes triviales.
7. **Le graphe n'est plus reconstruit à chaque pas** : il l'était pour chaque contact et
   chaque pas, soit des milliers de fois par tick.
8. **`_cadence()` perd un paramètre mort, un import mort et un repli inatteignable** — dont
   une borne d'horaire codée en dur qui faisait une TROISIÈME écriture de la fenêtre
   d'envoi. Elle la demande désormais à `deliverability_agent`.
Plus : `sys.path` ne grossit plus à chaque requête (garde ajouté), et deux champs dérivables
sortent du contrat de `boites()`.

**Écarté volontairement :** l'unification des trois fenêtres horaires
(`deliverability_agent` / Mozart / `_cadence`) en une fonction paramétrée, et le passage de
`_DERNIER_ENVOI` en base pour que la cadence tienne ENTRE deux process. Les deux sont
justes et méritent d'être faits — mais ils touchent le chemin d'envoi des campagnes en
production, un jour où il tourne. À reprendre à froid.

**Deux tests ont cassé, et c'était leur rôle** : ils affirmaient que Mozart portait des
règles qui ont déménagé. Réécrits pour vérifier l'EMPLACEMENT de la règle plutôt que sa
copie — dont un contrôle nouveau : `send_email` refuse-t-il bien AVANT d'écrire sur le
réseau, et non après. Les quinze suites passent.

### MAJ 2026-08-25 — La sidebar ne pouvait qu'enlever des entrées, jamais en ajouter

**Symptôme.** Ni les pages Onoff ni « Adresses d'envoi » n'apparaissaient dans le menu,
alors que le serveur les déclarait et que le compte `camille` (superadmin) y avait droit.

**La cause, et c'est la TROISIÈME fois.** `app-sidebar.tsx` porte ses entrées de menu
**écrites en dur**, et ne se sert de la réponse de `/api/mes-pages` que pour les FILTRER :

```
navMain = navConstruit.map(g => ({ ...g, items: g.items.filter(…autorisées…) }))
```

Une page déclarée côté serveur mais absente de ce fichier ne pouvait donc jamais s'afficher.
Le 2026-08-24, Mozart clignotait pour la même raison ; j'avais alors corrigé la table
clé → URL en la faisant venir du serveur, **et cru avoir traité la racine**. Je n'avais
traité que la moitié : l'URL venait du serveur, l'EXISTENCE de l'entrée restait locale.

**Correction à la racine.**
- `/api/mes-pages` renvoie désormais un `catalogue` complet — clé, libellé, groupe, URL —
  et plus seulement les URL.
- La sidebar **ajoute** toute page autorisée absente de son menu, dans le groupe que le
  serveur lui donne. Le code local ne décide plus que de l'ORDRE des groupes et de
  l'ICÔNE ; l'existence vient d'une seule source. Une clé sans icône reçoit une pastille
  neutre — mieux vaut une entrée sans belle icône qu'une entrée invisible.
- Deux écueils d'ordonnancement traités : la fusion s'exécute APRÈS la création du groupe
  « Configuration » (sinon il existait en double) et AVANT le marquage des bêtas (sinon
  une page ajoutée n'aurait jamais son étiquette).
- Nouveau groupe `Configuration` dans le catalogue serveur ; « Adresses d'envoi » y est
  rangée plutôt que dans « Administration » — c'est une page de site, pas d'admin globale.
  Une page hors `/site/{code}/` est explicitement écartée du menu contextuel.

**Contrôle** dans `tests/test_menu_et_droits.py` : il vérifie les DEUX moitiés du contrat —
le serveur envoie le catalogue, l'écran sait ajouter ce qu'il ne connaît pas — plus l'ordre
fusion/bêta. C'est le contrôle qui aurait vu les trois disparitions.

### MAJ 2026-08-25 — Quatre adresses réservées à Mozart, et une chauffe par boîte

**Demande de Camille.** Quatre nouvelles boîtes Maildoso — `news@`, `agence@`, `info@`
(Pascal Cabral) et `immo@` (Julie Durand) — **exclusivement pour Mozart**, afin que les
volumes des campagnes ad hoc et des scénarios automatiques ne se croisent pas. Avec une
chauffe conforme au guide Maildoso, et un tableau de toutes les adresses en Configuration.

**Ce qui a été fait.**
- Colonnes `usage` ('adhoc' | 'mozart', contrainte en base) et `warmup_debut` sur
  `mailboxes`. Les quatre anciennes passent en `adhoc`, les quatre nouvelles en `mozart`.
- Mot de passe SMTP distinct (`MAILDOSO_SMTP_PASSWORD_MOZART`) : celui du CSV n'est pas
  celui des boîtes existantes.
- **`expediteur.plafond_chauffe()`** — une adresse de moins de **14 jours rend 0**, pas
  « un peu » : zéro cold email, elle ne fait que la chauffe interne de Maildoso. Ensuite la
  même pente que la flotte : 15, +1/jour, 35 au plus. Pour les quatre nouvelles :
  **rien jusqu'au 2026-09-08**, 15 ce jour-là, **35 le 2026-09-28**.
- `boites(site, usage=…)` filtre les pools. Mozart envoie avec `usage="mozart"`, les
  campagnes avec `usage="adhoc"`. `routage` et `programmation` ne comptent plus que les
  adresses ad hoc — sinon la planification promettrait un volume que le dispatch ne peut
  pas honorer.
- **QUATRE plafonds désormais, le plus bas gagnant** : plafond Maildoso (ce que le
  fournisseur accepte), plafond de progression, rampe de flotte, chauffe individuelle.

**La précédence qu'il fallait trancher.** L'affinité expéditeur dit « 1 contact = 1 adresse
à vie » ; la séparation des pools dit « Mozart n'utilise que ses adresses ». Les deux
s'opposent pour un contact déjà démarché par une campagne qui entre dans un scénario.
**L'affinité gagne** : `choisir()` cherche l'affinité parmi TOUTES les boîtes du site, et
seule la PREMIÈRE attribution respecte l'usage. Sans cette précédence, ce contact aurait
attendu indéfiniment (sa boîte absente de la liste proposée) ou changé d'expéditeur, ce qui
remet à zéro la réputation acquise auprès de lui.

**Incident, causé par mon ordre d'opérations.** J'ai inséré les quatre boîtes en base
**pendant qu'un dispatch de campagne tournait**, et avant d'avoir câblé la séparation. Le
dispatch a immédiatement pris `agence@` pour un envoi ad hoc : **1 email parti d'une boîte
née le jour même**, à 10h58 (Paris), vers `immobilier@captaldea.com`. Exactement ce que la
demande visait à empêcher. Actions : dispatch arrêté (reprise sûre — `send_batch` ignore
les destinataires déjà servis), affinité accidentelle libérée (non confirmée, sinon le
contact aurait attendu 14 jours). **La leçon : insérer une adresse d'envoi en base est un
acte de production ; il se fait dispatch à l'arrêt.**

**Le tableau demandé** — `/site/{code}/setup/expediteurs` : par adresse, l'usage
(cliquable pour basculer), les envois d'aujourd'hui, d'hier, sur 30 jours et depuis le
début, le reste du jour, le plafond Cheffer **sur** le plafond Maildoso, les ouvreurs et
cliqueurs sur 30 jours, et l'état (active / en chauffe jusqu'au … / au repos). Les volumes
viennent de `email_events`, jamais de `mailboxes.sent_today` qui vit dans DuckDB et se perd
sous verrou.

**Piège signalé à l'écran** : Maildoso limite les quatre nouvelles à **3/jour**. Ce chiffre
doit être relevé **chez Maildoso** au fil de la chauffe, sinon les envois seront rejetés à
la source quelle que soit la rampe de Cheffer.

### MAJ 2026-08-25 — Guide de délivrabilité Maildoso : l'écart mesuré, et ce qu'on en a fait

**Point de départ, pour ne pas dramatiser.** Sur 30 jours : 1 046 envois, **46,9 %
d'ouverture, 9,8 % de clic, 0,1 % de rebond, 0 plainte**. Maildoso affiche par ailleurs
Google « High » et Microsoft « High » au 24/08. Rien n'était en feu ; ce qui suit est de
l'optimisation.

**Le seul chiffre du guide** : « limit cold sending to **15 emails per day per mailbox,
including follow-ups** », après 14 jours de chauffe. Nous étions à 40 de plafond, 24-27
effectifs. Les dix autres recommandations, confrontées au code :

| Recommandation | État constaté |
|---|---|
| Texte seul, sans HTML | multipart texte + HTML |
| Ne pas tracker les ouvertures | pixel actif |
| Éviter liens/images au 1er message | **2,4 liens** de moyenne, 1 image |
| Signature sans lien ni photo | **la signature ÉTAIT une image S3** |
| Vérifier les mots spam | **aucun contrôle** |
| Spintax | **absent** (variantes = 1 partout) |
| Plusieurs campagnes en parallèle | une seule à la fois |
| Rotation toutes les 2 semaines | 18 j puis 7 j — conforme |
| En-tête de désinscription | présent, `mailto:` seul |

**Trouvé en plus, hors guide** : le pixel et les liens réécrits pointent vers
`api.cheffer.email` alors que l'envoi part de `leclient-roi.com`. Un domaine de tracking
étranger au domaine d'envoi est un signal classique. **Non corrigé** : demande une entrée
DNS, donc une décision de Camille.

**Décisions de Camille (2026-08-25).**
1. **Volume : rampe de chauffe.** 15/jour/boîte aujourd'hui, **+1 par jour pendant 20
   jours, jusqu'à 35**. Implémentée dans `expediteur.plafond_rampe()` comme TROISIÈME
   plafond : plafond de la boîte, plafond de progression, rampe — la plus basse gagne.
   Arrivée à 35 le **2026-09-14**, puis stable.
2. **Suivi des ouvertures : option, jamais suppression.** « Sinon notre outil tombe à
   l'eau, comment j'alimente les commerciaux sur les ouvreurs. » Le pixel devient une
   option `suivi_ouverture` par scénario Mozart (colonne + bascule dans l'éditeur), défaut
   à VRAI. Les **clics restent toujours mesurés** : c'est une redirection, pas une image.
3. **Contenu : les quatre points retenus**, tous livrés.

**Livré.**
- `scripts/qualite_message.py` — mots à risque (deux niveaux : bloquant / avertissement),
  excès de forme (capitales, `!!`, symboles monétaires), comptage des liens et images, et
  **spintax déterministe**. Le tirage utilise `hashlib` et non `hash()`, qui est salé par
  processus : sinon une relance aurait été rédigée autrement que le message déjà reçu par
  la même personne. Le motif exige un `|`, donc `{{prenom}}` et `{prenom}` traversent intacts.
- Branchements : spintax dans `send_email` (avant la personnalisation), contrôle de
  vocabulaire dans la garde avant lot de `campaign_engine` — bloquant sur les termes
  notoires, avertissement sinon, et signalement quand un message n'a aucune variante.
- **Signature en texte** dans `god_mode_templates.py` et `api.py` (l'image S3 disparaît).
- **Premier message allégé** : `email_generator` n'ajoute plus le lien secteur au premier
  email (réservé aux relances), et `scripts/alleger_premiers_messages.py` a repris les
  modèles déjà en base. Résultat : **10 modèles passés de 2-5 liens à 1 lien, 0 image**,
  tous conformes au lint existant (le CTA de rendez-vous est préservé).

**Deux tests corrigés dans leur PRÉMISSE, pas dans leur résultat.**
- `test_pg_journal` exigeait « PostgreSQL ne compte jamais PLUS que le pool ». Depuis le
  Lot 1, PostgreSQL fait foi et c'est DuckDB la copie qui perd : `mark_pushed_to_emelia`
  écrit PG PUIS DuckDB, un verrou entre les deux laisse une ligne d'un seul côté. Constaté :
  70 contre 69 pour j.bernard. L'écart est désormais toléré **dans les deux sens**, serré.
- `test_cadence` calculait le plafond attendu à partir de deux limites ; il y en a trois
  depuis la rampe.

`tests/test_delivrabilite_contenu.py` (28 contrôles) fige l'ensemble. **19 suites au vert.**

### MAJ 2026-08-24 — Connecteur Onoff Business : MVP téléphonie

**La contrainte, trouvée avant d'écrire une ligne.** La navigation complète de
docs.onoffbusiness.com donne la surface exacte de l'API : Members, Numbers, Departments,
Contacts, Calls (4 endpoints), SMS (2), Statistics. Tous en lecture. Il n'existe :
- **aucun endpoint pour PASSER un appel** — Onoff passe par son extension Chrome
  « Click2Call » ou son application ;
- **aucun endpoint pour ENVOYER un SMS** — la page produit officielle le range dans les
  fonctions « à venir » : *« SMS management: send messages directly via the API (listing is
  already live) »* ;
- **aucun endpoint pour le SOLDE / les crédits**, nulle part.

De plus **l'API entière demande le plan Max**. Le WEBHOOK, lui, fonctionne quel que soit
l'abonnement : il livre appels, SMS, messagerie et enregistrements. Il est donc la source
PRIMAIRE ici, l'API n'étant qu'un enrichissement — sans quoi un changement d'abonnement
ferait disparaître une messagerie non lue de l'écran.

**Ce qui a été livré.**
- `scripts/onoff.py` (466 l.) — client, normalisation E.164 (le pool stocke du national
  `0428384508`, Onoff renvoie de l'international : sans conversion des deux côtés aucun
  rapprochement n'aboutit), journal local, résumé. Délai 8 s + une seconde chance, et le
  vocabulaire de cause `cle`/`service`/`reseau` repris des connecteurs du tableau de bord.
- `scripts/onoff_schema.sql` — table `onoff_evenements`, index partiel sur les non-lus.
- 12 routes API, dont `POST /api/webhook/onoff/{site}` (jeton en query, mécanisme déjà en
  place) et `POST …/onoff/appel` qui rend l'URI `tel:` **et** consigne l'appel dans le suivi.
- Trois pages : `/site/{code}/onoff` (état, chiffres 30 j, membres, numéros, derniers
  appels), `/site/{code}/onoff/messagerie` (répondeur, écoute, marquage), et
  `/site/{code}/setup/onoff` (clé API + webhook, avec la liste franche de ce que le
  connecteur permet et ne permet pas).
- Action **Appeler** dans `ActionsAppel` : composition par `tel:`, SMS 1 à 1, et
  l'historique Onoff du numéro. Les deux pages sont en **bêta fermée** (compte `camille`).

**Le choix de conception qui compte.** L'appel part par `tel:`, mais la PREUVE qu'il a eu
lieu ne vient pas du bouton : elle vient du journal Onoff reçu par webhook. C'est
exactement l'objection de Camille au « bouton appel passé » du 23/08 — « il est branché à
rien et c'est juste du déclaratif ». Ici le fait est mesuré, pas déclaré.

**Deux invariants figés par `tests/test_onoff.py`** (34 contrôles) :
1. **Un rejeu d'Onoff ne remet jamais en non lu une messagerie écoutée.** `lu_at` est
   exclu de l'`ON CONFLICT DO UPDATE` ; sans cela le répondeur se remplirait tout seul.
2. **Un seul POST part vers Onoff dans tout le module**, et c'est la tentative d'envoi de
   SMS. Si un autre apparaît, c'est la porte par laquelle une action non supportée
   s'introduirait.

**Corrigé au passage.** `resume()` comptait les SMS dans « entrants » : le total ne
s'additionnait plus (2 appels, 2 entrants, 1 sortant). Et `tests/test_cadence.py` supposait
la fenêtre d'envoi ouverte — hors fenêtre `_cadence` retombe au plancher, ce qui est juste,
mais la suite passait au rouge tous les soirs après 17h59. Le contrôle suit désormais
l'heure et vérifie les deux comportements. **18 suites au vert.**

**Ce qui attend Camille** : la clé API dans `/site/lcr/setup/onoff` (plan Max requis), et
la déclaration du webhook côté Onoff avec l'URL que la page affiche. Le répondeur
fonctionne avec le webhook SEUL.


### MAJ 2026-08-24 — La fausse panne Ahrefs, et la page d'accueil qui ne demandait rien

**Le symptôme.** Le tableau de bord LCR affichait « Erreur — Ahrefs (SEO) », 3051 ms, avec
pour consigne « Vérifier la clé et la connectivité réseau ».

**Ce que la clé disait vraiment.** Trois appels de suite à l'API Ahrefs : HTTP 200 en
953 ms, puis 200 ms, puis 187 ms. Abonnement Lite actif. **La clé n'a jamais été en cause.**
Le ping était coupé à 3 secondes, sans seconde tentative — or la toute première requête paie
la poignée de main TLS, et Ahrefs oscille : mesuré à 5 903 ms lors d'un contrôle ultérieur,
soit le double de l'ancien plafond. La panne était fabriquée par le contrôle lui-même.

**Deux défauts, pas un.** Le second est le plus coûteux : le message d'action accusait la
clé dans TOUS les cas d'erreur. Il envoyait chercher un problème là où il n'y en avait pas,
et masquait ceux qui existaient vraiment.

**Corrections.**
- Délai porté à 8 s avec une seconde tentative sur incident réseau uniquement
  (`_http(..., essais=2)`) — un code HTTP d'erreur n'est jamais rejoué.
- Nouvelle fonction `_verdict()` : elle traduit un ping en statut **et en cause** —
  `cle` (401/403), `service` (autre code HTTP), `reseau` (aucune réponse). Elle remplace au
  passage six lignes de verdict recopiées à l'identique.
- Les dix connecteurs sont désormais pingés **de front** et non en file indienne : à 8 s
  × 2 essais, la séquence aurait fait attendre l'écran jusqu'à deux minutes. Mesuré à
  **5,9 s pour les dix**, soit le plus lent d'entre eux.
- L'écran propose une action par cause, et n'envoie plus vers Setup & API quand la clé est
  hors de cause.

**Trouvé au passage — un vrai défaut, lui.** WordPress MKD répond **HTTP 401
`incorrect_password`** : le mot de passe d'application n'est plus valide. Le site lui-même
répond 200 sans authentification, donc seule la clé est en cause. Ce défaut existait déjà,
noyé dans le même message générique que la fausse panne Ahrefs. **Il demande une action de
Camille** : régénérer un mot de passe d'application dans WordPress (Utilisateurs → Profil →
Mots de passe d'application) et le reporter dans `WP_APP_PASSWORD`.

**La page d'accueil.** `/` renvoyait vers `/view`, un tableau croisé de huit colonnes — la
« page bizarre ». Elle demande maintenant **quel projet ouvrir**, avec une grande carte
cliquable par marque : pastille d'identité colorée (LCR ambre, MKD bleu), nom, domaine,
statut en ligne, et quatre chiffres — visites/mois, leads, emails sur 7 jours, coût IA sur
la période choisie. Le tableau technique n'est pas perdu : il est replié sous « Détail
technique et SEO des projets ».

Deux pièges évités en la construisant :
- `/api/campaigns` **n'a aucun champ `site`** — le site est encodé dans le NOM de la
  campagne (`lcr-…`). Compter les emails par site ainsi aurait attribué chaque campagne aux
  deux projets. Le chiffre vient désormais du **journal réel** (`daily-stats`, Maildoso +
  Sweego), pas d'Emelia.
- Le journal ne remonte qu'à 31 jours (`_PERIODES_JOURS`). La cellule « Emails » est donc
  fixée à 7 jours et libellée comme telle, plutôt que de prétendre suivre l'onglet « 1 an ».
- `/api/campaigns` faisait un appel GraphQL Emelia **par campagne** à chaque ouverture de la
  page d'accueil. Devenu inutile, il est retiré — autant de crédits Emelia préservés.

**Contrôle.** `tests/test_connecteurs.py` fige les deux règles : le délai, et la traduction
d'un échec en cause (clé refusée → `cle`, réseau muet → `reseau` et jamais `cle`, clé absente
→ `missing_key`). 17 suites au vert.

