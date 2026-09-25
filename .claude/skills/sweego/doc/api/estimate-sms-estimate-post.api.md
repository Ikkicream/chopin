# Estimate sms length & price

Source : https://learn.sweego.io/docs/sweego/estimate-sms-estimate-post

> Estimate sms length & price

Estimate sms length & price

**POST** `https://api.sweego.io/sms/estimate`

Estimate sms length & price

- **data**: Body content

### Corps de la requête (requis)

Content-Type : `application/json`

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `campaign_type` | string | oui | Type of sms — valeurs : `market`, `transac` |
| `message_txt` | string |  | Message provided in text formae. Only one of message_txt & template_id must be set |
| `recipients` | array<object (ModelRecipientSms)> |  | List of recipient. If set, will calcul sms price & credit left |
| `recipients[].converted_num` | string |  |  |
| `recipients[].num` | string | oui |  |
| `recipients[].region` | string | oui | valeurs : `AC`, `AD`, `AE`, `AF`, `AG`, `AI`, `AL`, `AM`, `AO`, `AR`, `AS`, `AT`, `AU`, `AW`, `AX`, `AZ`, `BA`, `BB`, `BD`, `BE`, `BF`, `BG`, `BH`, `BI`, `BJ`, `BL`, `BM`, `BN`, `BO`, `BQ`, `BR`, `BS`, `BT`, `BW`, `BY`, `BZ`, `CA`, `CC`, `CD`, `CF`, `CG`, `CH`, `CI`, `CK`, `CL`, `CM`, `CO`, `CR`, `CU`, `CV`, `CW`, `CX`, `CY`, `CZ`, `DE`, `DJ`, `DK`, `DM`, `DO`, `DZ`, `EC`, `EE`, `EG`, `EH`, `ER`, `ES`, `ET`, `FI`, `FJ`, `FK`, `FM`, `FO`, `FR`, `GA`, `GB`, `GD`, `GE`, `GF`, `GG`, `GH`, `GI`, `GL`, `GM`, `GN`, `GP`, `GQ`, `GR`, `GT`, `GU`, `GW`, `GY`, `HK`, `HN`, `HR`, `HT`, `HU`, `ID`, `IE`, `IL`, `IM`, `IN`, `IO`, `IQ`, `IR`, `IS`, `IT`, `JE`, `JM`, `JO`, `JP`, `KE`, `KG`, `KH`, `KI`, `KM`, `KN`, `KP`, `KR`, `KW`, `KY`, `KZ`, `LA`, `LB`, `LC`, `LI`, `LK`, `LR`, `LS`, `LT`, `LU`, `LV`, `LY`, `MA`, `MC`, `MD`, `ME`, `MF`, `MG`, `MH`, `MK`, `ML`, `MM`, `MN`, `MO`, `MP`, `MQ`, `MR`, `MS`, `MT`, `MU`, `MV`, `MW`, `MX`, `MY`, `MZ`, `NA`, `NC`, `NE`, `NF`, `NG`, `NI`, `NL`, `NO`, `NP`, `NR`, `NU`, `NZ`, `OM`, `PA`, `PE`, `PF`, `PG`, `PH`, `PK`, `PL`, `PM`, `PR`, `PS`, `PT`, `PW`, `PY`, `QA`, `RE`, `RO`, `RS`, `RU`, `RW`, `SA`, `SB`, `SC`, `SD`, `SE`, `SG`, `SH`, `SI`, `SJ`, `SK`, `SL`, `SM`, `SN`, `SO`, `SR`, `SS`, `ST`, `SV`, `SX`, `SY`, `SZ`, `TA`, `TC`, `TD`, `TG`, `TH`, `TJ`, `TK`, `TL`, `TM`, `TN`, `TO`, `TR`, `TT`, `TV`, `TZ`, `UA`, `UG`, `US`, `UY`, `UZ`, `VA`, `VC`, `VE`, `VG`, `VI`, `VN`, `VU`, `WF`, `WS`, `XK`, `YE`, `YT`, `ZA`, `ZM`, `ZW`, `OTHER` |
| `shorten_urls` | boolean |  | True to shorten urls — défaut : `true` |
| `shorten_with_protocol` | boolean |  | Add protocol to shortened urls — défaut : `true` |
| `simulate_data` | boolean |  | Simulate shortened urls uid & stop short num — défaut : `true` |
| `template_id` | string |  | ID of a saved template. Only one of message_txt & template_id must be set |
| `track_urls` | boolean |  | Tracks all urls — défaut : `false` |
| `variables` | object (Variables) |  | Variables dictionary to uses with template (ignored otherwise) |

### Réponses

#### 200 — Successful Response

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `credit` | string |  |  |
| `credit_after` | string |  |  |
| `credit_before` | string |  |  |
| `error_code` | integer |  |  |
| `error_message` | string |  |  |
| `max_nb_pages` | integer |  |  |
| `per_recipients` | array<object (ModelOutSmsEstimateRecipient)> |  |  |
| `per_recipients[].credit_per_page` | string |  |  |
| `per_recipients[].credit_total` | string |  |  |
| `per_recipients[].max_chars_available` | integer |  |  |
| `per_recipients[].message` | string | oui |  |
| `per_recipients[].nb_pages` | integer |  |  |
| `per_recipients[].recipient` | object (ModelRecipientSms) | oui |  |
| `per_recipients[].recipient.converted_num` | string |  |  |
| `per_recipients[].recipient.num` | string | oui |  |
| `per_recipients[].recipient.region` | string | oui | valeurs : `AC`, `AD`, `AE`, `AF`, `AG`, `AI`, `AL`, `AM`, `AO`, `AR`, `AS`, `AT`, `AU`, `AW`, `AX`, `AZ`, `BA`, `BB`, `BD`, `BE`, `BF`, `BG`, `BH`, `BI`, `BJ`, `BL`, `BM`, `BN`, `BO`, `BQ`, `BR`, `BS`, `BT`, `BW`, `BY`, `BZ`, `CA`, `CC`, `CD`, `CF`, `CG`, `CH`, `CI`, `CK`, `CL`, `CM`, `CO`, `CR`, `CU`, `CV`, `CW`, `CX`, `CY`, `CZ`, `DE`, `DJ`, `DK`, `DM`, `DO`, `DZ`, `EC`, `EE`, `EG`, `EH`, `ER`, `ES`, `ET`, `FI`, `FJ`, `FK`, `FM`, `FO`, `FR`, `GA`, `GB`, `GD`, `GE`, `GF`, `GG`, `GH`, `GI`, `GL`, `GM`, `GN`, `GP`, `GQ`, `GR`, `GT`, `GU`, `GW`, `GY`, `HK`, `HN`, `HR`, `HT`, `HU`, `ID`, `IE`, `IL`, `IM`, `IN`, `IO`, `IQ`, `IR`, `IS`, `IT`, `JE`, `JM`, `JO`, `JP`, `KE`, `KG`, `KH`, `KI`, `KM`, `KN`, `KP`, `KR`, `KW`, `KY`, `KZ`, `LA`, `LB`, `LC`, `LI`, `LK`, `LR`, `LS`, `LT`, `LU`, `LV`, `LY`, `MA`, `MC`, `MD`, `ME`, `MF`, `MG`, `MH`, `MK`, `ML`, `MM`, `MN`, `MO`, `MP`, `MQ`, `MR`, `MS`, `MT`, `MU`, `MV`, `MW`, `MX`, `MY`, `MZ`, `NA`, `NC`, `NE`, `NF`, `NG`, `NI`, `NL`, `NO`, `NP`, `NR`, `NU`, `NZ`, `OM`, `PA`, `PE`, `PF`, `PG`, `PH`, `PK`, `PL`, `PM`, `PR`, `PS`, `PT`, `PW`, `PY`, `QA`, `RE`, `RO`, `RS`, `RU`, `RW`, `SA`, `SB`, `SC`, `SD`, `SE`, `SG`, `SH`, `SI`, `SJ`, `SK`, `SL`, `SM`, `SN`, `SO`, `SR`, `SS`, `ST`, `SV`, `SX`, `SY`, `SZ`, `TA`, `TC`, `TD`, `TG`, `TH`, `TJ`, `TK`, `TL`, `TM`, `TN`, `TO`, `TR`, `TT`, `TV`, `TZ`, `UA`, `UG`, `US`, `UY`, `UZ`, `VA`, `VC`, `VE`, `VG`, `VI`, `VN`, `VU`, `WF`, `WS`, `XK`, `YE`, `YT`, `ZA`, `ZM`, `ZW`, `OTHER` |
| `per_recipients[].text_size` | integer |  |  |
| `state` | boolean | oui |  |

#### 422 — Validation Error

| Champ | Type | Requis | Description |
| --- | --- | --- | --- |
| `detail` | array<object (ValidationError)> |  |  |
| `detail[].loc` | array<string \| integer> | oui |  |
| `detail[].msg` | string | oui |  |
| `detail[].type` | string | oui |  |
