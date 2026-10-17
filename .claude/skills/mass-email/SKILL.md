---
name: mass-email
description: Mass Email (mail.cheffer.email) — emailing en masse séparé de Cheffer : import CSV, public B2C/B2B, nettoyage Mailnjoy, envoi Sweego 1 pour 1, montée en charge par paliers et par fournisseur, délivrabilité, désinscription, page de rappel. Utiliser pour tout ce qui touche à genesis/mass_mailing, à genesis-ui/src/app/mass-email, à une campagne Mass Email, à son envoi ou à ses statistiques.
---

# Mass Email — l'emailing en masse (mail.cheffer.email)

Outil interne de Camille, **séparé de Cheffer** depuis le 26/09/2026 : service à part, PostgreSQL seul,
**jamais DuckDB**. Lire aussi `.claude/skills/sweego/SKILL.md` avant toute affirmation sur l'API Sweego,
`.claude/skills/delivrabilite/SKILL.md` avant tout envoi en masse et `.claude/skills/anti-bot-clics/SKILL.md`
pour tout ce qui touche au verdict des clics.

## 1. Où vit quoi

| Élément | Emplacement |
|---|---|
| Serveur (FastAPI) | `mass_mailing/serveur.py` → PM2 `mass-mailing-api`, 127.0.0.1:8090, compte autoblog |
| Worker (jobs : import, validation, envoi, clics, resynchro stats) | `mass_mailing/worker.py` → PM2 `mass-mailing-worker` |
| Routes | `mass_mailing/api/routes.py` (`router` `/api/mass-mailing/*` sous jeton `mm_…`, `public_router` `/api/public/mass-mailing/*`) |
| Base | schéma PG `mass_mailing` (`schema.sql`, migrations `ADD COLUMN IF NOT EXISTS` en fin de fichier) ; accès `from infra import pg` → `pg.ligne / pg.lignes / pg.valeur / pg.ecrire` |
| Connexion | `infra/auth.py` : tables `utilisateurs` (bcrypt + TOTP) et `sessions` (7 j) ; compte `camille` |
| Interface | `genesis-ui/src/app/mass-email/` (Next, servie sous mail.cheffer.email). **Dossier NON versionné** : sauvegarder dans `/home/autoblog/sauvegardes/` avant de toucher |
| Nginx | `/etc/nginx/sites-available/mass-email` : `/api/` → 8090, `/mass-email*` + `/_next/` → Next 3100 |
| Webhook Sweego dédié | `mass-email` (uuid 098499f8-…) → `https://mail.cheffer.email/api/public/mass-mailing/webhook?token=…`, table `webhook_events` |
| Outils | `/home/autoblog/outils-captures/` : `mm-shoot-pg.py` (captures), `phases_live.py` (paliers), `montee_fournisseurs.py` (étalement), `sonde_cheffer.py`, résultats dans `mm-audit/` |

## 2. Règles à ne jamais casser

1. **1 destinataire = 1 appel `/send`** (`infra/sweego.envoyer_un`, `assert len(recipients) == 1`). Jamais de `/send` à N : ce serait un mail de groupe.
2. **Jamais de double envoi** : `queued → submitted` une seule fois ; un appel incertain (délai dépassé) est marqué `failed` et n'est PAS rejoué.
3. **Suppression relue juste avant chaque lot** (`envoi.envoyer_lot`).
4. **Public B2C / B2B obligatoire** (`campaigns.audience`). En **B2C, aucune adresse d'organisation ne part** (consigne de Camille du 26/09, après un envoi B2C parti chez bnpparibas.com) : voir § 4.
5. **Rien ne part sans feu vert** (`envoi.autoriser`) et sans préflight au vert.
6. **Fenêtre d'envoi** : lun-sam 08:01-17:59, heure de Paris (Camille peut l'étendre ponctuellement : noter pour QUEL envoi).
7. **Ne rien redémarrer pendant une validation Mailnjoy** : chaque redémarrage du worker consomme un essai (5 au plus) sur les jobs en cours.
8. **Toute adresse testée dans un palier est retirée de la campagne source** (`eligibility_reason = 'envoye_en_test'`) : jamais deux fois le même mail à la même personne.

## 3. Le parcours d'une campagne

Assistant (5 étapes, autosauvegarde) : **1. Libellé + public (B2C/B2B)** → **2. Fichier** (CSV ou liste collée ;
`jobs/analyze_csv.py`) → **3. Nettoyage Mailnjoy** par lots de 1 000 (`jobs/validation.py`) → **4. Message**
(`infra/controle_html.py`, `infra/harmonisation.py`) → **5. Planification** (BAT, page de rappel, feu vert).

- `dispatch_mode` : `progressive` (chaque lot validé part aussitôt) ou `after_validation`.
- Statuts : `draft → ready_for_validation → validating_list → ready_to_schedule → sending → completed`.
- Duplication : `POST /campaigns/{id}/dupliquer` copie message, expéditeur, domaines, type, mode, rappel ET public, jamais la cible.

## 4. Public B2C / B2B (`infra/domaines.py`)

- `GRAND_PUBLIC` = messageries et FAI ouverts aux particuliers (gmail, hotmail/live/outlook/msn, yahoo, aol,
  icloud, **privaterelay.appleid.com** (relais Apple = un particulier), orange/wanadoo, free, sfr/neuf, laposte,
  bbox, gmx…). **Tout autre domaine = organisation** (« entreprise » ou « administration » : mairies,
  universités, `.gouv.fr` ; cette distinction ne sert qu'à l'affichage).
- Règles de Camille : `settings.domain_rules = {"grand_public": [...], "entreprise": [...]}`, prioritaires ;
  routes `GET/PUT /reglages/domaines` (`{"domaine", "classe": "grand_public"|"entreprise"|null, "campaign_id"?}`).
- **B2C** : l'adresse d'organisation est écartée **à l'import** (`eligibility_reason = 'hors_cible_b2c'`,
  avant Mailnjoy donc sans crédit), puis revérifiée au **préflight** (contrôles `public` et `b2c`, bloquants)
  et **juste avant chaque lot**.
- **B2B** : rien n'est écarté ; les adresses personnelles sont seulement comptées.
- Changer le public : `PATCH /campaigns/{id} {"audience"}` → `domaines.reevaluer()` (une adresse déjà passée
  chez Mailnjoy n'est pas réintégrée : réimporter).
- Écran : `_public.tsx` (ChoixPublic, BadgePublic, ControleDomaines), `GET /campaigns/{id}/domaines`.

## 5. Délivrabilité — ce qu'on sait (audit du 26/09, `mm-audit/audit_delivrabilite.md`)

- Domaine d'envoi `news.leclientroi.email` : SPF, DKIM et DMARC `p=reject` OK, aucune liste noire.
  **Mais réputation 🟠** : il est surtout utilisé par la plateforme LeClientRoi (campagne « default »,
  ~16 % de rebonds durs) et l'IP partagée en hérite. Gmail 97 % livrés ; Microsoft 92 % livrés mais ~0,4 %
  d'ouvertures (indésirables) ; Orange, SFR, Yahoo 64-72 % ; Free bloqué.
- `news.leclientroi.app` n'est PAS libre (webhooks LeClientRoi) ; `leclientroi.com` = Google Workspace, jamais pour la masse.
- Recommandé : sous-domaine réservé à Mass Email, chauffé sur 2-3 semaines ; liens sous le domaine d'envoi ;
  retirer le lien piège caché ; corriger la phrase « vous êtes client… » si la liste vient d'un tiers (CNIL).
- **Débit** : `settings.max_rate_per_minute` = 100 par défaut (600 avant le 26/09 : trop). Par fournisseur :
  Gmail 60/min, Microsoft 20, Yahoo 10, Orange/SFR/autres 5.
- **Seuils d'arrêt** : rebonds durs > 2 %, non-livrés > 5 %, plaintes > 0,1 % (arrêt ferme 0,3 %),
  Microsoft < 1 % d'ouvertures humaines 2 h après = probablement en indésirables.
- **Lire les chiffres** : « livré » ne veut pas dire « boîte de réception » (les indésirables comptent comme
  livrés). Les ouvertures humaines sont le vrai signal. Les logs Sweego ont ~7-10 min de retard ; le webhook
  dédié est en temps réel.

## 6. Montée en charge

- **Paliers** (`phases_live.py`) : 1 → 10 → 100 → 200 → 400 → 500, une campagne « Test unitaire N » par palier,
  analyse à +10 min, palier suivant à +15 min, dédoublonnage strict (jamais une adresse déjà reçue ni en
  suppression), arrêt automatique au rouge. Reprise d'un palier déjà parti : `REPRISE="k:cid:epoch_fin_envoi"`.
  Un palier est un test de sécurité, **pas un warm-up** (qui se compte en jours).
- **Étalement par fournisseur** (`montee_fournisseurs.py`) : une campagne « JAECOO J<n> — <fournisseur> » par
  fournisseur, du plus fragile au plus solide, chacune à son débit ; bilan 2 h après ; un fournisseur au rouge
  est sauté le lendemain. C'est un process `nohup` : **un reboot le tue**, vérifier qu'il tourne.

## 7. Désinscription

- Lien personnel signé en pied (`infra/desinscription.py`), page publique `/api/public/mass-mailing/desinscription?t=…`.
- **Piège vu le 26/09** : les scanners de sécurité d'entreprise (BNP, Defender Safe Links, Proofpoint,
  Mimecast) ouvrent TOUS les liens d'un mail. Un GET qui désinscrit les fait désinscrire à la place du
  destinataire. Correctif : GET = page de confirmation, POST = désinscription
  (`outils-captures/correctifs/desinscription-get-confirmation.patch`).
- En-tête `List-Unsubscribe` one-click (RFC 8058) : `sweego.envoyer_un(url_desinscription=…)` → objet
  `list-unsub` `{"method": "one-click", "value": "<mailto:list-unsub@<domaine>>,<url>"}`. Ne JAMAIS envoyer en
  plus un en-tête `List-Unsubscribe` dans `headers` (il deviendrait `X-List-Unsubscribe`).
- Clics : verdict humain / robot / suspect (`jobs/clics.py`, `settings.click_rules`). Un scanner = toutes les
  URL en quelques secondes → « robot ».

## 8. Déployer, tester, montrer

- **Serveur** : les modifications de `mass_mailing/` ne prennent effet qu'au redémarrage de `mass-mailing-api`
  et/ou `mass-mailing-worker` (PM2, compte autoblog). Écrire du code **rétrocompatible** : le worker peut
  redémarrer à tout moment.
- **Interface** : `npx tsc --noEmit` (le build ignore les erreurs de type), puis
  `NEXT_DIST_DIR=.next-verify npx next build`, puis `npx next build` et `pm2 restart genesis-ui`.
  Un build raté vide `.next` : toujours compiler dans `.next-verify` d'abord.
- **Prévisualiser sans toucher à la prod** : API copie `python3 -m uvicorn mass_mailing.serveur:app --port 8099`
  + `NEXT_DIST_DIR=.next-verify npx next start -p 3199`, puis
  `BASE=http://127.0.0.1:3199 API_LOCAL=http://127.0.0.1:8099 python3 mm-shoot-pg.py <suffixe> <clés>`
  (Playwright redirige `/api` vers la copie). Tuer le `next-server` par son port à la fin (`pkill` sur la
  ligne de commande ne l'attrape pas).
- **Captures** : `mm-shoot-pg.py` ouvre une session `mm_` puis la ferme ; ne plus utiliser `mm-shoot.py`
  (il écrit dans `data/auth.duckdb`, obsolète depuis la séparation).
- **Tester sans écrire en vrai** : campagne jetable « ZZ … », supprimée dans un `finally` ; ou copie isolée
  d'un module chargée avec `importlib` + `fastapi.testclient`.
- **Sondes HTTP** : Cloudflare renvoie 403 à l'agent « Python-urllib » ; mettre un User-Agent de navigateur.
- Toujours montrer l'interface **avant / après** (captures dans `mm-audit/`), un sujet à la fois.

## 9. Bouton « Webmails » et classement des webmails (26/09/2026)

Cahier de Camille : `references/tache-webmails.md` (résumé ci-dessous).
- **Liste des campagnes** : dernière colonne « Webmails » (`_bouton-webmails.tsx` `BoutonWebmails`) :
  démo 21st.dev « Tooltip Metrics Card » (Ark UI `@ark-ui/react`, installé avec **pnpm** — le projet
  genesis-ui est en pnpm, `npm i` casse avec « Cannot read properties of null (reading 'matches') »).
  UN seul `<button>` (`Tooltip.Trigger asChild`), `stopPropagation` (pas de clic de ligne), mini-carte :
  délivrabilité = livrés/envoyés, ouvertures/envois = ouvertures uniques HORS robots / envoyés,
  plaintes = plaintes / livrés (3 décimales). Compteurs `ouvertures_uniques`, `plaintes` dans GET /campaigns.
- **Fenêtre** : UN `Dialog` pour toute la table (`selectedCampaignId`), onglets Délivrabilité / Ouvertures,
  données chargées à l'ouverture : `GET /campaigns/{id}/webmails` = compteurs PAR DOMAINE (aucune adresse).
- **Calcul** : `_webmails.ts` (fonctions pures) : domaines → webmail, sommes brutes, `MIN_SENT = 200`,
  « Autres » jamais classé, iCloud hors classement en mode ouvertures (Apple MPP), égalité → autre
  métrique puis volume, format français « 99,2 % » / « 12 480 ». Tests : `pnpm test` (node
  --experimental-strip-types, `tests/webmails.test.mjs`, 8 tests).
- **Classement** : `src/components/ui/leaderboard-rankings.tsx` reconstitué depuis le bundle public
  21st.dev (pas de clé `API_KEY_21ST` sur le serveur), seule modif : prop `formatValue`.
- Plaintes : `suppressions.reason = 'complaint'` (metadata.swg_uid) ou `webhook_events` `%complaint%`.
- Logos `public/webmails/<clé>.svg` : aucun à ce jour (liste `LOGOS` dans `_bouton-webmails.tsx`), initiales.
- « Dernière activité » de la liste passée en `2xl` pour que la colonne tienne sans débordement.

## 10. Parcours de la liste = Sankey (26/09/2026, version en ligne)

Camille voulait le composant 21st.dev « LegionWebDev/allocation-echarts-sankey-chart » ADAPTÉ à nos étapes
(la 1re refonte en 3 colonnes de texte a été rejetée : « c'est n'importe quoi »).
- `src/components/ui/allocation-echarts-sankey-chart.tsx` : copie exacte du démo.
- `src/components/ui/allocation-echarts-sankey-chart-utils/echarts-sankey-chart.tsx` : moteur « Evil Charts »
  reconstitué depuis le bundle public (le fichier n'est servi qu'avec la clé 21st ; `shadcn add` → 403).
  Dépendance `echarts` (pnpm). Seul écart : badge Loading sans framer-motion.
- `src/app/mass-email/_parcours-sankey.tsx` : nœuds = Fichier → Éligibles → Envoyés → Livrés → Clics humains →
  « Oui, rappelez-moi », pertes à côté de leur étape (doublons, adresses pro, désinscrits, refus Mailnjoy,
  paliers, pas encore partis, rebonds, refus Sweego, statut inconnu, robots, suspects, sans clic).
  `align="left"` OBLIGATOIRE (sinon les petites pertes sont poussées dans la dernière colonne).
  Noms de nœuds = clés ASCII (servent de variables CSS), libellés dans `config`. Données : `parcours` de la fiche.
- L'ancien `_parcours.tsx` (3 colonnes) n'est plus utilisé.

## 11. Rebonds, liste noire globale, risque d'adresse, entonnoir (30/09/2026)

Documentation technique complète : `references/rebonds-entonnoir-reputation.md`. Le pourquoi et les chiffres : skill `risque-adresses`.
- `jobs/rebonds.py` (worker, toutes les heures) : échecs Sweego de TOUT le compte → hard / soft / refus liés à l'IP → liste noire globale (`hard_bounce`, `soft_bounce`). **Un refus lié à l'IP n'entre jamais en liste noire.**
- `jobs/risque_adresses.py` (worker, chaque jour) : probabilité de hard par adresse (Bayes naïf, AUC 0,80) ; conseil seulement.
- Colonne Performance = **entonnoir** importés → Mailnjoy → autres exclusions → éligibles → envoyés → délivrés (`ENTONNOIR_SQL`).
- UCEPROTECT niveaux 2/3 = avertissement, **pas** blocage (`hetrix.LISTES_RESEAU`).
