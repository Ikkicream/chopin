# Tâche : bouton « Webmails » dans la datatable des campagnes + classement des webmails

> Cahier fourni par Camille le 26/09/2026 (copie fidèle). Réalisation : voir `../SKILL.md` § 9.
> Écarts assumés : la clé `API_KEY_21ST` n'existe pas sur le serveur → le composant
> LeaderboardRankings a été reconstitué depuis le bundle public 21st.dev ; l'en-tête de la
> mini-carte montre le libellé de la campagne (l'id est un UUID illisible) ; le projet est en
> pnpm (et non npm) ; les tests passent par le lanceur intégré de Node 22 (aucune dépendance).

## Contexte
Tableau de bord de délivrabilité emailing (France, B2C et B2B). La datatable des campagnes affiche une ligne par campagne. Ajoute sur chaque ligne un bouton qui :
1. au survol ou au focus clavier, affiche une mini-carte avec les métriques de la campagne ;
2. au clic, ouvre une fenêtre qui classe les webmails (Gmail, Outlook, Orange, SFR, Free, La Poste, Yahoo, iCloud…) pour cette campagne, selon la délivrabilité ou le ratio ouvertures / envois.

## Composants
1. **Bouton + mini-carte** : reprends le démo « Tooltip Metrics Card » de 21st.dev (https://21st.dev/@anubra266/components/tooltip-1/tooltip-metrics-card). C'est un démo construit directement avec Ark UI, il n'y a rien à installer depuis 21st.dev. Il suffit de lancer `npm i @ark-ui/react lucide-react`.
   - Garde sa structure : `Tooltip.Root openDelay={0} closeDelay={0}`, puis `Tooltip.Trigger` (icône `BarChart3` + libellé), puis `Portal > Tooltip.Positioner > Tooltip.Content` avec un en-tête gris et 3 lignes « pastille de couleur + libellé + valeur en gras ».
   - Les classes `animate-fade-in` / `animate-fade-out` supposent des keyframes Tailwind. Ajoute-les si le projet ne les a pas, sinon retire ces classes.
2. **Classement** : `npx shadcn@latest add "https://21st.dev/r/trophyso/leaderboard-rankings?api_key=$API_KEY_21ST"`
   - La clé 21st.dev est dans la variable d'environnement `API_KEY_21ST`. Ne l'écris jamais dans le code et ne la committe pas. Sans clé, la commande répond « Authentication required ».
   - API du composant : `<LeaderboardRankings rankings={[{ userId, rank, userName, byline, value, avatarUrl, displayed }]} />`.
   - Il affiche `value` en nombre compact (289400 devient 289.4k). Lis `Component.tsx` et ajoute une prop optionnelle `formatValue?: (v: number) => string`, dont la valeur par défaut garde le comportement actuel, pour pouvoir afficher des pourcentages. Ne change rien d'autre dans ce composant.
3. **Fenêtre** : le `Dialog` shadcn du projet. S'il manque, installe-le avec `npx shadcn@latest add dialog`.

## Comportement
- Ajoute une colonne « Webmails » en dernière position de la datatable. Chaque ligne a un bouton libellé « Webmails », avec l'icône `BarChart3` et le style du démo.
- **Survol et focus** affichent la mini-carte :
  - en-tête : « <id campagne> · <envois formatés> envois » ;
  - ligne bleue : Délivrabilité = délivrés / envoyés ;
  - ligne violette : Ouvertures / envois = ouvertures uniques / envoyés ;
  - ligne rouge : Plaintes = plaintes / délivrés, avec 3 décimales (0,082 %).
- **Clic** : ouvre la fenêtre du classement.
  - Un seul `Dialog` pour toute la table, contrôlé par un état `selectedCampaignId`, et non un dialog par ligne.
  - Un seul `<button>` porte le tooltip et le clic : utilise `asChild` et ne mets jamais un bouton dans un bouton.
  - Le clic ne déclenche ni le clic de ligne ni le tri de la datatable (`stopPropagation`).
  - Le tooltip se ferme quand la fenêtre s'ouvre. Échap et clic extérieur ferment la fenêtre.
- **Contenu de la fenêtre** :
  - titre « Classement des webmails · <id campagne> », sous-titre avec la date d'envoi et l'objet ;
  - un sélecteur à deux choix (`Tabs` ou `ToggleGroup` shadcn) : « Délivrabilité » (par défaut) ou « Ouvertures / envois ». Le classement se recalcule selon le choix. En cas d'égalité, départager par l'autre métrique, puis par le volume envoyé.
- **Correspondance avec `LeaderboardRankings`** :

  | Prop | Valeur |
  |---|---|
  | `userId` | clé du webmail |
  | `rank` | rang dans le classement |
  | `userName` | nom affiché (Gmail, Outlook, Orange…) |
  | `value` | la métrique choisie en %, affichée « 99,2 % » (virgule décimale, espace insécable avant %) |
  | `byline` | « Délivrabilité 99,2 % · Ouvertures 31,4 % · 12 480 envois » |
  | `avatarUrl` | logo local `public/webmails/<clé>.svg`, avec les initiales si le logo manque. Aucun service de favicon externe. |
  | `displayed` | `true` |

## Règles de calcul
- **Grain** : campagne × webmail. Les domaines destinataires se regroupent ainsi :

  | Domaines | Webmail |
  |---|---|
  | gmail.com, googlemail.com | Gmail |
  | outlook.\*, hotmail.\*, live.\*, msn.com | Outlook |
  | orange.fr, wanadoo.fr | Orange |
  | sfr.fr, neuf.fr, club-internet.fr | SFR |
  | free.fr | Free |
  | laposte.net | La Poste |
  | yahoo.\*, ymail.com | Yahoo |
  | icloud.com, me.com, mac.com | iCloud |
  | bbox.fr | Bouygues |
  | gmx.\* | GMX |
  | tout le reste | Autres |

- **Stats déjà agrégées par fournisseur** (clés `gmail`, `microsoft`, `orange`, `free`, `sfr`, `laposte`, `yahoo`, `apple`, `other`) : `microsoft` devient Outlook, `apple` devient iCloud, `other` devient Autres.
- **Hors classement** : ces lignes s'affichent sous le classement, en gris, avec leurs chiffres et une mention :
  - « Autres » n'est jamais classé ;
  - un webmail avec moins de 200 envois (constante `MIN_SENT`) est marqué « volume insuffisant » ;
  - en mode « Ouvertures / envois », iCloud est marqué « ouvertures gonflées par Apple MPP ».
- **Calcul des pourcentages** : sur les compteurs bruts (somme des numérateurs / somme des dénominateurs), jamais en faisant la moyenne de pourcentages. Un dénominateur à 0 s'affiche « — ».

## Données
- Pour chaque campagne et chaque webmail, il faut : `sent`, `delivered`, `unique_opens`, `complaints`.
- Si la table des stats par fournisseur n'a pas de colonne d'ouvertures uniques, ajoute `unique_opens INTEGER NOT NULL DEFAULT 0`. Alimente-la depuis l'export d'événements de l'ESP avec les ouvertures uniques par destinataire, pas les ouvertures totales.
- Charge les données du classement à l'ouverture de la fenêtre, avec une requête pour la campagne concernée, et non pour toutes les lignes au chargement de la table. La mini-carte utilise les totaux déjà présents dans la ligne.
- Exemple de requête (SQLite) :
  `SELECT provider, SUM(sent) AS sent, SUM(delivered) AS delivered, SUM(unique_opens) AS unique_opens, SUM(complaints) AS complaints FROM campaign_stats WHERE campaign_id = ? GROUP BY provider;`

## Critères d'acceptation
1. Chaque ligne a son bouton. Le survol et le focus clavier (Tab) affichent la mini-carte avec les 3 bonnes valeurs.
2. Le clic ouvre le classement de CETTE campagne, et basculer le sélecteur réordonne la liste.
3. Les couronnes du composant désignent les 3 premiers webmails classés. « Autres », les webmails sous `MIN_SENT` et iCloud en mode ouvertures sont hors classement.
4. Les nombres sont au format français partout : « 99,2 % », « 12 480 ».
5. Le mode sombre est correct : utilise les tokens `bg-popover`, `text-popover-foreground` et `border-border`.
6. Aucune régression sur le tri, la pagination et le clic de ligne de la datatable.
7. La fonction de calcul du classement a des tests unitaires : regroupement des domaines, seuil `MIN_SENT`, exclusion d'iCloud en mode ouvertures, départage des égalités, division par zéro.

Ne modifie que ce qui est nécessaire. À la fin, liste les fichiers créés ou modifiés et les commandes lancées.
