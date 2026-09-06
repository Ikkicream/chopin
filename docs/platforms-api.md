# Plateformes d'envoi email — doc interne (2026-06-23)

Trois routes d'envoi selon le type de campagne. Ne pas mélanger.

| Plateforme | Usage | Limite | Route dans le code |
|---|---|---|---|
| **Emelia** | Cold email — commerciaux | 30 emails/j | `emelia_campaign_manager.py` |
| **Maildoso** | Cold email acquisition — séquenceur maison | 300 emails/j (4 boîtes × ~40/j ramp-up) | `cold_email_engine.py` *(à construire)* |
| **Sweego** | Campagnes masse (newsletter, annonce) | crédits (pas de limite/j fixe) | `sweego_backend.py` |

---

## 1. Emelia — cold email commerciaux

### Auth
Header : `Authorization: <clé>` (**sans** préfixe Bearer pour REST, **avec** Bearer pour GraphQL).

Variables d'env : `EMELIA_API_KEY` (global) ou `EMELIA_API_KEY_LCR` / `EMELIA_API_KEY_MKD` (par site).

### Endpoints REST `https://api.emelia.io`

| Méthode | Path | Notes |
|---|---|---|
| `GET` | `/emails/campaigns` | liste ; `_id`, `name`, `status` |
| `POST` | `/emails/campaigns` | `{name}` — création |
| `PATCH` | `/emails/campaigns/{id}/steps` | `{steps:[…]}` ; pause obligatoire si RUNNING |
| `POST` | `/emails/campaigns/{id}/start` | démarre |
| `POST` | `/emails/campaign/contacts` | ⚠️ **singulier**. `{id, contact:{email, firstName, lastName, field1..4}}` |
| `POST` | `/emails/test` | BAT : `{campaignId, email, step}` |
| `GET` | `/webhook` | liste les webhooks enregistrés |

Voir `docs/emelia-api.md` pour la carte complète, les pièges et les requêtes GraphQL.

### Format des tags (variables de personnalisation)
```
{{firstName}}   {{lastName}}   {{company}}   {{field1}}   {{field2}}   {{field3}}   {{field4}}
```
Spintax Emelia : non supporté — le spintax reste côté Genesis, résolu AVANT d'envoyer à l'API.

### Steps (format)
```python
{
  "delay": {"amount": 3, "unit": "DAYS"},  # ou MINUTES pour l'étape 0
  "versions": [{
    "subject": "Objet {{firstName}}",
    "disabled": False,
    "message": "<p>HTML ici {{field1}}</p>",
    "rawHtml": True,
    "attachments": []
  }]
}
```

### Séquence standard (4 touches, approche setting)
- **J0** : ouverture conversation, zéro pitch
- **J+3** : demande de permission (même thread `Re:`)
- **J+3** : question qualifiante (même thread)
- **J+4** : interview post-perte (même thread)

Voir `routeur_doc/coldemail.md` pour le copy complet avec spintax.

### Click → lead (Emelia)
`emelia_to_crm.py` tourne chaque soir à 19h UTC et consulte l'API GraphQL :
- `hasClicked` → `prm` (si état < prm)
- `hasReplied` → `lead` (si état < lead)
- `hasBounced` ou `hasUnsubscribed` → `blacklisted`
- `hasOpened` → horodate `emelia_opened_at` sans changer l'état

Endpoint CRM interne : `acquisition_backend.py` → `data/crm/{site}.duckdb`.

---

## 2. Sweego — campagnes masse

### Auth
Header : `Api-Key: <clé>`

Variables d'env :
```
SWEEGO_API_KEY=282c1419-4ccb-4a80-8b25-f2b7adc491e4
SWEEGO_DOMAIN=news.leclientroi.email
```

### Endpoint d'envoi
```
POST https://api.sweego.io/send
```

**Payload requis (email) :**
```python
{
    "provider": "email",               # ⚠️ TOUJOURS "email", pas "sweego"
    "campaign-type": "market",         # "market" (marketing) ou "transac" (transactionnel)
    "campaign-id": "lcr-immo-juin",   # identifiant libre pour tracking
    "subject": "Sujet de l'email",
    "from": {"email": "news@leclientroi.com", "name": "Le Client ROI"},
    "recipients": [
        {"email": "contact@agence.com"},
        # Personnalisation : ajouter les variables comme champs extra du recipient
        {"email": "autre@agence.com", "firstName": "Jean", "company": "Agence Paris"}
    ],
    "message-html": "<p>Votre HTML ici</p>",
    "message-txt": "Version texte brut",
    "dry-run": True    # True = validation sans envoi
}
```

**Champs interdits / ne pas mettre :**
- Pas de champ `"channel"` dans la requête (il est dans la *réponse*)
- Pas de `"campaign-type": "newsletter"` — ça n'existe pas

**Réponse succès :**
```json
{
    "channel": "email",
    "provider": "email",
    "swg_uids": {"contact@agence.com": "02-xxxx-yyyy"},
    "transaction_id": "73c9d591-67e2-486d-b533-af7f6e74793b"
}
```

### Domaines expéditeur autorisés (vérifiés par test)
| Domaine | Statut |
|---|---|
| `leclientroi.com` | ✅ **Seul domaine fonctionnel** (DKIM/SPF/DMARC OK, MTA via `swg.leclientroi.com`) |
| `news.leclientroi.email` | ❌ NE FONCTIONNE PAS — Sweego accepte l'envoi mais l'email part dans le vide (pas de `swg.news.leclientroi.email` dans l'infra DNS Sweego). Vérifié : 0 email reçu. |
| `leclientroi.email` | ❌ Unauthorized |
| `notification.leclientroi.fr` | ❌ Non autorisé |

> **Règle absolue** : `SWEEGO_DOMAIN=leclientroi.com` uniquement. Détails dans `docs/infrastructure.md`.

### Personnalisation
Sweego substitue les `{{variable}}` si le champ correspondant est présent dans l'objet recipient.
Pour une newsletter sans personnalisation : supprimer les `{{variable}}` du HTML avant envoi
(`clean_html_for_sweego()` dans `sweego_backend.py`).

### Stats
```
POST https://api.sweego.io/stats/msp
Body: {"channel": "email"}   # optionnel
```
Retourne par MSP (gmail, microsoft, yahoo_eu, laposte, sfr, orange, default) :
`sent`, `accepted`, `bounced`, `hardbounce`, `softbounce`, `complaints`, `rejected`, `undelivered`

`POST /stats` avec `{channel: "sms"}` → retourne `result: [{...}]` par jour (email stats via /stats/msp seulement).

### Click → lead (Sweego)

> ⚠️ Correction 2026-06-24 : une version précédente de cette doc affirmait « pas de webhook natif ».
> **C'était faux.** Sweego A un webhook par destinataire. Deux mécanismes coexistent maintenant :

**A. Lien de tracking maison — ✅ EN PROD, testé bout-en-bout (2026-06-24)**
Pour chaque destinataire on génère un token et le lien pointe vers un endpoint Genesis public :
```
GET https://api.cheffer.email/api/sweego/click?t=<token>
```
- `sweego_backend.make_click_token(site, email, campaign_id, dest_url)` → stocke le mapping dans
  la table `sweego_click_tokens` (god_mode.duckdb) et renvoie le token.
- L'endpoint `GET /api/sweego/click` (public — exception dans le middleware d'auth) :
  résout le token → promeut le contact en `prm` (`acquisition_backend.create(..., skip_validation=True)`)
  → redirige (302) vers `dest_url`.
- **`skip_validation=True` obligatoire** : un cliqueur est réel par définition. Sans ça, la vérif
  Mailnjoy synchrone (a) bloque la redirection ~10s et (b) peut rejeter le contact (ex.
  `camille@leclientroi.com` classé *risky*).
- Indépendant de Sweego : marche même sans webhook enregistré.

**B. Webhook natif Sweego — RÉCEPTEUR PRÊT, enregistrement à faire**
Sweego POST un event par destinataire (doc : learn.sweego.io/docs/webhooks/email_events) :
```
event_type ∈ email_sent, delivered, soft-bounce, hard_bounce, list_unsub,
             complaint, email_opened, email_clicked
champs clés : recipient (email), campaign_id, campaign_type, click.url, open.proxy
```
- Récepteur : `POST /api/sweego/webhook?token=<WEBHOOK_TOKEN_1>` (déjà codé dans `api.py`).
  Mapping : `email_clicked`→`prm` ; `hard_bounce`/`list_unsub`/`complaint`→`blacklisted` ;
  `email_opened` (humain)→horodatage ; reste→ignoré. Events bruts loggés dans `sweego_events`.
- **Enregistrement** : route `POST /clients/{uuid_client}/webhooks` (scopée client).
  ⚠️ L'UUID client n'est PAS récupérable via l'API avec la seule clé — il vient du **dashboard
  Sweego** (paramètres/compte) ou de l'en-tête `x-client-id` d'un email reçu. **À fournir** pour
  activer ce canal (captera alors aussi les clics sur les liens normaux, sans api.cheffer.email).

---

## 3. Maildoso — séquenceur custom (warmup en cours, disponible J+14)

### Infra
Pure SMTP/IMAP. Maildoso ne fait **que** l'hébergement + warmup. Toute la logique d'envoi est maison.

| | |
|---|---|
| **SMTP** | `smtp.maildoso.com:587` (STARTTLS) |
| **IMAP** | `imap.horus.maildoso.com:993` (SSL) |

### Boîtes disponibles (warmup jusqu'à ~J+14 depuis 2026-06-23)
| Email | Prénom | Nom | Password |
|---|---|---|---|
| j.durand@leclient-roi.com | Juliette | Durand | `VfQ3EmMkB7IoLf` |
| j.bernard@leclient-roi.com | Juliette | Bernard | `VfQ3EmMkB7IoLf` |
| j.juste@leclient-roi.com | Juliette | Juste | `VfQ3EmMkB7IoLf` |
| j.nguyen@leclient-roi.com | Juliette | Nguyen | `VfQ3EmMkB7IoLf` |

⚠️ **Ne jamais hardcoder le mot de passe dans le code.** Lire depuis `.env` (`MAILDOSO_PASS`).
⚠️ **Aucun envoi cold tant qu'une boîte n'est pas `active`** (warmup terminé, score Maildoso ≥ 80).

### Format des tags
Spintax (résolu côté Genesis) :
```
{option a|option b|option c}      # choix aléatoire à chaque envoi
{{prénom}}                         # variable prospect
{{entreprise}}   {{ville}}   {{secteur}}   {{prénom_expéditeur}}
```

Resolver Python (dans `cold-email-engine.md`) :
```python
import random, re
def spin(text):
    pattern = re.compile(r'\{([^{}]*)\}')
    while True:
        m = pattern.search(text)
        if not m: return text
        choice = random.choice(m.group(1).split('|'))
        text = text[:m.start()] + choice + text[m.end():]
```

### Séquence (4 touches, texte brut uniquement)
- **J0** : Email 1, objet `{petite question {{ville}}|question rapide}`
- **J+3** : Relance 1 (même thread `Re:`), demande de permission
- **J+3** : Relance 2 (même thread `Re:`), question qualifiante
- **J+4** : Relance 3 (même thread `Re:`), interview post-perte

Séquence complète avec spintax : `routeur_doc/coldemail.md`.
Spécification technique du séquenceur : `routeur_doc/cold-email-engine.md`.

### Architecture du séquenceur (à construire)
- `data/maildoso.sqlite` → tables `mailboxes`, `prospects`, `campaigns`, `sequence_steps`, `enrollments`, `messages_sent`, `events`, `suppression`
- PM2 : `maildoso-engine` (envoi, tick toutes les 30-180s) + `maildoso-poller` (IMAP, toutes les 5-10min)
- Heures ouvrées : lun-ven, 9h-18h Europe/Paris uniquement
- Ramp-up : S1→10/j, S2→20/j, S3→30/j, plafond 40/j par boîte
- Kill-switch : bounce rate > 3% par boîte → pause ; > 5% global → tout pause

### Click → lead (Maildoso)
Les emails sont texte brut donc pas de pixel. L'unique signal disponible est la **réponse IMAP**.
Transitions :
- `reply` → lead + suppression list (arrêt séquence)
- `unsubscribe` (mot-clé dans corps) → blacklisted + suppression list
- `bounce` → blacklisted + suppression list

---

## 4. Tags et variables — récapitulatif comparatif

| Plateforme | Format variable | Spintax | Résolution |
|---|---|---|---|
| Emelia | `{{firstName}}` `{{field1}}` | non | Côté Emelia à l'envoi |
| Sweego | `{{firstName}}` `{{company}}` | non | Côté Sweego si champ dans recipient |
| Maildoso | `{{prénom}}` `{{entreprise}}` | `{a\|b\|c}` | Côté Genesis (spin + interp) avant SMTP |

---

## 5. Click → lead — pipeline unifié

Objectif : toute personne cliquant dans un email (sauf le lien de désinscription) doit apparaître
dans `/site/lcr/acquisition` en état `prm` minimum.

| Plateforme | Mécanisme actuel | Status |
|---|---|---|
| Emelia | `emelia_to_crm.py` cron 19h + `POST /api/emelia/webhook` → `hasClicked`/`clicked` → `prm` | ✅ Actif |
| Sweego (lien maison) | `GET /api/sweego/click?t=<token>` → `prm` → redirect | ✅ Actif, testé en réel 2026-06-24 |
| Sweego (webhook natif) | `POST /api/sweego/webhook` → `email_clicked` → `prm` | 🟡 Récepteur prêt, manque UUID client pour enregistrer |
| Maildoso | IMAP reply uniquement (texte brut, pas de lien trackable) | ⬜ Prévu dans poller |

Endpoint d'arrivée pour tous : `acquisition_backend.create(..., skip_validation=True)` ou
`change_state()` → `data/crm/{site}.duckdb`. Les signaux d'engagement (clic/réponse) sautent la vérif
Mailnjoy (le contact a déjà interagi → il est réel).

---

## 5bis. Cadence & délivrabilité (agent + scheduler)

Les campagnes du **hub** (`/site/{site}/campaigns`) sont planifiées et étalées par un scheduler, sous
le contrôle d'un agent délivrabilité à **règles dures** (jamais dépassées) + explication IA.

### Plafonds d'envoi/jour par canal (`deliverability_agent.DAILY_CAP`, validés user 2026-06-24)
| Canal | Cap/jour | Fenêtre max | Au-delà |
|---|---|---|---|
| Emelia | **30/j** | 30 j (≈900) | → suggère Sweego |
| Sweego | **1000/j** | 60 j (≈60k) | → réduire / étaler |
| Maildoso | **300/j** | 60 j (≈18k) | → suggère Sweego (canal désactivé jusqu'au ~07/07) |

Caps **plats** (pas de ramp). Au-delà de la fenêtre → `feasible=false` + canal suggéré.
Exemples vérifiés : Emelia 30k → refus + Sweego ; Sweego 30k → étalé 30 j ; Maildoso 900 → 3 j.

### Modèle & scheduler (`campaign_engine.py`)
- Table `campaigns_unified` (god_mode.duckdb) : canal, message, secteurs, cible, `schedule_start`,
  `cadence` (planning jour/jour), statut, `sent_count`.
- `dispatch_due(today)` — cron quotidien **8h30** (`run_agent.sh scripts/campaign_engine.py dispatch`) :
  pour chaque campagne due, pioche le lot du jour (`pick_for_campaign`, Mailnjoy valid < 6 mois),
  envoie via le canal, incrémente `sent_count`, passe `done` à la cible atteinte. Idempotent/jour.
- Cible : `count_available_for_sector` / `pick_for_campaign` filtrent désormais **Mailnjoy valid ET
  `checked_at` < 180 jours** (param `cleaned_within_days`, défaut 180).

## 6. Fichiers clés

| Fichier | Rôle |
|---|---|
| `scripts/emelia_campaign_manager.py` | Création + configuration campagnes Emelia |
| `scripts/emelia_to_crm.py` | Sync click/reply Emelia → acquisition (cron 19h) |
| `scripts/sweego_backend.py` | Envoi masse + stats + engagement + tokens de clic (`make_click_token`/`resolve_click`) |
| `scripts/api.py` | Endpoints `GET /api/sweego/click` (lien tracké) + `POST /api/sweego/webhook` (récepteur natif) + `GET /api/sweego/engagement` |
| `scripts/acquisition_backend.py` | Storage unifié des leads (cold_email→prm→lead→crm), `create(skip_validation=…)` |
| `scripts/campaign_engine.py` | Modèle de campagne unifié + scheduler (`dispatch_due`, cron 8h30) |
| `scripts/deliverability_agent.py` | Caps par canal + planning de cadence + explication IA |
| `genesis-ui/.../campaign-wizard.tsx` | Wizard 5 étapes (canal→message→cible→aperçu→planning) |
| `genesis-ui/.../channel-perf-card.tsx` | Carte stats par canal (Emelia vs Sweego), réutilisée dashboard + hub |
| `routeur_doc/cold-email-engine.md` | Spec complète du séquenceur Maildoso |
| `routeur_doc/coldemail.md` | Copywriting + séquence 4 touches |
| `routeur_doc/accounts_maildoso.csv` | Identifiants SMTP/IMAP des 4 boîtes |
| `docs/emelia-api.md` | Carte API Emelia vérifiée (REST + GraphQL) |
