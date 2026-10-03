# Get SMS price by country

Source : https://learn.sweego.io/docs/sweego/get-billing-sms-prices-country-code

> Retrieves SMS price (€) for a given country

Get SMS price by country

**GET** `https://api.sweego.io/billing/sms/prices/{country_code}`

Retrieves SMS price (€) for a given country

Args:
request: request received
country_code: country code

Returns:
BillingPrice: Price for sending a sms to the given country.

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `country_code` | string | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `price` | number | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
