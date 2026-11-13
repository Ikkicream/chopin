# Onboarding Checklist — Nouveau site Genesis

> Spec opérationnelle. Liste exhaustive des questions à poser et configurations à faire pour démarrer un nouveau site sur Genesis. Format step-by-step, à brancher dans `genesis-ui/src/app/onboarding/page.tsx` (refonte).

## Vue d'ensemble — résumé en tableau

| # | Step (titre H2) | Sortie attendue | Bloquant ? |
|---|---|---|---|
| 1 | Identité du site | code 3-lettres + nom + domaine | OUI |
| 2 | Stack & URLs publiques | URLs live/preview/staging | OUI |
| 3 | Persona client & zone géographique cible | description + pays/régions | OUI |
| 4 | Goals SEO & concurrents | mots-clés cibles + 5-10 concurrents | OUI |
| 5 | Ton éditorial & CTA standard | guide style + CTA fil rouge | NON (peut être complété après) |
| 6 | Secteurs de prospection | parmi 6 secteurs (+ ordre de priorité) | OUI |
| 7 | Sender email (provider Gmail) | adresse + nom + signature | OUI |
| 8 | Mention RGPD pied de mail | bloc texte standardisé | OUI |
| 9 | Clés API site-specific | Emelia, Serper, Tally, Telegram, webhook tokens | OUI |
| 10 | Templates initiaux par secteur | 1 template par secteur (peut être généré IA) | NON (lazy) |
| 11 | Warmup sender | date J0 + plan A/B | OUI |
| 12 | Modules activés | SEO / Content / Workflow / Tally / Emelia / ... toggles | OUI |
| 13 | Projet Ahrefs Site Audit | project_id (ou "à créer dans l'UI Ahrefs") | NON (peut attendre) |
| 14 | Quota daily Emelia & cooldowns | nombre max contacts/jour + cooldown re-push | OUI |
| 15 | Compte propriétaire (multi-tenant) | account_id (qui possède ce site) | OUI |
| 16 | Validation finale par mail test | mail test reçu + clic lien activation | OUI |

---

## Steps détaillés

## Step 1 : Identifiant et nom commercial du nouveau site (code court, nom officiel, domaine principal)

**Pourquoi** : ces 3 champs identifient le site dans toutes les DBs (`site_code` comme clé), dans les chemins fichiers (`/data/crm/{code}.duckdb` legacy), dans les URLs (`/site/{code}/...`), et dans les notifications. Une fois choisi, le code est immuable.

**Inputs** :
- `site_code` (3-4 lettres en lowercase, ex: `lcr`, `mkd`, `tvz`)
- `site_name` (label utilisateur, ex: "LeClientROI")
- `domain` (sans http, ex: `leclientroi.com`)
- `logo` (upload optionnel, sinon initiales)

**Sortie** : insertion dans `sites_config.py` registry + création des dossiers `memory/{code}/`, `context/{code}/`, etc.

---

## Step 2 : URLs publiques (production, preview/staging) et CMS utilisé par le site

**Pourquoi** : permet au `health_check`, à `indexation_agent`, et au `publish_agent` de savoir où publier les articles et où vérifier le statut HTTP.

**Inputs** :
- `url_production` (ex: `https://leclientroi.com`)
- `url_preview` (optionnel, branch staging)
- `cms_type` (parmi : `emdash`, `wordpress`, `next-static`, `aucun`)
- Si CMS = Emdash → `emdash_workspace_id`
- Si CMS = WordPress → `wp_url`, `wp_user`, `wp_app_password`

**Sortie** : `context/{code}/site.json` enrichi.

---

## Step 3 : Persona client cible et zone géographique principale (qui on cherche à atteindre)

**Pourquoi** : alimente tous les prompts DeepSeek (qualifier sectoriel, content writer, brief agent). Sans ça l'IA tire au hasard.

**Inputs** :
- `persona` (1 paragraphe, ex: "dirigeants de TPE/PME locales en France, 30-55 ans, secteur services")
- `geo_target` (FR | EU | global)
- `dept_priority` (codes dept FR si applicable, ex: `["92", "75", "59", "69"]` — alimente `workflow_geo.PRIORITY_DEPTS`)
- `city_min_population` (défaut 10000)

**Sortie** : `context/{code}/audience.md`.

---

## Step 4 : Objectifs SEO et liste des principaux concurrents pour Ahrefs et la stratégie de contenu

**Pourquoi** : sert au `brief_agent` pour proposer des articles ciblés (gap analysis), au `seo_strategy_agent` pour mesurer la progression, et au `competitor_analyzer` pour benchmark.

**Inputs** :
- `target_keywords` (3-10 mots-clés stratégiques)
- `competitor_domains` (5-10 concurrents directs, ex: `octopush.com`, `smsmode.com`)
- `traffic_goal_6m` (objectif visites/mois à 6 mois)
- Option : créer le projet Ahrefs Site Audit maintenant ? (Y/N — sinon ça reste à faire dans l'UI Ahrefs)

**Sortie** : `memory/{code}/seo/STRATEGIE.md` + `seed_competitors` ajouté dans `workflow_qualifier.py`.

---

## Step 5 : Ligne éditoriale (ton de voix, CTA standard, mots interdits, signature)

**Pourquoi** : tous les agents d'écriture (editorial_writer, content_agent, linkedin_agent) consomment ce style guide. Garantit la cohérence ton entre tous les contenus.

**Inputs** :
- `tone` (formel | amical | technique | direct | autre)
- `cta_default` (ex: "Réservez un appel de 15 min")
- `banned_words` (liste mots à ne jamais utiliser, ex: "gratuit", "promo", "no-risk")
- `signature` (signature pied de mail, ex: "Camille — LeClientROI")

**Sortie** : `context/{code}/editorial-style.md`.

---

## Step 6 : Secteurs de prospection ciblés et ordre de priorité (parmi les 6 secteurs Genesis)

**Pourquoi** : `god_mode_settings` filtre les secteurs scrapés. L'ordre de priorité conditionne le `daily_quota_per_sector` du `workflow_runner`. Un secteur non listé = jamais scrapé pour ce site.

**Inputs** :
- `sectors_enabled` (parmi `immobilier`, `restaurant`, `garagiste`, `coiffeur`, `retail`, `artisan`)
- Pour chaque secteur, un ordre de priorité 1-N
- `daily_quota_per_sector` (défaut 10, à ajuster selon volume)

**Sortie** : `god_mode_settings` table + `context/{code}/prospection.md`.

---

## Step 7 : Adresse email d'envoi (sender), nom affiché et configuration du compte Gmail/Provider

**Pourquoi** : c'est l'adresse depuis laquelle les emails partent. Doit être connectée à Emelia (provider Gmail/SMTP). Sans elle aucun envoi possible.

**Inputs** :
- `sender_email` (ex: `juliette@leclientroi.com`)
- `sender_name` (ex: "Juliette Assistante")
- `provider_type` (Gmail | Outlook | SMTP custom)
- `emelia_provider_id` (récupéré côté Emelia après connexion du compte Gmail)
- Confirmation : DKIM + SPF + DMARC sont OK côté domaine ? (Y/N, lien doc si non)

**Sortie** : insertion dans `email_senders` (god_mode.duckdb) avec `status=active`.

---

## Step 8 : Pied de mail B2B standard (identité expéditeur + opt-out, posture allégée RGPD)

**Pourquoi** : tout cold email B2B doit afficher l'identité de l'expéditeur + un lien d'opt-out (déjà injecté par Emelia). On reste minimaliste : raison sociale + lien désabo + source. Pas besoin de DPO/SIRET hyper-visible pour le B2B.

**Inputs** :
- `raison_sociale` (ex: "LeClientROI")
- `adresse_postale_courte` (ex: "Paris, France")
- `source_label` (ex: "via votre présence professionnelle publique")
- `privacy_policy_url` (optionnel)
- `dpo_email` (optionnel — ne s'affiche que si renseigné)

**Sortie** : `context/{code}/footer.md` injecté dans tous les templates.

---

## Step 9 : Clés API site-specific (Emelia, Serper, Tally, Telegram bot, webhook tokens)

**Pourquoi** : chaque site a SON compte Emelia/Tally séparé. Ces clés sont privées au site, jamais partagées (sauf Mailnjoy/Ahrefs/DeepSeek = globales).

**Inputs** :
- `EMELIA_API_KEY_{CODE}` (avec lecture seule = NON et autorisation achat = OUI)
- `SERPER_API_KEY_{CODE}` (optionnel si workflow scrape activé)
- `TALLY_WORKSPACE_ID` + `TALLY_API_KEY` (optionnel si Tally activé)
- `TELEGRAM_BOT_TOKEN_{CODE}` + `TELEGRAM_CHAT_ID_{CODE}` (notifications)
- `WEBHOOK_TOKEN_1` + `WEBHOOK_TOKEN_2` (auto-générés 40 chars, pour `/api/emelia/webhook`)

**Sortie** : `.env` enrichi, ou (mieux) table `site_credentials` chiffrée AES-256 par champ.

---

## Step 10 : Templates email initiaux par secteur (3 emails de séquence par template, ou génération IA)

**Pourquoi** : la page Campagnes a besoin d'au moins 1 template par secteur activé pour permettre de lancer une campagne. Sans ça `god_mode_templates` reste vide et le push Emelia échoue.

**Inputs** (par secteur activé en Step 6) :
- Option A : **Coller** subject + body HTML manuellement (3 emails par template = séquence)
- Option B : **Générer via DeepSeek** depuis le persona + secteur + style éditorial (cf. Step 3, 5, 6)
- Option C : **Copier** depuis un site existant (clone template lcr → mkd avec adaptations)

**Sortie** : `god_mode_templates` rows + push initial Emelia via `PATCH /emails/campaigns/{id}/steps` quand la campagne sera créée.

---

## Step 11 : Démarrage du warmup du sender (date J0, plan conservateur A ou agressif B)

**Pourquoi** : un sender neuf ne peut pas envoyer 100 cold emails par jour sans se faire blacklister. Le warmup ramp progressif (cf. specs/warmup-plan.md) est obligatoire.

**Inputs** :
- `warmup_start_date` (défaut : aujourd'hui)
- `warmup_plan` (A = conservateur 10→100/30j | B = agressif 36→10000/30j)
- `daily_max_override` (NULL pour suivre le plan, valeur entière pour forcer un cap manuel)

**Sortie** : insertion `email_senders` avec `warmup_start_date` + état J1.

---

## Step 12 : Activation/désactivation des modules par site (toggles sur 6 modules)

**Pourquoi** : tous les sites n'utilisent pas tous les modules. Désactiver un module = pas de cron, pas d'UI affichée. Économie de coûts et clarté.

**Modules** :
| Module | Description | Cron concerné |
|---|---|---|
| `seo` | Audit Ahrefs + recommendations | ahrefs_daily, monthly_audit, strategy_agent |
| `content` | Génération auto articles | brief_agent, content_agent, linkedin_agent |
| `workflow` | Scrape Serper + push Emelia auto | workflow_runner |
| `tally` | Sync formulaires Tally | tally_to_prm |
| `emelia` | Push manuel via page Campagnes | (manuel via UI) |
| `mailnjoy` | Vérification délivrabilité email | (auto via workflow_runner) |

**Inputs** : 6 booléens (toggles)

**Sortie** : `modules_backend.py` config par site + filtrage automatique sidebar.

---

## Step 13 : Projet Ahrefs Site Audit (création maintenant ou à faire dans l'UI Ahrefs)

**Pourquoi** : sans projet Site Audit, `ahrefs_monthly_audit.py` skippe ce site → pas d'analyse technique (404, redirects, etc.).

**Inputs** :
- Option A : `ahrefs_project_id` (si déjà créé dans l'UI Ahrefs)
- Option B : "à créer manuellement" (lien direct https://app.ahrefs.com/site-audit)

**Sortie** : insertion `ahrefs_monthly_audit.SITES` registry + flag "à créer" si vide.

---

## Step 14 : Quotas quotidiens d'envoi Emelia et délais de cooldown re-push entre 2 campagnes

**Pourquoi** : protège contre les envois sauvages. Limite par cap business (combien on veut envoyer max par jour) et respect du cooldown re-push (un même contact ne peut pas être re-pushé avant N jours).

**Inputs** :
- `emelia_daily_limit` (défaut 50/site, doit être ≤ warmup quota du sender)
- `cooldown_same_site_days` (défaut 7)
- `cooldown_global_days` (défaut 30 — cf. pool mutualisé)

**Sortie** : `god_mode_settings` enrichis.

---

## Step 15 : Compte propriétaire du site (account_id pour la multi-tenant)

**Pourquoi** : Genesis devient une plateforme SaaS où plusieurs comptes (clients) peuvent gérer chacun plusieurs sites. L'account_id identifie le propriétaire facturable.

**Inputs** :
- `account_id` (UUID, ou label du compte)
- `account_role` (owner | admin | viewer pour ce site)
- Quels users existants ont accès à ce site ? (cf. `users.sites` JSON array)

**Sortie** : table `accounts` (à créer) + update `users.sites` + `god_mode_state.account_id` + tous les nouveaux contacts taggés avec `account_id` pour traçabilité dans le pool mutualisé.

---

## Step 16 : Validation finale par envoi d'un email test sur l'email du propriétaire avant déblocage du site en production

**Pourquoi** : avant d'autoriser ce nouveau site à envoyer du cold email à de vrais prospects, on s'assure que toute la chaîne fonctionne. C'est le filet de sécurité qui évite de réaliser après coup qu'un sender mal configuré envoie tout en spam.

**Inputs** :
- `owner_email` (email du propriétaire du compte, rempli à l'inscription)
- Pas d'autre input — on utilise les configs des steps 7 (sender), 8 (footer), 10 (au moins 1 template)

**Mécanique** :
1. Sélection auto du 1er template disponible pour ce site (`god_mode_templates LIMIT 1`)
2. Appel `POST /emails/test {campaignId: <test_campaign_id>, email: owner_email, step: 0}`
3. Attente confirmation user via UI : "J'ai reçu le mail ✓" / "Je n'ai rien reçu ✗"
4. Si reçu → `god_mode_state.enabled = TRUE` pour ce site → débloque tous les crons et features
5. Si rien reçu après 15 min → message d'erreur + lien diagnostic (vérifier sender, DKIM, etc.)

**Sortie** : `god_mode_state.enabled = TRUE` (site activé) OU notification d'échec de validation.

---

## 3. Annexe — Formats DB ciblés (après refonte)

| Table | DB | Inputs onboarding qui la peuplent |
|---|---|---|
| `sites_config` (Python registry) | code | Step 1 |
| `email_senders` | god_mode.duckdb | Steps 7, 11 |
| `god_mode_settings` | god_mode.duckdb | Steps 6, 14 |
| `god_mode_state` | god_mode.duckdb | Step 15 |
| `god_mode_templates` | god_mode.duckdb | Step 10 |
| `accounts` (NOUVELLE) | god_mode.duckdb | Step 15 |
| `site_credentials` (NOUVELLE chiffrée) | god_mode.duckdb | Step 9 |
| `modules_backend` config JSON | `memory/{code}/modules.json` | Step 12 |
| Markdown context | `context/{code}/*.md` | Steps 2, 3, 5, 8 |
| Site Audit Ahrefs registry | `scripts/ahrefs_monthly_audit.py:SITES` | Step 13 |

## 4. Validation user requise

- [ ] Les 15 steps sont-ils exhaustifs (rien d'oublié ?)
- [ ] L'ordre est-il logique (peut-on faire Step 7 avant Step 5 ?)
- [ ] Steps marqués "NON bloquant" peuvent vraiment être skippés à l'init ?
- [ ] Faut-il un Step 16 "Validation test" : envoi d'un email test à un email user avant de débloquer le site en prod ?
