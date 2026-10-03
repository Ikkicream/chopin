# Email Payloads

Source : https://learn.sweego.io/docs/webhooks/payload

> Here is the list of payload you will receive depending on the event you subscribed to in email communication channel.

Here is the list of payload you will receive depending on the event you subscribed to in email communication channel.

### email_sent

`{"key": "[object Object]"}`

**[email_sent format]**

```json
{
  "event_type": email_sent,
  "timestamp": timestamp,
  "swg_uid": string,
  "event_id": UUID,
  "details": string,
  "channel": string,
  "transaction_id": UUID,
  "headers": {
    "x-mailer": string,
    "x-swg-uid": string,
    "x-campaign-id": string,
    "x-client-id": string,
    "x-originating-ip": string,
    "x-campaign-type": string,
    "x-custom-header": string|int,
    "x-transaction-id": UUID
  },
  "campaign_tag": array[string]|string|null,
  "campaign_type": string,
  "campaign_id": string,
  "recipient": string,
  "domain_from": string
}
```

**[email_sent example]**

```json
{
  "event_type": "email_sent",
  "timestamp": "2024-09-02T08:45:05+00:00",
  "swg_uid": "01-47d3e283-1afb-4b9e-bd45-bfbf32ba251f",
  "event_id": "3e42ea83-f6a5-40cc-a1fa-8745669454",
  "channel": "email",
  "transaction_id": "861aad97-e4e8-4aaf-9322-1b64835760b9",
  "headers": {
    "x-campaign-type": "default",
    "x-swg-uid": "01-47d3ekdpj-1fdb-4bde-bsd5-bfbf32sdgf54f",
    "x-mailer": "Sweego",
    "x-campaign-id": "default",
    "x-client-id": "0c8cc711c85e45b79189456644166sj",
    "x-originating-ip": "185.255.28.207",
    "x-email-id": "23",
    "x-transaction-id": UUID
  },
  "campaign_tags": null,
  "campaign_type": "default",
  "campaign_id": "default",
  "recipient": "mymail@mydomain",
  "domain_from": "send.sweego.io",
  "details": "Sep  2 08:45:05 prod-mta-03 zone-mta: Sep 02 08:45:05 info Sender/yahoo_us/1176[39] id=cqsdgfz7wuo5mgotwk 191bfdfgdfe8afc50000597.001 ACCEPTED from=prod-mta-03.448414784884e45b7918e68e49b64944f.191b1e8afc50000597@swg.send.sweego.io to=xxxxx-999@xxxx.com src=185.255.28.5 mx=mtz456.am0.yahoodns.net[XXX.XXX.XXX.XX] id=<1725266702.0c8cc711c85e45b7918ege4g84erg48erg4944f.191b1e8afc50000597@send.sweego.io> (250 ok dirdel)"
}
```

### delivered

`{"key": "[object Object]"}`

**[delivered format]**

```json
{
  "event_type": delivered,
  "timestamp": timestamp,
  "swg_uid": string,
  "event_id": UUID,
  "details": string,
  "channel": string,
  "transaction_id": UUID,
  "headers": {
    "x-mailer": string,
    "x-swg-uid": string,
    "x-campaign-id": string,
    "x-client-id": string,
    "x-originating-ip": string,
    "x-campaign-type": string,
    "x-custom-header": string|int,
    "x-transaction-id": UUID
  },
  "campaign_tag": array[string]|string|null,
  "campaign_type": string,
  "campaign_id": string,
  "recipient": string,
  "domain_from": string
}
```

**[delivered example]**

```json
{
  "event_type": "delivered",
  "timestamp": "2024-09-02T08:45:08+00:00",
  "swg_uid": "01-f1491565-39b6-4160-bc45-f5b27a277ca9",
  "event_id": "7ebba9ce-3742-45fe-866a-a0699a5a8042",
  "channel": "email",
  "transaction_id": "861aad97-e4e8-4aaf-9322-1b64835760b9",
  "headers": {
    "x-campaign-type": "default",
    "x-swg-uid": "01-f14sqdf65-fgh9b6-4160-bc45-fliolioa277ca9",
    "x-mailer": "Sweego",
    "x-campaign-id": "default",
    "x-client-id": "0c8cc711c85e4595953862",
    "x-originating-ip": "XXX.XXX.XXX.XX",
    "x-email-id": "23",
    "x-transaction-id": UUID
  },
  "campaign_tags": null,
  "campaign_type": "default",
  "campaign_id": "default",
  "recipient": "myemail@mydomain",
  "domain_from": "send.sweego.io",
  "details": "Sep  2 08:45:08 prod-mta-03 zone-mta: Sep 02 08:45:08 info Sender/gmail/1007[14] id=cclwz7wuo5mgotwk dsfsdfdsf8afb80000597.001 ACCEPTED from=prod-mta-03.0c8cc711c8151584918e68e49b64944f.191b1e8afb80000597@swg.send.sweego.io to=myemail@mydomain src=XXX.XXX.XXX.XXX mx=gmail-smtp-in.l.google.com[XXX.XXX.XXX.XXX] id=<1725284842.0c8184841c85e45b7918848e49b64944f.191b1e8afb80000597@send.sweego.io> (250 2.0.0 OK 1725266708 ffacd0b84848484-374c8d5c2a2si1032881f8f.195 - gsmtp)"
}
```

### soft-bounce

`{"key": "[object Object]"}`

**[soft-bounce format]**

```json
{
  "event_type": soft-bounce,
  "timestamp": timestamp,
  "swg_uid": string,
  "event_id": UUID,
  "details": string,
  "channel": string,
  "transaction_id": UUID,
  "headers": {
    "x-mailer": string,
    "x-swg-uid": string,
    "x-campaign-id": string,
    "x-client-id": string,
    "x-originating-ip": string,
    "x-campaign-type": string,
    "x-custom-header": string|int,
    "x-transaction-id": UUID
  },
  "campaign_tag": array[string]|string|null,
  "campaign_type": string,
  "campaign_id": string,
  "recipient": string,
  "domain_from": string
}
```

**[soft-bounce example]**

```json
{
  "event_type": "soft-bounce",
  "timestamp": "2024-08-20T08:38:27+00:00",
  "swg_uid": "01-4f5qsdqsd3-b5e1-4012-a350-2e3d0d176ef1",
  "event_id": "82ebfgbfgb-0fgbfg-4190-967c-2e8484212f1c0f",
  "channel": "email",
  "transaction_id": "861aad97-e4e8-4aaf-9322-1b64835760b9",
  "headers": {
    "x-campaign-type": "default",
    "x-swg-uid": "01-4f5e28484-b515-4848-1956-2e3d0d176ef1",
    "x-mailer": "Sweego",
    "x-client-id": "MypersonnalId",
    "x-originating-ip": "XXX.XXX.XXX.XXX",
    "x-campaign-ref": "895000N",
    "x-campaign-pool": "default",
    "x-campaign-id": "b20dsfsdfds6-9595b5-9595a7-565b9-5e2b826595053",
    "x-campaign-canal": "mycanal",
    "x-transaction-id": UUID
  },
  "campaign_tags": null,
  "campaign_type": "default",
  "campaign_id": "default",
  "recipient": "myemail@mydomain",
  "domain_from": "send.sweego.io",
  "details": "Aug 20 08:38:27 prod-mta-03 zone-mta: Aug 20 08:38:27 info Sender/gmail/4449[5] id=oifhdfgdfgdfptzkbcgv 14845548438770008de7.001 REJECTED[capacity] from=prod-mta-03.xxxxx.1916ee63959595770008de7@mysubdomain to=myemail@ùydomain src=XXX.XXX.XXXX.XXX mx=smtp-mydomain[XXX.XXX.XXX.XXX] id=<184844142467.xxx.191684848770008de7@mydomain> (452 <myemail@mydomain> User quota exceeded)",
  "response_code": 452,
  "status": null
}
```

### hard_bounce

`{"key": "[object Object]"}`

**[hard_bounce format]**

```json
{
  "event_type": hard_bounce,
  "timestamp": timestamp,
  "swg_uid": string,
  "event_id": UUID,
  "details": string,
  "channel": string,
  "transaction_id": UUID,
  "headers": {
    "x-mailer": string,
    "x-swg-uid": string,
    "x-campaign-id": string,
    "x-client-id": string,
    "x-originating-ip": string,
    "x-campaign-type": string,
    "x-custom-header": string|int,
    "x-transaction-id": UUID
  },
  "campaign_tag": array[string]|string|null,
  "campaign_type": string,
  "campaign_id": string,
  "recipient": string,
  "domain_from": string
}
```

**[hard_bounce example]**

```json
{
  "event_type": "hard_bounce",
  "timestamp": "2024-08-20T08:48:35+00:00",
  "swg_uid": "01-68d20f85-253e-4986-b7f0-0e4229df4d61",
  "event_id": "88eaff9a-5087-47d9-afdd-6eeaddfb11ae",
  "channel": "email",
  "transaction_id": "861aad97-e4e8-4aaf-9322-1b64835760b9",
  "headers": {
    "x-swg-uid": "01-68d20f85-253e-4986-b7f0-0e4229df4d61",
    "x-client-id": "myid",
    "x-campaign-pool": "default",
    "x-campaign-canal": "mycanal",
    "x-campaign-type": "default",
    "x-mailer": "Sweego",
    "x-originating-ip": "XXX.XXX.XXX.XXX",
    "x-campaign-ref": "895000#N",
    "x-campaign-id": "b205d7b6-9eb5-4ba7-b3b9-5e2b8cade053",
    "x-transaction-id": UUID
  },
  "campaign_tags": null,
  "campaign_type": "default",
  "campaign_id": "default",
  "recipient": "xxxx@domain.com",
  "domain_from": "my_domain.from",
  "details": "Aug 20 08:48:35 prod-mta-01 zone-mta: Aug 20 08:48:35 info Sender/XXX/1279[18] id=fh3vwwcf6cmnrzxu 1916ee7307c0008de7.001 REJECTED[other] from=prod-mta-01.xxxx.6ee7307c0008de7@xxx.xxx.xxx to=xxxx@mydomain.com src=XX.XX.XX.XX mx=smtp-xxxxxx[XXX.XXXX.XXXX.XXXX] id=<1724142530.yyyy.1916ee7307c0008de7@yy.yyy-yyyy.yy> (550 Invalid Recipient <xxxxx@domain.com> [smtp-08.ZZZ.local; ZZZ_520])",
  "response_code": 550,
  "status": null
}

```

### list_unsub

`{"key": "[object Object]"}`

**[list_unsub format]**

```json
{
  "event_type": list_unsub,
  "timestamp": timestamp,
  "swg_uid": string,
  "event_id": UUID,
  "details": string,
  "channel": string,
  "transaction_id": UUID,
  "headers": {
    "x-mailer": string,
    "x-swg-uid": string,
    "x-campaign-id": string,
    "x-client-id": string,
    "x-originating-ip": string,
    "x-campaign-type": string,
    "x-custom-header": string|int,
    "x-transaction-id": UUID
  },
  "campaign_tag": array[string]|string|null,
  "campaign_type": string,
  "campaign_id": string,
  "recipient": string,
  "domain_from": string
}
```

**[list_unsub example]**

```json
{
  "event_type": "list_unsub",
  "timestamp": "2024-09-02T12:55:09.416380+00:00",
  "swg_uid": "02-5898484-484f2-841d-84ea-a33351589aabc0",
  "event_id": "0a190ab5-aad8-4874-9c32-0848484f8fc",
  "channel": "email",
  "transaction_id": "861aad97-e4e8-4aaf-9322-1b64835760b9",
  "headers": {
    "x-campaign-id": "42",
    "x-campaign-tags": "billing",
    "x-campaign-type": "transac",
    "x-client-id": "d6b1222eb484fb8f4g8d4fg8cd4",
    "x-client-ip": "XXX.XXX.XXX.XXX",
    "x-mailer": "Sweeg",
    "x-originating-ip": "XXX.XXX.XXX.XXX",
    "x-ref-1": "643524",
    "x-ref-2": "lervcn",
    "x-ref-3": "o10icr",
    "x-swg-uid": "02-589edd0e-b7f2-4a1d-a3ea-a333cb9aabc0",
    "x-transaction-id": "3d0e56e8-3470-475b-8000-9dc43586f529"
  },
  "campaign_tags": "billing",
  "campaign_type": "transac",
  "campaign_id": "transac",
  "recipient": "myemail@mydomain.com",
  "domain_from": "sweego.mydomain.com",
  "one_click": false
}
```

### complaint

`{"key": "[object Object]"}`

**[complaint format]**

```json
{
  "event_type": complaint,
  "timestamp": timestamp,
  "swg_uid": string,
  "event_id": UUID,
  "details": string,
  "channel": string,
  "transaction_id": UUID,
  "headers": {
    "x-mailer": string,
    "x-swg-uid": string,
    "x-campaign-id": string,
    "x-client-id": string,
    "x-originating-ip": string,
    "x-campaign-type": string,
    "x-custom-header": string|int,
    "x-transaction-id": UUID
  },
  "campaign_tag": array[string]|string|null,
  "campaign_type": string,
  "campaign_id": string,
  "recipient": string,
  "domain_from": string
}
```

## Tracking

### Click

`{"key": "[object Object]"}`

**[click tracking format]**

```json
{
  "event_type": "email_clicked",
  "timestamp": timestamp,
  "swg_uid": string,
  "event_id": UUID,
  "channel": string,
  "transaction_id": UUID,
  "headers": {
    "x-mailer": string,
    "x-swg-uid": string,
    "x-campaign-id": string,
    "x-client-id": string,
    "x-originating-ip": string,
    "x-campaign-type": string,
    "x-custom-header": string|int,
    "x-transaction-id": UUID
  },
  "campaign_tags": string|null,
  "campaign_type": string,
  "campaign_id": string,
  "recipient": string,
  "domain_from": string,
  "subject": string,
  "click": {
    "ip_address": string,
    "url": string,
    "user_agent": string,
    "proxy": bool
  }
}
```

**[click tracking example]**

```json
{
  "event_type": "email_clicked",
  "timestamp": "2024-12-10T17:35:39",
  "swg_uid": "02-6e5dbe48-e6f4-4af3-8fb4-bf125e75776b",
  "event_id": "3e434a94-628c-4cbd-92b5-ed6be715aa2c",
  "channel": "email",
  "transaction_id": "568c5678-2d03-40f8-89e0-22ffb5cfe63d",
  "headers": {
    "x-mailer": "Sweego",
    "x-swg-uid": "02-6e5dbe48-e6f4-4af3-8fb4-bf125e75776b",
    "x-client-id": "f8367456332369298d050cf4bc83e058",
    "x-client-ip": "XXX.XXX.XXX.XXX",
    "x-campaign-id": "fake_campaign",
    "x-campaign-type": "default",
    "x-originating-ip": "XXX.XXX.XXX.XXX",
    "x-transaction-id": "568c5678-2d03-40f8-89e0-22ffb5cfe63d"
  },
  "campaign_tags": null,
  "campaign_type": "default",
  "campaign_id": "fake_campaign",
  "recipient": "random@domain.com",
  "domain_from": "my.domain.from",
  "subject": "Test webhook 2024-01-01",
  "click": {
    "ip_address": "XXX.XXX.XXX.XXX",
    "url": "https://google.com",
    "user_agent": "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)",
    "proxy": false
  }
}
```

### Human / Proxy open

`{"key": "[object Object]"}`

**[open tracking format]**

```json
{
  "event_type": "email_opened",
  "timestamp": timestamp,
  "swg_uid": string,
  "event_id": UUID,
  "channel": string,
  "transaction_id": UUID,
  "headers": {
    "x-mailer": string,
    "x-swg-uid": string,
    "x-campaign-id": string,
    "x-client-id": string,
    "x-originating-ip": string,
    "x-campaign-type": string,
    "x-custom-header": string|int,
    "x-transaction-id": UUID
  },
  "campaign_tags": string|null,
  "campaign_type": string,
  "campaign_id": string,
  "recipient": string,
  "domain_from": string,
  "subject": string,
  "open": {
    "ip_address": string,
    "user_agent": string,
    "proxy": bool
  }
}
```

**[open tracking example]**

```json
{
  "event_type": "email_opened",
  "timestamp": "2024-01-01T00:00:00",
  "swg_uid": "02-6e5dbe48-e6f4-4af3-8fb4-bf125e75776b",
  "event_id": "3e434a94-628c-4cbd-92b5-ed6be715aa2c",
  "channel": "email",
  "transaction_id": "568c5678-2d03-40f8-89e0-22ffb5cfe63d",
  "headers": {
    "x-mailer": "Sweego",
    "x-swg-uid": "02-6e5dbe48-e6f4-4af3-8fb4-bf125e75776b",
    "x-client-id": "f8367456332593298d050cf4bc83e0ab",
    "x-client-ip": "XXX.XXX.XXX.XXX",
    "x-campaign-id": "fake_campaign",
    "x-campaign-type": "default",
    "x-originating-ip": "XXX.XXX.XXX.XXX",
    "x-transaction-id": "568c5678-2d03-40f8-89e0-22ffb5cfe63d"
  },
  "campaign_tags": null,
  "campaign_type": "default",
  "campaign_id": "fake_campaign",
  "recipient": "XXXX@XXXXX.com",
  "domain_from": "my_domain.from",
  "subject": "Test webhook",
  "open": {
    "ip_address": "XXX.XXX.XXX.XXX",
    "user_agent": "Mozilla/5.0 (Windows NT 5.1; rv:11.0) Gecko Firefox/11.0 (via ggpht.com GoogleImageProxy)",
    "proxy": true
  }
}
```
