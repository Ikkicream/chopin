---
name: sweego
description: Base de connaissance Sweego (envoi email/SMS, webhooks, tracking, logs, stats) — la doc officielle complète en local + la synthèse de ce qui compte pour Cheffer et Mass Mailing. À lire AVANT toute affirmation ou tout code touchant Sweego.
---

# Sweego — base de connaissance

Doc officielle aspirée le **2026-09-25** depuis https://learn.sweego.io : 63 pages de guide
(les 11 rubriques Auth → Tracking, plus Templates et SDK) et 117 pages de référence d'API.

| Où | Quoi |
| --- | --- |
| `doc/<rubrique>/*.md` | Les guides, un fichier par page, avec l'URL source en tête |
| `doc/api/INDEX.md` | Les 117 endpoints : méthode, chemin, titre, fichier |
| `doc/api/*.api.md` | Chaque endpoint : paramètres, corps (tableau des champs), réponses par code HTTP, exemples |
| `outils/` | Le rendu, pour rafraîchir la doc (voir en bas) |

**Règle** : on cite la page (`doc/...`) pour toute affirmation sur Sweego. Si la doc ne dit rien,
on écrit « non documenté » et on le vérifie par un envoi à blanc (`dry-run`), jamais de supposition.

---

## 1. Envoyer un email — deux routes, pas interchangeables

Source : `doc/sending/how_to_send_email_by_api.md`, `doc/api/send-send-post.api.md`,
`doc/api/send-bulk-email-send-bulk-email-post.api.md`

| | `POST /send` | `POST /send/bulk/email` |
| --- | --- | --- |
| Destinataires | 1 à N | **2 minimum** |
| Avec N destinataires | **UN mail de groupe : chacun voit toutes les adresses dans « À »** | N mails séparés, personne ne voit personne |
| Variables | à la racine, 1 seul destinataire | **dans chaque destinataire** (`recipients[].variables`) |
| CC / BCC | oui (chaque CC/BCC a son `swg_uid`) | non |
| Maximum | « Unlimited » selon la doc | « Unlimited » selon la doc |

➡️ **Envoi de masse = `/send/bulk/email`, toujours.** `/send` sert à 1 destinataire.

Champs communs (`ModelInSendEmail` / bulk) :
- requis : `provider`, `from{email,name}`, `subject`, `recipients`, et au moins un de
  `message-html` / `message-txt` / `template-id` (pas `message-html` ET `template-id`) ;
- `channel` : `"email"` (valeur par défaut dans le schéma) ;
- `provider` : **`"sweego"`** dans tous les exemples de la doc ;
- `campaign-id` (texte libre), `campaign-tags` (≤ 5, `^[A-Za-z0-9-]{1,20}$`),
  `campaign-type` (`market` | `newsletter` | `transac`) ;
- `reply-to` : **un objet** `{email, name?}`, pas une chaîne ;
- `list-unsub` : `{method: "mailto"|"one-click", value}` (voir § 4) ;
- `headers` : 5 en-têtes perso max, le préfixe `X-` est ajouté par Sweego ;
- `dry-run` (rien n'est envoyé), `expires`, `tracking_open` (false = pas de pixel),
  `compress_style`, `force_inline_style`, `attachments` (20 Mo au total).

**Réponse 200 (les deux routes)** — `ModelOutSend` :
```json
{ "transaction_id": "uuid (UN par appel)",
  "swg_uids": { "<destinataire>": "<swg_uid>" },
  "channel": "email", "provider": "...", "credit_left": "..." }
```
➡️ `transaction_id` = l'appel (le lot). `swg_uid` = UN message. Les deux reviennent dans chaque
événement webhook, ce qui permet de rattacher chaque retour à son lot et à son destinataire.

Erreurs (`doc/api_error_codes.md`) : 400 données mal formées, 401, 403 compte restreint,
409 conflit, 413 requête trop grosse, 422 champ manquant ou invalide (dont « headers limités à 5 »),
500 « Unable to send message ». **Aucune limite de débit (429) n'est documentée.**

## 2. Webhooks

Source : `doc/webhooks/*.md`

- Événements email : `email_sent`, `delivered`, `soft-bounce`, `hard_bounce`, `list_unsub`,
  `complaint`, `email_opened` (avec `open.proxy` = vrai/faux), `email_clicked` (`click.url`, `click.proxy`).
- Chaque événement porte : `event_id` (unique, sert à dédoublonner), `swg_uid`, `transaction_id`,
  `recipient`, `campaign_id`, `campaign_type`, `campaign_tags`, `domain_from`, `headers`
  (dont nos en-têtes `x-…`), `details` (ligne du serveur d'envoi), et pour les rebonds `response_code`.
- `campaign_id` vaut **`"default"` si on n'a pas envoyé de `campaign-id`**.
- Délai : immédiat, sauf ouvertures et clics (**jusqu'à 10 min**).
- **Signature** : en-têtes `webhook-id`, `webhook-timestamp`, `webhook-signature` =
  base64(HMAC-SHA256(base64decode(secret), "{id}.{timestamp}.{corps brut}")). Le secret se lit via
  `GET /clients/{uuid_client}/webhooks/{uuid}/secret`.
- Un webhook peut être limité à certains domaines ; sans restriction, il se déclenche pour tous.

## 3. Tracking

Source : `doc/tracking/email_tracking.md`

- S'active **par domaine** (clics et ouvertures), avec un enregistrement DNS `t.<domaine d'envoi>`.
  Même chose par API : `PUT /clients/{uuid}/domains/{uuid}/tracking`.
- Les liens sont réécrits `https://t.<domaine>/t/c/?i=…&u=…`, et un pixel `…/t/o/` est ajouté.
- Lien de désinscription : ajouter **`data-url-type="unsub"`** → `/t/u/`, statut `clicked-unsub`.
  Le webhook de cet événement est annoncé mais pas encore disponible ; il apparaît dans les logs.
- Statuts : `opened-proxy`, `opened-human`, `clicked-proxy`, `clicked-human`, `clicked-unsub`.

## 4. Désinscription (List-Unsubscribe)

Source : `doc/emails/headers/list_unsub.md`, `doc/logs/email/list_unsubscribe.md`

- `mailto` **géré par Sweego** : il fournit une boîte `list-unsub@<domaine d'envoi>`, et le sujet
  doit suivre `Unsubscribe-<client>-<campaign_id>-<message_id>`. Sweego collecte les demandes,
  envoie un webhook `list_unsub` et les met dans un CSV quotidien sur SFTP.
- `one-click` : `"<mailto:…>,<https://…>"`. Sweego ajoute `List-Unsubscribe-Post`, mais **l'URL
  est à nous** : Sweego ne l'enregistre pas et ne nous la renvoie pas.
- Ne jamais envoyer à la fois `list-unsub` ET un en-tête `List-Unsubscribe`
  (sinon il devient `X-List-Unsubscribe`, ce qui ne sert à rien).

## 5. Liste de suppression Sweego

Source : `doc/emails/suppression_list.md`

Un rebond dur « user unknown » bloque l'adresse **90 jours**, avant même toute tentative
(`DROP[suppressed]` dans les logs). **Cette liste n'est ni consultable ni exportable**, ni par
l'app ni par l'API. Il faut donc tenir notre propre liste de suppression.

## 6. Logs et statistiques (réconciliation)

Source : `doc/logs/email/sending.md`, `doc/api/logs-logs-post.api.md`, `doc/api/stats-stats-post.api.md`

- `GET /logs/{swg_uid}` (fiche complète) et `GET /logs/{swg_uid}/status` (statut seul, le moins coûteux).
- `POST /logs` avec `channel: "email"` et les filtres `transaction_id`, `campaign-tags`,
  `campaign-type`, `status[]`, `domains[]`, `msp[]`, `search_word` (swg_uid ou adresse),
  `start_date`/`end_date`, `size` ≤ 500, `offset`.
  ➡️ **Filtrer par `transaction_id` = relire tout un lot**, sans webhook.
- Statuts, cumulatifs : `queued` → `delivered` | `undelivered` → `opened-*` → `clicked-*`.
  Filtrer sur `delivered` seul exclut donc les messages déjà ouverts.
- `POST /stats` : agrégats par dates, domaines et messagerie (pas par campagne).
  Métriques : sent, accepted, rejected, bounced (hard/soft), complaints, list_unsubscribe.
- Rétention selon l'abonnement. Export quotidien par SFTP (`report.YYYY-MM-DD.csv.gz`,
  `fbl.*.csv` pour les plaintes, `list-unsub.*.csv`), mais **l'accès SFTP se demande au support**.
- `GET /clients/{uuid}/logs/audit` : journal des changements de configuration.

## 7. Domaine et authentification

Source : `doc/auth/sender_authentication.md`, `doc/emails/verify_an_email_domain.md`

Sous-domaine d'envoi **obligatoire**, avec 2 CNAME obligatoires (SPF/Return-Path et DKIM 2048)
et un DMARC recommandé (Gmail et Yahoo l'exigent au-delà de 5 000 mails par jour).
Un domaine non vérifié ne peut pas envoyer.
Auth API : en-tête `Api-Key: …` (valable pour `send/*`, `logs/*`, `stats/*`, `client/*`).

## 8. SMS (pour mémoire)

Source : `doc/sending/how_to_send_sms_by_api.md`, `doc/sms/*.md`

`/send` avec `channel: "sms"` : chaque destinataire reçoit **son propre** SMS (contrairement à
l'email). `campaign-type` est obligatoire (`transac`/`market`). « STOP » est ajouté
automatiquement en France pour `market`. 160 caractères, ou 70 avec des accents ou emojis.

---

## Écarts entre notre code et la doc (relevés le 2026-09-25)

| # | Où | Écart | Gravité |
| --- | --- | --- | --- |
| 1 | `scripts/sweego_backend.py` `send_campaign` | `/send` avec N adresses = **mail de groupe, adresses visibles** | 🔴 à corriger (décision de Camille en attente) |
| 2 | `scripts/sweego_backend.py` + `mass_mailing/infra/sweego.py` | `"provider": "email"` alors que la doc met `"sweego"`. Les envois de Cheffer passent pourtant : Sweego tolère peut-être cette valeur | 🟠 à vérifier par dry-run |
| 3 | `mass_mailing/infra/sweego.py` | `reply-to` envoyé en **chaîne**, alors que le schéma attend un objet `{email}` | 🟠 à corriger avant le 1er envoi |
| 4 | `mass_mailing/infra/sweego.py` | aucun `list-unsub` : pas de bouton de désinscription natif dans Gmail et Outlook | 🟠 à ajouter |
| — | `mass_mailing/infra/sweego.py` | passage à `/send/bulk/email` dès 2 destinataires | ✅ fait le 2026-09-25 |

## Rafraîchir la doc

```bash
cd outils
curl -sL https://learn.sweego.io/docs/intro -o p.html   # repérer main.*.js et runtime~main.*.js
# télécharger main.js et rt.js, régénérer pages.json (clé de chunk → fichier source), puis :
node aspire.mjs /tmp/sweego_doc && python3 nettoie.py /tmp/sweego_doc
```
Le site est rendu en JavaScript (Docusaurus) : WebFetch et curl sur les pages ne voient qu'une
page vide. `aspire.mjs` exécute chaque page compilée avec un faux React, puis `nettoie.py`
transforme les schémas OpenAPI en tableaux.
