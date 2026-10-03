# Get info from token

Source : https://learn.sweego.io/docs/sweego/get-clients-users-info

> Get info from token

Get info from token

**GET** `https://api.sweego.io/clients/users/info`

Get info from token

**Body**

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `uuid` | string (uuid4) | oui |  |
| `status` | integer | oui | An enumeration. — valeurs : `0`, `1`, `2`, `3`, `4` |
| `onboarded` | boolean | oui |  |
| `creation_dt` | string (date-time) | oui |  |
| `last_update_dt` | string (date-time) | oui |  |
| `email_contact` | string (email) |  |  |
| `tz_name` | string | oui |  |
| `country` | string |  | minLength : `2`; maxLength : `2`; pattern : `[a-zA-Z]{2}` |
| `address` | string |  | minLength : `1` |
| `address_2` | string |  | minLength : `1` |
| `phone_number` | string |  | minLength : `1` |
| `postal_code` | string |  | minLength : `1` |
| `city` | string |  | minLength : `1` |
| `intra_vat` | string |  | minLength : `1` |
| `company_name` | string |  | minLength : `1` |
| `client_type` | string | oui | Type of client possible — valeurs : `company`, `individual` |
| `billing_email_address` | string (email) |  |  |
| `sweego_referral_source` | string |  |  |
| `uuid_user` | string (uuid4) | oui |  |
