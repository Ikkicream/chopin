# Infrastructure email — LeClientROI (2026-06-24)

Vue d'ensemble des domaines, DNS et infra d'envoi. Mettre à jour dès qu'un domaine ou une
configuration change.

---

## Domaines

| Domaine | Usage | MX / Provider |
|---|---|---|
| `leclientroi.com` | Site principal + expéditeur email | Google Workspace (`smtp.google.com`) |
| `leclientroi.email` | Domaine secondaire | — |
| `news.leclientroi.email` | ~~Ancien expéditeur Sweego~~ ❌ non configuré chez Sweego | Cloudflare Email Routing |
| `swg.leclientroi.com` | Sous-domaine géré par Sweego (bounce/MTA) | Sweego infrastructure |
| `leclient-roi.com` | Domaine Maildoso (boîtes warmup) | Maildoso (`imap.horus.maildoso.com`) |

---

## Sweego — comment ça marche vraiment

Sweego **ne passe pas par le domaine expéditeur** pour router les emails. Il utilise sa propre
infrastructure MTA et forge l'enveloppe SMTP sur un sous-domaine qu'il contrôle :

```
Header From  (visible destinataire) : info@leclientroi.com
Return-Path  (envelope / bounce)    : ...@swg.leclientroi.com   ← Sweego MTA
SMTP sending IP                     : 185.255.28.17 (prod-mta-12.swg-srv.net)
```

### Authentification vérifiée (enveloppe réelle du 2026-06-24)
| Check | Résultat |
|---|---|
| DKIM | ✅ pass — `leclientroi.com`, sélecteur `selector1` |
| SPF | ✅ pass — IP 185.255.28.17 autorisée via `swg.leclientroi.com` |
| DMARC | ✅ pass — politique `p=REJECT sp=REJECT` (la plus stricte) |

### Domaine expéditeur — règle absolue
**Utiliser uniquement `leclientroi.com`** comme domaine dans `SWEEGO_DOMAIN`.

`news.leclientroi.email` ne fonctionne pas : Sweego n'a pas `swg.news.leclientroi.email`
configuré dans son infrastructure DNS. L'email part dans le vide.

### Configuration dans le projet
```
# .env
SWEEGO_API_KEY=282c1419-4ccb-4a80-8b25-f2b7adc491e4
SWEEGO_DOMAIN=leclientroi.com

# → expéditeur généré par sweego_backend._from() :
# {"email": "info@leclientroi.com", "name": "Le Client ROI"}
```

### Endpoint d'envoi
```
POST https://api.sweego.io/send
Header: Api-Key: <SWEEGO_API_KEY>

{
  "provider": "email",          # toujours "email" (pas "sweego")
  "campaign-type": "market",    # "market" ou "transac" (pas "newsletter")
  "campaign-id": "lcr-xxx",
  "subject": "...",
  "from": {"email": "info@leclientroi.com", "name": "Le Client ROI"},
  "recipients": [{"email": "..."}],
  "message-html": "...",
  "message-txt": "...",
  "dry-run": false
}
```

---

## Emelia — domaines d'envoi

Emelia utilise ses propres boîtes d'envoi (warmup Emelia). Les domaines expéditeurs sont
configurés dans le dashboard Emelia (Settings → Mailboxes).
Auth : header `Authorization: <clé>` (sans Bearer pour REST).

---

## Maildoso — boîtes SMTP/IMAP

4 boîtes en warmup depuis le 2026-06-23 (~disponibles le 2026-07-07) :

| Boîte | SMTP | IMAP |
|---|---|---|
| j.durand@leclient-roi.com | smtp.maildoso.com:587 | imap.horus.maildoso.com:993 |
| j.bernard@leclient-roi.com | idem | idem |
| j.juste@leclient-roi.com | idem | idem |
| j.nguyen@leclient-roi.com | idem | idem |

Password : voir `.env` (`MAILDOSO_PASS`) — ne jamais hardcoder.
Domaine : `leclient-roi.com` (avec tiret, différent de `leclientroi.com`).

---

## VPS

| | |
|---|---|
| IP | 204.168.186.159 |
| User | autoblog |
| Commandes | `sudo -u autoblog bash -lc '...'` |
| Process manager | PM2 |
| App | `/home/autoblog/genesis` (backend) + `/home/autoblog/genesis-ui` (frontend) |

---

## Voir aussi
- `docs/platforms-api.md` — Auth, endpoints, tags et stats des 3 plateformes
- `docs/emelia-api.md` — Carte API Emelia vérifiée (REST + GraphQL)
- `routeur_doc/cold-email-engine.md` — Spec séquenceur Maildoso
