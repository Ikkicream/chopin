# Get client plan

Source : https://learn.sweego.io/docs/sweego/get-clients-uuid-client-billing-plans-current

> Get client plan

Get client plan

**GET** `https://api.sweego.io/clients/{uuid_client}/billing/plans/current`

Get client plan

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid_client` | string (uuid4) | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `id` | integer | oui | minimum : `0`; maximum : `2147483647` |
| `range_name` | string | oui |  |
| `plan_name` | string | oui |  |
| `price` | integer | oui |  |
| `commitment` | string | oui | An enumeration. — valeurs : `day`, `month`, `year` |
| `current_period_start_dt` | string (date-time) | oui |  |
| `current_period_end_dt` | string (date-time) | oui |  |
| `subscription_dt` | string (date-time) | oui |  |
| `termination_dt` | string (date-time) |  |  |
| `active` | boolean | oui |  |
| `renews_at` | string (date-time) |  |  |
| `next_payment_at` | string (date-time) |  |  |
| `next_payment_estimated_price` | integer |  |  |
| `next_subscription` | object (BillingPlanInfoData) |  |  |
| `next_subscription.id` | integer | oui | minimum : `0`; maximum : `2147483647` |
| `next_subscription.range_name` | string | oui |  |
| `next_subscription.plan_name` | string | oui |  |
| `next_subscription.price` | integer | oui |  |
| `next_subscription.commitment` | string | oui | An enumeration. — valeurs : `day`, `month`, `year` |
| `next_subscription.current_period_start_dt` | string (date-time) | oui |  |
| `next_subscription.current_period_end_dt` | string (date-time) | oui |  |
| `next_subscription.subscription_dt` | string (date-time) | oui |  |
| `next_subscription.termination_dt` | string (date-time) |  |  |
| `next_subscription.active` | boolean | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
