# Manage tracking options for this domain

Source : https://learn.sweego.io/docs/sweego/put-clients-uuid-client-domains-uuid-domain-tracking

> Init server actions: client_domain

Manage tracking options for this domain

**PUT** `https://api.sweego.io/clients/{uuid_client}/domains/{uuid_domain}/tracking`

Init server actions: client_domain

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_domain` | string (uuid4) | oui |  |
| `uuid_client` | string (uuid4) | oui |  |

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `click_enabled` | boolean |  |  |
| `open_enabled` | boolean |  |  |

### Réponses

#### 204 — Successful Response

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
