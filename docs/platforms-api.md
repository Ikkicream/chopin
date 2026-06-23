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
| `leclientroi.com` | ✅ Autorisé |
| `news.leclientroi.email` | ✅ Autorisé |
| `leclientroi.email` | ❌ Unauthorized |
| `notification.leclientroi.fr` | ❌ Non autorisé |

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
Pas encore de webhook natif découvert. Deux approches possibles :
1. **Polling `/stats/msp`** + tracking UTM (le lien contient `utm_source=sweego&utm_campaign=ID`) → détecter les clics UTM dans les logs Apache/nginx → pousser vers acquisition
2. **Pixel de tracking** Sweego (à explorer dans le dashboard) → webhook vers `/api/sweego/webhook`

**À implémenter** : un endpoint `/api/sweego/webhook` ou un cron de polling UTM qui pousse les cliqueurs vers `acquisition_backend.create()` avec `state=prm`.

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
| Emelia | `emelia_to_crm.py` cron 19h → `hasClicked` → `prm` | ✅ Actif |
| Sweego | UTM tracking (`utm_source=sweego`) → à capter côté site/webhook | ⬜ À faire |
| Maildoso | IMAP reply uniquement (texte brut, pas de lien trackable) | ⬜ Prévu dans poller |

Endpoint d'arrivée pour tous : `acquisition_backend.create()` ou `change_state()` → `data/crm/{site}.duckdb`.

---

## 6. Fichiers clés

| Fichier | Rôle |
|---|---|
| `scripts/emelia_campaign_manager.py` | Création + configuration campagnes Emelia |
| `scripts/emelia_to_crm.py` | Sync click/reply Emelia → acquisition (cron 19h) |
| `scripts/sweego_backend.py` | Envoi masse + stats Sweego |
| `scripts/acquisition_backend.py` | Storage unifié des leads (cold_email→prm→lead→crm) |
| `routeur_doc/cold-email-engine.md` | Spec complète du séquenceur Maildoso |
| `routeur_doc/coldemail.md` | Copywriting + séquence 4 touches |
| `routeur_doc/accounts_maildoso.csv` | Identifiants SMTP/IMAP des 4 boîtes |
| `docs/emelia-api.md` | Carte API Emelia vérifiée (REST + GraphQL) |
