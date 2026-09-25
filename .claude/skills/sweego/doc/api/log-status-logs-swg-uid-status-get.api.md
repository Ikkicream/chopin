# Retrieve a status of a message by the Sweego UID

Source : https://learn.sweego.io/docs/sweego/log-status-logs-swg-uid-status-get

> Get a status of a message by the Sweego UID

Retrieve a status of a message by the Sweego UID

**GET** `https://api.sweego.io/logs/{swg_uid}/status`

Get a status of a message by the Sweego UID

- **swg_uid**: Sweego id

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `swg_uid` | string | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

**Variante : ModelOutLogStatus**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `channel` | string | oui |  |
| `status` | string | oui |  |
| `swg_uid` | string | oui |  |

**Variante : ModelResponseFail**

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `msg` | string | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
