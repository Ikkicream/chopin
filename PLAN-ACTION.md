# PLAN D'ACTION — Genesis Kill Paperclips

## Vue d'ensemble
Remplacer Paperclip ($735+ gaspillés) par un système multi-agents Claude Code avec Emelia pour le cold email, dashboard agent-flow, et contrôle depuis téléphone. Priorité : leclientroi.com.

---

## PHASE 0 — PRÉREQUIS (toi, avant tout)
- [x] Clé API DeepSeek → fournie (sk-9c4e...)
- [x] Credentials WordPress MKD → fournis (camille.afchain@protonmail.com + app password)
- [x] Clé API Anthropic → déjà en place
- [x] CSV prospects → fourni (79 263 contacts)
- [x] **Clé API Emelia** → fournie (GtUKd...)
- [x] **Domaine cold email** → leclientroi.com déjà configuré
- [x] **Boîte mail** → juliette@leclientroi.com connectée dans Emelia
- [x] **SPF/DKIM/DMARC** → déjà paramétré (Emelia configuré)
- [x] **Warmup** → vérifier le statut dans Emelia (déjà actif ?)

---

## PHASE 1 — SETUP VPS (session tmux)

### 1.1 Backup des données Paperclip
```bash
ssh -i ~/.ssh/id.mkdautoblog root@204.168.186.159
mkdir -p /home/autoblog/genesis/backup
cp -r /home/autoblog/blog/articles/ /home/autoblog/genesis/backup/lcr-articles/
rsync -av --exclude='node_modules' /home/autoblog/autoblog/agents/ /home/autoblog/genesis/backup/mkd-agents/
cp -r /home/autoblog/.paperclip/instances/default/companies/56727614-*/agents/ /home/autoblog/genesis/backup/lcr-agents/
cp -r /home/autoblog/webhook/ /home/autoblog/genesis/backup/webhook/
chown -R autoblog:autoblog /home/autoblog/genesis
```

### 1.2 Transférer Genesis depuis le Mac
```bash
scp -i ~/.ssh/id.mkdautoblog -r /Users/camille/Genesis_kill_paperclips/* root@204.168.186.159:/home/autoblog/genesis/
scp -i ~/.ssh/id.mkdautoblog /Users/camille/Genesis_kill_paperclips/.env.template root@204.168.186.159:/home/autoblog/genesis/
ssh -i ~/.ssh/id.mkdautoblog root@204.168.186.159 "chown -R autoblog:autoblog /home/autoblog/genesis"
```

### 1.3 Configurer le .env
```bash
su - autoblog
cd /home/autoblog/genesis
cp .env.template .env
nano .env  # vérifier toutes les clés, ajouter EMELIA_API_KEY
```

### 1.4 Installer les outils
```bash
# Router multi-modèle (DeepSeek/Haiku/Sonnet)
npm install -g @musistudio/claude-code-router

# Agent-flow (visualisation graph live)
mkdir -p tools && cd tools
git clone https://github.com/patoles/agent-flow
cd agent-flow && pnpm i && cd ../..

# claude-mem (mémoire inter-sessions — SQLite + ChromaDB)
npx claude-mem install
ufw deny 37777/tcp  # sécuriser le port

# knowledge-rag (RAG local — embeddings locaux, 0 API, 0 coût)
cd tools
git clone https://github.com/lyonzin/knowledge-rag
cd knowledge-rag && pip install -r requirements.txt
# → copier les docs métier dans documents/ (voir specs/rag-architecture.md)
cd ../..

# Agents-observe (observabilité)
# → installer via Claude Code marketplace une fois dans la session

# OSINT (enrichissement CSV)
pip install crosslinked poastal buster

# Créer les dossiers
mkdir -p memory/{mkd,lcr,shared} skills dashboard/assets
```

### 1.5 Lancer Claude Code dans tmux
```bash
tmux new -s genesis
cd /home/autoblog/genesis
set -a; source .env; set +a
ccr code   # lance Claude Code avec le router DeepSeek/Haiku/Sonnet
# OU: claude  (sans router si DeepSeek pas encore configuré)
```

### 1.6 Bootstrap — copier le prompt initial
→ Copier le contenu de `specs/bootstrap-prompt.md` dans Claude Code
→ Il lit le CLAUDE.md + les specs + configure les hooks

### 1.7 Activer Remote Control (contrôle depuis téléphone)
```
/remote
→ Scanner le QR code avec l'app Claude sur iPhone
```

---

## PHASE 2 — SKILLS CONTENT + ORCHESTRATEUR

### 2.1 Écrire le skill `swarm-orchestrate`
- Le cerveau : reçoit les commandes, décide, route, reporte
- Modèle : Sonnet
- Cron : lundi 6h UTC

### 2.2 Écrire le skill `swarm-content`
- Rédige + publie articles SEO
- Modèle : DeepSeek
- APIs : WordPress (MKD), Emdash (LCR), Unsplash

### 2.3 Test run complet
- Brief SEO → rédaction article → QC → images → publication
- Vérifier que l'article apparaît bien sur leclientroi.com / mkdgroupe.com

### 2.4 Écrire le skill `swarm-briefing`
- Rapport quotidien Telegram (8h Paris)
- Modèle : Haiku

### 2.5 Écrire le skill `swarm-memory`
- RAG fichiers markdown
- Met à jour articles-published.md, keywords, etc.

---

## PHASE 3 — SKILLS SEO + OUTREACH

### 3.1 Écrire le skill `swarm-seo`
- Analyse Ahrefs (MCP), GSC, veille concurrents RSS
- Modèle : Haiku
- Brief éditorial pour l'orchestrateur

### 3.2 Écrire le skill `swarm-outreach`
- Posts LinkedIn via Emelia LinkedIn Campaigns API
- Copy Meta Ads
- Modèle : DeepSeek

### 3.3 Configurer les crons
```
/schedule "lundi 6h UTC" → swarm-orchestrate (pipeline hebdo)
/schedule "chaque jour 7h UTC" → swarm-briefing (rapport Telegram)
```

---

## PHASE 4 — COLD EMAIL LCR (priorité)

### 4.1 Enrichir le CSV prospects
- Script Python : parser 79K emails → prénom/nom/entreprise
- OSINT (CrossLinked/Poastal) sur les top 500 prospects
- Segmenter en 3 tiers (voir specs/prospect-tiers.md)

### 4.2 Écrire le skill `swarm-cold-email`
- Parse CSV, génère icebreakers personnalisés
- Modèle : Sonnet (ton humain)
- Règles : cold-email-rules.md (interdits, ton, signature)
- CTA : toujours lien TidyCal https://tidycal.com/1rr6kv1/15-minute-meeting
- Signature : contact@leclientroi.com + leclientroi.com

### 4.3 Écrire le skill `swarm-campaign`
- Orchestration Emelia : crée campagnes, configure steps, injecte contacts
- Injection quotidienne progressive (voir specs/daily-injection-workflow.md)
- Monitoring stats, auto-pause si bounce > 5%

### 4.4 Créer les campagnes dans Emelia
```
POST /emails/campaigns → "LCR-TIER1-Mai2026" (retail/hôtel/immo)
POST /emails/campaigns → "LCR-TIER2-Mai2026" (agences marketing)
POST /emails/campaigns → "LCR-TIER3-Mai2026" (grands comptes)

PATCH .../steps → séquence 3 emails pour chaque tier
  Email 1 (J+0) : icebreaker + valeur + lien TidyCal
  Email 2 (J+3) : relance + guide LCR
  Email 3 (J+7) : dernière relance + livre blanc PDF
```

### 4.5 Warmup (semaines 1-2 après setup boîtes)
- Emelia warmup automatique activé
- 0 envoi pendant 2-3 semaines
- Pendant ce temps : enrichissement CSV + préparation séquences

### 4.6 Montée en charge progressive
```
Semaine 3 :   5/jour   → micro-test
Semaine 4 :  10/jour   → test, mesurer open rate
Semaine 5 :  15/jour   → ramp si open rate > 25%
Semaine 6 :  25/jour   → ramp
Semaine 7 :  40/jour   → accélération
Semaine 8 :  50/jour   → croisière
Semaine 10 : 80/jour   → scale (ajouter boîtes mail)
Semaine 12 : 150/jour  → full scale
```

### 4.7 Monitoring quotidien (automatisé par l'agent)
- Matin 7h : GET /statistics → check métriques avant injection
- Open rate < 18% → redescendre d'un palier + alerte Telegram
- Bounce > 3% → diviser le quota par 2
- Bounce > 5% → PAUSE campagne
- Réponses positives → alerte Telegram immédiate

### 4.8 Sync Emelia → Twenty CRM (chaque soir 19h)
- GET /activities → récupérer tous les événements du jour
- Créer/mettre à jour les contacts dans Twenty CRM avec statut (sent/opened/clicked/replied/bounced)
- Réponse positive → tag `lead_hot` + alerte Telegram
- Clic TidyCal → tag `demo_requested`
- Pipeline CRM : email_sent → email_opened → email_clicked → demo_requested → client
- Voir specs/emelia-to-twenty-sync.md

### 4.9 Rapport Telegram hebdomadaire (chaque lundi 9h Paris)
- Nombre envoyés, ouverts, cliqués, réponses de la semaine
- Liste nominative des cliqueurs (prénom, nom, entreprise, email, date)
- Stats pipeline CRM (combien à chaque étape)
- Budget restant (Anthropic + DeepSeek)
- Alertes si métriques hors cible

### 4.8 Écrire le skill `swarm-email-marketing`
- Newsletter mensuelle (Resend ou Emelia)
- Modèle : DeepSeek

---

## PHASE 5 — DASHBOARD + MONITORING

### 5.1 Setup agent-flow
```bash
cd /home/autoblog/genesis/tools/agent-flow
pnpm run setup  # configure les hooks Claude Code
pnpm run dev    # lance le dashboard graph live
```

### 5.2 Setup agents-observe
```
# Dans Claude Code :
marketplace add simple10/agents-observe
```

### 5.3 Dashboard custom (HTML + Chart.js)
- Page health check : statut connexions + crédits Anthropic/DeepSeek
- Data table : runs, modules, coûts, statuts
- Charts : coûts/jour, articles publiés, campagnes Emelia
- Servie par Nginx sur genesis.mkdgroupe.dev

### 5.4 Configurer Nginx
- Vhost genesis.mkdgroupe.dev
- Certbot SSL
- Proxy vers agent-flow + agents-observe + dashboard custom

---

## PHASE 6 — ARRÊT PAPERCLIP

### 6.1 Vérifier que tout tourne sans Paperclip
- [ ] Articles se publient sur LCR et MKD
- [ ] Briefing Telegram arrive chaque matin
- [ ] Campagnes Emelia tournent avec les stats
- [ ] Dashboard accessible
- [ ] Remote Control fonctionne depuis téléphone

### 6.2 Stop Paperclip
```bash
su - autoblog
pm2 stop paperclip
pm2 delete paperclip
pm2 save
```

### 6.3 Nettoyage VPS
```bash
# Supprimer les données lourdes Paperclip
rm -rf /home/autoblog/.paperclip/instances/default/data/run-logs/
rm -rf /home/autoblog/.paperclip/instances/default/data/backups/
rm -rf /home/autoblog/.paperclip/instances/default/logs/
rm -rf /home/autoblog/.paperclip/instances/default/db/
# Garder le backup dans /home/autoblog/genesis/backup/
```

### 6.4 NE PAS TOUCHER
- emdashcms (PM2 root) → CMS de LCR
- lcr-webhook (PM2 root) → webhook Tally → Twenty
- Twenty CRM (Docker) → CRM contacts
- Nginx → reverse proxy

---

## BUDGET

### Coûts récurrents
| Poste | Coût | Fréquence |
|---|---|---|
| Anthropic (Sonnet + Haiku) | ~$4-10 | /semaine |
| DeepSeek | ~$0.50-2 | /semaine |
| Emelia (plan Start) | 37€ | /mois |
| Domaine cold email | ~10€ | /an |
| VPS Hetzner | déjà payé | /mois |
| **TOTAL** | **~$60-80/mois** | vs $550+/mois Paperclip |

### Budget Anthropic actuel : ~$20
- Mode survie activé (23 agents Paperclip en pause)
- $20 = ~2-5 semaines avec le nouveau système
- Recharger quand on passe en croisière

---

## FICHIERS DE RÉFÉRENCE

| Fichier | Contenu |
|---|---|
| `CLAUDE.md` | Instructions globales Claude Code |
| `.env.template` | Toutes les clés API |
| `specs/architecture-v2.md` | Architecture complète 10 skills |
| `specs/stack-tools.md` | Stack : quoi installer vs coder |
| `specs/dashboard-specs.md` | UX/UI agent-flow + dataviz |
| `specs/vps-setup.md` | Guide déploiement VPS |
| `specs/bootstrap-prompt.md` | Prompt initial pour Claude Code |
| `specs/pre-transfer-checklist.md` | Checklist backup avant nettoyage |
| `specs/enrichment-pipeline.md` | Pipeline enrichissement CSV (0 coût) |
| `specs/prospect-tiers.md` | 3 tiers de prospects (Tier1/2/3) |
| `specs/daily-injection-workflow.md` | Workflow injection quotidien Emelia |
| `context/lcr/campaign-plan.md` | Plan campagne cold email LCR |
| `context/lcr/goals.md` | Goals leclientroi.com |
| `context/lcr/article-templates.md` | Templates articles LCR |
| `context/mkd/goals.md` | Goals mkdgroupe.com |
| `context/shared/credentials.md` | Accès VPS + APIs |
| `context/shared/cold-email-rules.md` | Ton, interdits, signature, TidyCal |
| `context/shared/emelia-api.md` | 71 endpoints Emelia |
| `context/shared/emelia-knowledge/` | Base connaissance Emelia (4 fichiers) |
| `context/shared/prospects.csv` | 79 263 contacts B2B |


---

## SPRINT FUTUR — Templates cold email à structure HTML verrouillée
> Ajouté 2026-05-25, après la refonte génération cold email (cf. STATE.md § COLD EMAIL).

**Besoin (user)** : fournir une **base HTML par template** (mise en page fixe : header, image, sections, footer). Dans l'éditeur, on ne doit pouvoir changer QUE les **textes, images et liens** — la **structure reste identique**.

**Mécanisme retenu**
- Placeholders nommés `{{...}}` dans le HTML fourni par le user.
- Type de zone détecté par **contexte** : `src="{{x}}"` → IMAGE · `href="{{x}}"` → LIEN · sinon → TEXTE.
- L'UI génère un **éditeur de zones** (formulaire : un champ par zone) qui **remplace l'éditeur Tiptap libre** ; la structure HTML est figée, jamais éditée à la main.
- **DeepSeek ne remplit QUE les zones TEXTE** (à partir de `context/lcr/sector-angles.md`) ; images / liens / structure inchangés.
- Validateur (≤150 mots, 1 CTA, interdits FR — `email_generator.validate_email`) appliqué au texte des zones.
- Stockage : **template (structure) + valeurs des zones (JSON)** ; HTML final = structure + substitution.

**À clarifier au lancement** : une structure unique pour tous, ou une par secteur / par type d'email (1er vs relance) ?

**Impact technique**
- `src/components/email-body-editor.tsx` (Tiptap) → nouveau `email-zones-editor.tsx` (formulaire de zones).
- `scripts/email_generator.py` : génère des **valeurs de zones texte** au lieu d'un body HTML complet.
- `scripts/email_templates_backend.py` + table `email_templates` : stocker template HTML + zones (JSON) au lieu de `body_html` brut.
- L'aperçu reste un rendu HTML (structure + zones substituées + variables Emelia d'exemple).

**Prérequis** : le user fournit le(s) HTML de base (collé ou déposé sur le VPS).


---

## SPRINTS AUTH / RBAC / RGPD — plan validé 2026-05-26

Contexte : beaucoup d'auth existe DÉJÀ (TOTP `pyotp`, login 2-étapes, page `/security` avec QR PNG, champ `role`, CRUD `/api/auth/users`, `reset_password` admin, `send_password_telegram`). Décisions user : **3 rôles fixes** (superadmin / stratégie / contenu / commercial), **superadmin = tous les sites**, users normaux = **1 seul site**.

### Sprint 1 — Auth & 2FA : fix + finalisation
- [ ] Fix bug `nav-user.tsx` (menu user en bas de sidebar → accès `/security` + logout)
- [ ] Tester le flux 2FA end-to-end (login 2-step → setup QR → confirm → disable)
- [ ] Création de compte (superadmin) : mot de passe temporaire + **bloc COPIABLE** (identifiant, mdp, URL login, pas-à-pas 2FA/QR à transmettre hors-email)
- [ ] Aucun reset par email (confirmer) ; reset = superadmin only ; option : forcer le 2FA à la 1ʳᵉ connexion

### Sprint 2 — RBAC (3 rôles) + isolation « 1 user = 1 site »
- [ ] Rôles superadmin/stratégie/contenu/commercial → mapping rôle → sections sidebar
- [ ] Backend : helper central d'enforcement `site ∈ session.sites` + module autorisé par rôle, sur les ~40 endpoints `/api/sites/{site}/*` (superadmin = bypass) — **FERME LA FAILLE** actuelle
- [ ] `users.sites` = exactement 1 site (non-superadmin), validé à la création
- [ ] Front : sidebar filtrée par rôle ; switcher de sites masqué si 1 seul site
- [ ] UI superadmin : CRUD users (créer / **bloquer** [champ `disabled`] / changer rôle / changer site / reset mdp)
- [ ] Migration : peupler `users.sites` + désigner le superadmin

### Sprint 3 — Revue de sécurité
- [ ] `/security-review` sur auth/RBAC/isolation (déclenché par le user)

### Sprint 4 — RGPD / Privacy by design (outil B2B exclusivement)
- [ ] 4a : **questions de cadrage RGPD** PUIS LIA intérêt légitime [lawve.ai legitimate-interest · O. Schmidt-Prietz] + compliance [lawve.ai]
- [ ] 4b : politique de confidentialité / privacy notice [lawve.ai gdpr-privacy-notice-eu]
- [ ] 4c : sécurisation données contacts (chiffrement at-rest, contrôle d'accès, rétention/purge)
- [ ] 4d : caviardage PDF [github Ldecavel/skill-caviardage-pdf] + anonymisation [datanaos]
- Liens ouverts au lancement du sprint ; questions d'abord.

Ordre conseillé : S1 → S2 → S3 → S4.

### Sprint technique — Durcissement du déploiement front (staleness) [ajouté 2026-05-26]
**Problème observé** : chaque `npm run build` régénère les IDs internes Next (chunks, Server Actions). Un onglet resté ouvert sur l'ancien build casse → page « This page couldn't load » et logs `genesis-ui-error.log` saturés de `Failed to find Server Action "x"`. Récurrent à chaque déploiement front.
**À faire** :
- Exposer un **build-id** (ex. `GET /api/version` ou variable injectée au build) et le comparer côté client → **bannière « Nouvelle version disponible — recharger »**.
- Ajouter un **`global-error.tsx` FR** + error boundary qui propose « Recharger » proprement (au lieu du message Next brut anglais).
- Optionnel : reload auto si le build-id change ; filtrer le bruit de scan dans les logs.
**Priorité** : basse (polish), mais à traiter car ça pollue l'UX à chaque déploiement.

### Sprint — Éditeur de newsletters HTML (concrétise le « sprint futur templates HTML ») [2026-05-26]
**Besoin** : créer des templates email à partir d'une **structure HTML de base** (ex. `~/Desktop/LCR/leclientroi-newsletter-v2.html`), éditable en mode SIMPLE — **uniquement texte + images, jamais la structure**.
**Structure v2 analysée** : HTML email (tables, styles inline, Plus Jakarta Sans), ~8 `<img>` + 1 image de fond (hero), ~20 zones texte (h1/h2/h3/p/span), liens CTA, variables Emelia `{{unsubscribe_url}}`/`{{preferences_url}}`.
**Goal user** :
- Aperçu fidèle de la newsletter.
- Éditer le **texte** en mode simple.
- Modifier une **image** : icône « modifier » → dialog shadcn (aperçu image actuelle + **meta taille/poids** + **input URL** nouvelle image + boutons Valider/Confirmer).
- **Sauvegarder** : nommer la version + date.
- **Envoyer à Emelia** (1er temps), puis autres canaux.
- **Stepper templates — step 2** : « Sélectionner un template HTML » EN PLUS de « Générer (IA) ».
**Technique** : stockage versionné (table `html_templates`), meta image via fetch (HEAD = poids, dimensions), envoi = HTML en step Emelia (`rawHtml:true`).
**À trancher avant de coder** : mode d'édition (in-place sur l'aperçu vs panneau de zones).
