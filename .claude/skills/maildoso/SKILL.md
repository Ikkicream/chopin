---
name: maildoso
description: Connecteur Maildoso (cold email maison, canal "maildoso" de Cheffer) — API REST d'infra + envoi SMTP. Utiliser pour tout ce qui touche aux boîtes @leclient-roi.com, au canal maildoso, à l'envoi SMTP maison ou à l'API developers.maildoso.com.
---

# Maildoso — connecteur cold email maison (canal `maildoso` de Cheffer)

## Vue d'ensemble — le point crucial

**L'API REST Maildoso NE FAIT PAS d'envoi d'email.** Elle gère uniquement l'infrastructure
(domaines, boîtes, warmup, forwarding, stats, export vers séquenceurs tiers).
**L'envoi se fait en SMTP direct** avec les credentials de chaque boîte :

- SMTP : `smtp.maildoso.com:587` (STARTTLS), login = adresse email complète
- IMAP : `imap.horus.maildoso.com:993` (SSL) — pour lire réponses/bounces
- Les réponses sont aussi agrégées sur la boîte de forwarding `leclientroi@maildoso.email`

Côté code : module `scripts/maildoso_backend.py` (BigMatch), boîtes en table `mailboxes`
dans `data/god_mode.duckdb`, secrets dans `.env`.

## Compte & infra (état au 2026-07-07)

- Compte : `camille@leclientroi.com` (user_id **8830**)
- Domaine d'envoi : **leclient-roi.com** (avec tiret ! ≠ leclientroi.com utilisé par Emelia/Sweego),
  domain_id 268736, ACTIVE depuis le 23/06/2026, redirect → https://leclientroi.com, tracking GCDT activé
- 4 boîtes actives (créées 23/06/2026, warmup ~2 semaines, réputation Microsoft "high") :
  | account_id | email | expéditeur |
  |---|---|---|
  | 1223461 | j.durand@leclient-roi.com | Juliette Durand |
  | 1223462 | j.juste@leclient-roi.com | Juliette Juste |
  | 1223463 | j.bernard@leclient-roi.com | Juliette Bernard |
  | 1223464 | j.nguyen@leclient-roi.com | Juliette Nguyen |
- Forwarding commun : `leclientroi@maildoso.email` (id 8677)
- ⚠️ Domaine jeune : rester prudent sur le volume (ramp-up ~10→40/jour/boîte, cf.
  `routeur_doc/cold-email-engine.md`), même si `deliverability_agent.py` autorise 300/jour.

## Secrets (`/home/autoblog/genesis/.env`)

- `MAILDOSO_API_TOKEN` — PAT de l'API REST (préfixe `pat_`, généré dans Settings → API Keys)
- `MAILDOSO_SMTP_PASSWORD` — mot de passe SMTP/IMAP (identique pour les 4 boîtes)

Ne jamais écrire ces valeurs en dur dans le code ou les docs. Le mot de passe est aussi
retourné en clair par `GET /v1/user/accounts-lookup` (champ `password`) si besoin de le récupérer.

## API REST

- Base URL : `https://api.maildoso.com`
- Auth : header `Authorization: Bearer <PAT>` (même token pour l'API et le serveur MCP `https://mcp.maildoso.com/mcp`)
- OpenAPI complet : `https://developers.maildoso.com/openapi.json` (copie locale : `openapi.json` à côté de ce skill)
- Doc humaine : https://developers.maildoso.com/

### Endpoints utiles (testés le 2026-07-07)

**Vérifier la connexion**
```
GET /v1/user/me
→ {"id":8830,"email":"camille@leclientroi.com","is_gcdt_enabled":true,"is_blocked":false,...}
```

**Lister les boîtes (avec creds SMTP/IMAP !)**
```
GET /v1/user/accounts-lookup            # params: limit, offset, keyword, status[], provider[]...
→ {"items":[{"id":1223461,"email_account":"j.durand@leclient-roi.com","is_active":true,
   "password":"<smtp/imap pass>","first_name":"Juliette","last_name":"Durand",
   "imap":{"imap_host":"imap.horus.maildoso.com","port":993},
   "forwarding_account":{"email":"leclientroi@maildoso.email"},
   "reputation_test":{"google_score":"unmeasured","microsoft_score":"high"},
   "status":"active",...}], "meta":{"total":4}}
```

**Quotas / usage**
```
GET /v1/user/stats
→ {"domains":{"total":1,"in_use":1},"maildoso_accounts":{"total":10,"in_use":4},
   "warmups":{"total":0,"in_use":0},...}
```
→ Marge dispo : 10 boîtes payées, 4 utilisées → on peut provisionner 6 boîtes de plus sans surcoût.

**Domaines**
```
GET  /v1/user/domains                    # filtres: keyword, ids, domain_type, provider
POST /v1/user/domains                    # body: {"domains":[...], "redirect_to":[...]}
PUT  /v1/user/domains                    # settings (redirect, tracking...)
POST /v1/user/domains/search             # recherche de domaines à acheter
PUT  /v1/user/domains/tracking           # activer/désactiver GCDT (custom domain tracking)
POST /v1/user/domains/external           # brancher un domaine externe
POST /v1/user/domains/restart-setup
GET  /v1/user/domains/provider-availability
```

**Boîtes email**
```
POST   /v1/user/accounts                 # body: [EmailAccountInsert, ...] — provisionner
DELETE /v1/user/accounts                 # body: [account_id, ...]
PUT    /v1/user/accounts/{account_id}    # body: {password?, first_name?, last_name?, forwarding_account_id?, is_premium_warmup?...}
GET    /v1/user/accounts/{account_id}/totp
GET    /v1/user/accounts/forwarding      # + PUT pour changer l'adresse de forwarding
```

**Forwarding**
```
GET    /v1/user/forwarding-lookup
POST   /v1/user/forwarding               # créer une adresse @maildoso.email
DELETE /v1/user/forwarding
POST   /v1/user/forwarding/password      # reset du mot de passe
```

**Warmup** (service optionnel Maildoso — actuellement 0 actif, le warmup initial des 4 boîtes est fini)
```
GET/POST/PUT /v1/user/services/warmups   # body: [WarmupServiceRequest, ...]
DELETE       /v1/user/services/warmups/{id}
```

**Séquenceurs tiers** (Instantly, Smartlead, Saleshandy — pas utilisés : notre séquenceur est maison)
```
GET/POST/PUT /v1/sequencers
POST         /v1/sequencers/export       # body: {"sequencer_id", "account_ids":[...]}
```

**Divers** : `GET /v1/user/settings`, `GET/POST/PATCH /v1/user/data`,
`POST /v1/user/regenerate_auth_pat` (⚠️ invalide le token courant), `GET /v1/billing/pricing`.

### Exemple curl

```bash
source /home/autoblog/genesis/.env 2>/dev/null || true
curl -s -H "Authorization: Bearer $MAILDOSO_API_TOKEN" https://api.maildoso.com/v1/user/me
```

## Envoi SMTP (le vrai canal d'envoi)

```python
import os, smtplib
from email.message import EmailMessage

msg = EmailMessage()
msg["From"] = "Juliette Durand <j.durand@leclient-roi.com>"
msg["To"] = "prospect@example.com"
msg["Subject"] = "sujet"
msg.set_content("texte brut")                      # cold email = plain text de préférence

with smtplib.SMTP("smtp.maildoso.com", 587, timeout=30) as s:
    s.starttls()
    s.login("j.durand@leclient-roi.com", os.environ["MAILDOSO_SMTP_PASSWORD"])
    s.send_message(msg)
```

Préférer `scripts/maildoso_backend.py` qui gère rotation des boîtes, caps et journalisation.

## Ramp-up automatique des caps

`scripts/maildoso_ramp.py` ajuste le `daily_cap` de chaque boîte **après chaque campagne
dispatchée** (hook en fin de `campaign_engine._send_batch`, idempotent 1×/boîte/jour,
log dans `maildoso_ramp_log`). Règle (fenêtre 3 jours sur `maildoso_sent`) :
- \>10 % d'erreurs SMTP → cap −10 (plancher 10)
- 0 erreur et dernier jour actif ≥ 60 % du cap → cap +5 (plafond 40)
- sinon inchangé

Le cap CANAL est dynamique : `deliverability_agent` somme les caps des boîtes actives,
et `/api/sites/{site}/channels` expose `mailboxes`, `per_mailbox_cap`, `remaining_today`
(affichés sur la card du campaign-wizard). CLI : `python3 scripts/maildoso_ramp.py status|run`.

⚠️ Remise différée : Maildoso met ~20 min à délivrer après acceptation SMTP (file
d'attente sortante). Un « rien reçu » immédiat est normal.

## Ce que fait vraiment le relais sortant (constaté au mail-tester du 2026-07-07, score 7.5/10)

- IP de sortie ≠ smtp.maildoso.com : pool `spf.pinkproof.net` (ex. 169.255.56.72,
  HELO/rDNS générique type `*.pinkrooffour.top`). Aucune des 23 blocklists IP ne les liste.
- **SPF pass, DKIM pass** (signé par le relais : `d=leclient-roi.com; s=out401500`, RSA 2048),
  **DMARC pass** malgré `p=reject` → l'authentification est entièrement gérée par Maildoso, ne rien signer nous-mêmes.
- ⚠️ **Le relais RÉÉCRIT le message** (tracking GCDT actif sur le domaine) : un envoi text/plain
  ressort en **text/html seul** (paragraphes convertis en `<p>`, sans balise `<html>`), et notre
  header `List-Unsubscribe` est **supprimé**. Pénalités SpamAssassin mineures (MIME_HTML_ONLY,
  HTML_MIME_NO_HTML_TAG). Pour du plain text pur : désactiver le tracking via
  `PUT /v1/user/domains/tracking`.
- ⚠️ **`leclient-roi.com` est listé sur ABUSE SURBL** (URIBL_ABUSE_SURBL, −1.9 pts — la plus
  grosse pénalité). Classique pour un domaine récent : demander le délisting sur surbl.org
  et re-tester. À surveiller.

## Intégration BigMatch/Cheffer

- Canal `maildoso` déclaré dans `campaign_engine.py` (`VALID_CHANNELS`), branch d'envoi dans `_send_batch`
- Caps : `deliverability_agent.py` (`DAILY_CAP["maildoso"]`, `MAX_DAYS["maildoso"]`)
- Exposé à l'UI Cheffer via `GET /api/sites/{site}/channels` (`api.py`) — le campaign-wizard
  de genesis-ui rend le canal automatiquement
- Boîtes : table `mailboxes` de `god_mode.duckdb` (source historique : `routeur_doc/accounts_maildoso.csv`)
- Spec complète du séquenceur maison : `routeur_doc/cold-email-engine.md`
