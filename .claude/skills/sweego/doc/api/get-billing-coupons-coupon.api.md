# Check if coupon is valid

Source : https://learn.sweego.io/docs/sweego/get-billing-coupons-coupon

> Get all existing country list.

Check if coupon is valid

**GET** `https://api.sweego.io/billing/coupons/{coupon}`

Get all existing country list.

Args:
request: request received
coupon: coupon for which we want to check validity

Returns:
ClientBillingCouponIsValid: coupon validity info

### Paramètres ()

| Nom | Type | Requis | Description |
| --- | --- | --- | --- |
| `coupon` | string | oui |  |

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `valid` | boolean | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
