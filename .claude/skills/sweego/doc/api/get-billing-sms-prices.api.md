# Get SMS price list

Source : https://learn.sweego.io/docs/sweego/get-billing-sms-prices

> Retrieves SMS price list (€)

Get SMS price list

**GET** `https://api.sweego.io/billing/sms/prices`

Retrieves SMS price list (€)

Args:
request: request received

Returns:
List [ BillingCountryPrice ]: Price for sending a sms to all supported country.

**Body**

### Réponses

#### 200 — Successful Response

Type : array<object (BillingCountryPrice)>
