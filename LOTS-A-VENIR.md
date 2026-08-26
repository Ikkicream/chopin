# LOTS À VENIR — Genesis / Cheffer

> Rédigé le **2026-08-26**. Reprend les 7 chantiers déposés en fin de session du 26/08,
> les 2 chantiers écartés à froid le 24/08, et 3 anomalies constatées ce matin.
> Historique et lots clos : voir `RESTE-A-FAIRE.md` et `STATE.md`.
>
> **Lettres et non numéros** : les numéros de lot 1→5 ont déjà servi deux fois avec des
> sens différents (« Lot 2 » désigne à la fois le classement des secteurs, clos le 21/08,
> et le routage Mozart, jamais attaqué). On repart sur A→G pour ne plus confondre.

| Lot | Titre | Effort | Bloqué par |
|---|---|---|---|
| **A** | Hygiène : 3 anomalies constatées ce matin | ~45 min | — |
| **B** | Attribution par message | ~2 h | — |
| **C** | L'écran cold email unifié | ~4 h | — |
| **D** | La marque et le sens des objets | ~2 h | décision Camille + 10 j de mesure (lot B) |
| **E** | Mozart : routage par secteur | ~1 j | — |
| **F** | Fenêtres horaires et cadence hors RAM | ~3 h | décision Camille (aligner ou non) |
| **G** | Documentation par rôle | ~1 j | C (les écrans doivent être stables) |

**Ordre recommandé : A → B → C → D → E → F → G.**
B avant D parce qu'on ne peut pas arbitrer des objets d'email qu'on ne sait pas encore
mesurer un par un. F après E parce que Mozart est le deuxième appelant des fenêtres :
autant unifier quand les deux chemins sont figés.

---

## Lot A — Hygiène : 3 anomalies constatées ce matin

**Objectif :** remettre à zéro ce qui saigne aujourd'hui. Aucune de ces trois ne bloque la
production, les trois polluent le diagnostic.

### A.1 — `re` n'est pas importé dans `scripts/api.py`

`_nom_avatar()` (`scripts/api.py:4896`) appelle `re.sub`, or `re` n'est **jamais importé au
niveau module** dans ce fichier — il ne l'est que localement, dans six fonctions
(lignes 1532, 3289, 4695, 6610, 9087). Les **quatre routes avatars** lèvent donc
`NameError` : statut (`:4903`), upload (`:4918`), suppression (`:4951`) et le contrôle de
droits (`:4923`). 32 erreurs 500 dans les journaux, et l'API redémarre en boucle
(61 redémarrages PM2).

- Ajouter `import re` en tête de `scripts/api.py`, à côté des autres imports standard.
- Laisser les `import re` locaux : ils sont redondants mais inoffensifs, et les retirer
  dans le même geste mélangerait un correctif et un nettoyage.
- `sudo -u autoblog pm2 restart genesis-dashboard`.

**Fait quand :** `curl -s localhost:8080/api/avatars/camille` renvoie du JSON et non un 500,
et le journal d'erreurs ne grossit plus.

### A.2 — Trois éléments appartenant à `root` dans `genesis-ui`

`.gitignore`, `next.config.ts.bak-distdir` et le dossier `.next-verify/` appartiennent à
`root` alors que tout tourne sous `autoblog`. C'est exactement la famille de panne qui a
déjà arrêté un cron **deux fois** (`alertes.json` le 20/08, `pg_reconcile.log` le 21/08) :
le cron tourne en `autoblog`, ne peut pas écrire, et meurt en silence.

- `chown -R autoblog:autoblog /home/autoblog/genesis-ui/.gitignore /home/autoblog/genesis-ui/next.config.ts.bak-distdir /home/autoblog/genesis-ui/.next-verify`
- Vérifier plus large : `find /home/autoblog/genesis /home/autoblog/genesis-ui -user root -not -path '*/node_modules/*' -not -path '*/.git/*'`
- Réflexe à garder : après **tout** lancement manuel en `root`, un `chown` avant de partir.

### A.3 — Le pré-en-tête pollue chaque contrôle anti-spam

Le lint remonte `low-contrast: Low contrast ratio 1.0:1` sur le pré-en-tête caché — blanc
sur blanc, opacité 0. **C'est voulu** : un pré-en-tête doit être invisible.
La catégorie `accessibility` n'est déjà **pas** bloquante
(`scripts/email_lint_backend.py:35` — `BLOCKING_CATEGORIES = ("templatevars", "links",
"html", "spam")`), donc rien n'est arrêté par ça ; mais le message apparaît dans chaque
rapport, y compris dans l'erreur de campagne du 26/08 où il a fait croire pendant un
moment que c'était lui le coupable (c'étaient les `{{si prenom}}`).

- Dans `email_lint_backend`, écarter les findings de contraste portant sur un élément
  `opacity:0`, `display:none`, `font-size:0` ou `max-height:0` — le pré-en-tête coche
  toutes ces cases.
- Ne pas désactiver la règle en entier : sur le corps visible, elle sert.

### A.4 — Bonus : les compteurs `sent_today` sont périmés

`mailboxes.sent_today` vaut 83, 71, 72, 72 pour un `daily_cap` de 40, alors que **10 emails
seulement** sont partis aujourd'hui. Le `last_reset` ne passe plus, probablement parce que
l'incrément échoue sur le verrou DuckDB (visible en clair dans
`memory/shared/campaign-dispatch.log`). Sans conséquence — le quota réel se compte dans
`email_events` — mais tout écran qui lirait `sent_today` mentirait. À trancher : réparer le
reset, ou supprimer la colonne et lire le journal partout.

---

## Lot B — Attribution par message

**Objectif :** savoir QUEL modèle a produit chaque envoi, chaque ouverture, chaque clic.

**Pourquoi maintenant :** aujourd'hui la galerie affiche des chiffres **par secteur**,
partagés par les trois emails d'un même secteur. On ne peut donc pas dire lequel des trois
marche. Or les lots D (objets, marque) et E (routage Mozart) sont tous les deux des
arbitrages entre messages. Sans B, on arbitre à l'aveugle.

**La bonne nouvelle :** le backlog notait ce chantier « bloqué en attente d'une évolution
du schéma `email_events` ». **Il ne l'est pas.** La table porte déjà une colonne
`meta jsonb NOT NULL DEFAULT '{}'` — il suffit d'y écrire le modèle. Aucune migration,
aucun `ALTER TABLE`, aucune reprise d'historique nécessaire.

**Étapes**

1. À l'envoi, passer le modèle dans `meta` : `pg_sync.record_send(...)` et
   `record_event(...)` (`scripts/pg_sync.py:337`) reçoivent déjà un paramètre `meta`.
   Y mettre `{"template": f"{secteur}:{kind}", "template_version": <hash ou updated_at>}`.
   Les appelants à couvrir : `campaign_engine` (chemin campagnes) et `mozart` (chemin
   scénarios) — les deux passent par `maildoso_backend.send_email`, c'est le point unique
   à instrumenter.
2. Reporter l'attribution sur les événements d'engagement : une ouverture ou un clic
   arrive **après**, sans contexte. Retrouver le `meta.template` du dernier `sent` du même
   couple (email, campagne) et le recopier — un `LATERAL` sur `idx_events_sent` suffit.
3. Indexer : `CREATE INDEX idx_events_template ON email_events ((meta->>'template'), event_type, occurred_at DESC);`
4. `email_templates_backend.tableau()` (servi par `/api/sites/{site}/templates/tableau`)
   lit ce champ au lieu d'agréger par secteur.
5. Marquer explicitement l'historique comme non attribuable — surtout **ne pas** répartir
   les anciens chiffres au prorata entre les trois modèles d'un secteur. Dans la galerie,
   « — » et une infobulle « mesuré depuis le 26/08 ».

**Fait quand :** deux modèles du même secteur affichent des taux d'ouverture différents.

**Risque :** faible. On ajoute un champ, on ne touche ni au chemin d'envoi ni aux
protections. Le seul piège est l'étape 2 : si la recopie rate, les ouvertures deviennent
non attribuées — donc dégrader vers « non attribué » et jamais vers « attribué au premier
modèle trouvé ».

---

## Lot C — L'écran cold email unifié

**Objectif :** un seul écran pour les cold emails ET les newsletters, filtrable par
secteur, lisible d'un coup d'œil. (Chantiers 2 et 3 du dépôt du 26/08, fusionnés : les
deux réécrivent la même table.)

**Fichiers :** `genesis-ui/src/app/site/[code]/cold-email/galerie.tsx` (la table),
`.../cold-email/page.tsx` (`sectorMeta` y est déjà, ligne 170), `.../newsletters/`
(la page à absorber), `scripts/email_templates_backend.py` et
`scripts/html_templates_backend.py` côté serveur.

**Étapes**

1. **Filtre par secteur.** Aujourd'hui il n'y a qu'un champ de recherche libre. Ajouter des
   pastilles cliquables, une par secteur, avec `sectorMeta.emoji` — le composant existe
   déjà dans l'assistant (`page.tsx:317`), il suffit de le remonter dans la galerie.
2. **Icône par secteur dans chaque ligne**, même source.
3. **Colonne « Objet ».** Elle affiche aujourd'hui le début du CORPS sous l'objet. Retirer
   la seconde ligne : l'aperçu latéral est là pour ça.
4. **Absorber les newsletters** dans `/site/{code}/cold-email` avec une colonne **Type**
   (`Cold email` / `Emailing`).

**Attention sur le point 4 — les deux sources ne se ressemblent pas :**

| | Cold email | Newsletter |
|---|---|---|
| Stockage | `email_templates` (god_mode.duckdb) | `structures/*.html` + table `html_templates` |
| Contenu | **24 lignes**, site `lcr` | **8 structures sur disque**, **0 version enregistrée** |
| Clés | `(site, secteur, kind)` | `struct:<fichier>` / `ver:<uuid>` |
| API | `/api/sites/{site}/templates/*` | `/api/sites/{site}/html/templates/*` |

La table `html_templates` étant **vide**, la galerie fusionnée doit lister les 8 structures
du disque comme lignes de premier rang, sinon l'onglet « Emailing » s'affichera désespérément
vide alors que le matériel existe. Ne pas fusionner les deux backends en un seul : garder
deux lecteurs et fusionner **dans la vue**, sinon on casse l'éditeur de newsletters.

**Fait quand :** un clic sur 🏠 immobilier montre les 3 cold emails + la newsletter du
secteur, dans la même table, avec la bonne icône et sans corps de message dans la colonne
Objet.

---

## Lot D — La marque et le sens des objets

**Objectif :** qu'un inconnu sache de qui vient l'email **avant** de l'ouvrir.

**Le constat de Camille :** « Vos mandats après août ? » ne dit rien, et **la marque n'est
identifiée nulle part** — ni dans l'objet, ni dans le nom d'expéditeur. Les 4 boîtes
s'appellent `Juliette Bernard`, `Juliette Durand`, `Juliette Juste`, `Juliette Nguyen`.
LeClientROI n'apparaît qu'en signature, donc après ouverture.

**Deux pistes, une seule à retenir :**

1. **Nom d'expéditeur → « Juliette Durand · LeClientROI ».** Visible dans TOUTE boîte de
   réception, avant ouverture, sans coûter un caractère d'objet.
   Un `UPDATE mailboxes SET sender_name = ...` suffit : `maildoso_backend.py:570` construit
   déjà `msg["From"] = f"{sender_name} <{email}>"`.
   ⚠️ **Vérifier d'abord** que `_split_name()` (`:383`) ne casse pas :
   `expediteur_prenom` / `expediteur_nom` sont injectés dans les signatures des gabarits.
   Avec « Juliette Durand · LeClientROI », le nom deviendrait « Durand · LeClientROI ».
   Corriger `_split_name` **avant** de changer les noms, pas après.
2. **La marque dans l'objet** — les données la déconseillent : nom d'entreprise en objet
   = 38 % d'ouverture, la pire catégorie utile, contre 46 % sur nos objets actuels.

**Recommandation : piste 1 seule.** Elle gagne la visibilité sans toucher aux objets, qui
mesurent déjà 46 % sur 30 jours.

**Puis, séparément :** relire les 24 objets à voix haute. Plusieurs restent courts et
anglicisés dans leur construction. Ne pas les changer en même temps que le nom
d'expéditeur — sinon on ne saura pas ce qui a produit l'effet. Un changement, dix jours,
on lit le lot B, on passe au suivant.

**Bloqué par :** décision de Camille sur la piste, et par le lot B pour la relecture des
objets.

---

## Lot E — Mozart : routage par secteur

**Objectif :** pour chaque contact nouvellement collecté, choisir automatiquement le bon
cold email selon son secteur, avec relance conditionnée à l'ouverture.

**Aujourd'hui :** un scénario porte UN message figé. Deux scénarios existent (immobilier,
agences), ce qui ne passe pas à l'échelle des 7 secteurs.

**Deux conceptions possibles :**

- **Un scénario par secteur.** Simple, lisible dans l'éditeur React Flow, mais 7 graphes à
  maintenir en parallèle : une correction de tuyauterie se fait sept fois.
- **Un nœud « message selon le secteur ».** Un seul graphe, un nœud qui résout
  `(secteur du contact) → (modèle)`. Plus de code, mais une seule vérité.

**Recommandation : le nœud.** Le graphe affiché est celui qui s'exécute — c'est le principe
posé pour Mozart — et sept copies divergentes le trahiraient au premier correctif.

**Garde-fous à ne surtout pas contourner** (le moteur n'a aucun privilège, c'est acquis et
ça doit le rester) : les 120 jours (`email_suppression` / `v_suppression`), les variables de
gabarit, **l'affinité d'expéditeur qui l'emporte toujours** (un contact qui a ouvert ou
cliqué garde son adresse quel que soit le réglage du nœud), les plafonds, les boîtes au
repos. Canaux : **Maildoso et Sweego uniquement** — Emelia travaille par campagne entière,
incompatible avec un scénario.

**Rappel :** Mozart est en **bêta fermée**, réservé au compte `camille`, barrière côté
serveur. Pour ouvrir : `PAGES_BETA_TESTEURS` dans `.env`. Pour sortir de la bêta : retirer
`beta: True` de la page `mozart` dans `roles_backend.PAGES`.

**Fait quand :** un contact `fleuriste` fraîchement collecté reçoit le cold email
`fleuriste:first` sans intervention, et sa relance ne part que s'il a ouvert.

---

## Lot F — Fenêtres horaires et cadence hors RAM

Les deux chantiers **écartés sciemment le 24/08** parce qu'ils touchent le chemin d'envoi
un jour où il tournait. Ils restent justes.

### F.1 — Unifier les trois fenêtres horaires

Trois implémentations de la même mécanique :

| Fonction | Fichier | Fenêtre |
|---|---|---|
| `within_send_window()` | `deliverability_agent.py:29` | campagnes, 08:01–17:59 |
| `fenetre_ouverte()` | `mozart.py:75` | scénarios, 09:01–18:30 |
| `_cadence()` | `maildoso_backend.py:674` | rythme intra-lot |

**Le vrai danger n'est pas la duplication, c'est où le contrôle se trouve :** ni
`send_email` ni `send_batch` ne vérifient l'heure — **ce sont les appelants qui le font**.
Un nouveau chemin d'appel enverrait donc à 3 h du matin sans que rien ne s'y oppose.
Correctif : une seule fonction paramétrée par profil, appelée **depuis `send_email`**.

⚠️ **Décision Camille attendue :** faut-il **aligner** les deux fenêtres ? Elles diffèrent
d'une heure de chaque côté, sans raison retrouvée. La mémoire projet retient
« lun-sam 08:01-17:59 » comme la règle — donc mon avis : Mozart s'aligne sur les campagnes.

### F.2 — Sortir la cadence par boîte de la mémoire du process

`_DERNIER_ENVOI` (`maildoso_backend.py:671`) est un dictionnaire **en RAM**. L'écart de
4 minutes entre deux envois d'une même boîte tient donc à l'intérieur d'un lot, **jamais
entre** le dispatch des campagnes (cron 8h30) et le tick Mozart (cron horaire) : deux
process différents, deux dictionnaires vides.

Correctif : lire l'horodatage dans `email_events` — comme le compteur du jour, qui a déjà
fait ce chemin. `idx_events_sent (email, occurred_at DESC) WHERE event_type='sent'` existe ;
il faut le pendant côté `mailbox` :
`CREATE INDEX idx_events_mailbox ON email_events (mailbox, occurred_at DESC) WHERE event_type = 'sent';`

**Rappel de méthode :** vérifier la cadence sur des données réparées à la main ne prouve
rien. Le test doit faire tourner les deux process pour de bon.

---

## Lot G — Documentation par rôle

**Objectif :** afficher **le bon guide selon le rôle de la session** — pas un guide unique
qui parle de pages que l'utilisateur ne voit pas.

**Étapes :** établir le plan, recenser l'existant **et** toutes les pages nouvelles
(Statistiques, Mozart, la galerie du lot C, le CRM commercial, la fiche d'appel), puis
brancher l'affichage sur `roles_backend.PAGES`, qui porte déjà la matrice des droits — la
même source décide ce qu'on voit et ce qu'on lit.

**Après le lot C**, sinon la doc décrit un écran qu'on est en train de refaire.

---

## Décisions qui n'attendent que toi

1. **Les plafonds d'envoi.** Les 4 boîtes portent **40/jour depuis leur création le
   07/07** : la montée en charge n'a jamais rien fait monter, elle a confirmé un plafond
   déjà au maximum. Un plafond de progression (+50 % de la moyenne des 7 derniers jours
   actifs) les tient à 22-24 aujourd'hui. Santé : **46 % d'ouverture sur 30 jours,
   0 plainte, 0 rebond récent**. Redescendre pour une vraie chauffe, ou assumer 40 sur des
   boîtes de sept semaines ? *Le risque était le rythme, pas le volume — le profil ne
   réclame pas qu'on redescende.*
2. **Aligner les fenêtres Mozart et campagnes ?** (lot F.1)
3. **Le nom d'expéditeur ou l'objet** pour porter la marque ? (lot D)
4. **`python3 scripts/journal_dedoublonner.py --apply`** — toujours en attente depuis le
   23/08. Retire 159 lignes de journal en double et pose l'index unique. Les lectures sont
   déjà justes sans ; c'est un nettoyage d'historique plus une ceinture. Le classifier
   refuse la suppression, donc c'est à toi de la lancer.

## Hors lots — en attente de ton feu vert

- Argumentaires `restaurant` et `tourisme` — gelés le 23/08, on reste sur l'immobilier.
- Refonte plaquette PDF (désactivée par défaut, case opt-in en place).
- Mineurs sécurité : hachage SHA-256 hérité, énumération par timing du login.
