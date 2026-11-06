# Sms Payloads

Source : https://learn.sweego.io/docs/webhooks/sms_payload

> Here is the list of payload you will receive depending on the event you subscribed to in email communication channel.

Here is the list of payload you will receive depending on the event you subscribed to in email communication channel.

### sms_sent

`{"key": "[object Object]"}`

**[sms_sent format]**

```json
{
    "event_type": sms_sent,
    "timestamp": timestamp,
    "swg_uid": string,
    "event_id": UUID,
    "details": string,
    "channel": sms,
    "client-id": string,
    "country_code": string,
    "sender_id": string,
    "sms_type": string,
    "sms_price": int,
    "campaign_id": string,
    "test_mode": true/false,
    "send_date": timestamp,
    "mobile_network_code": int,
    "mobile_country_code": int
}
```

**[sms_sent example]**

```json
{
  "event_type": "sms_sent",
  "timestamp": "2024-09-02T16:03:05",
  "swg_uid": "03-1c9e3539-d499-4699-ae5d-fa50e6e8af2a",
  "event_id": "037d527e-576c-47aa-a82d-3cd01fef2064",
  "channel": "sms",
  "client_id": "0c8cc711-c85e-45b7-918e-68e49b64944f",
  "country_code": "FR",
  "phone_number": "00336XXXXXXXX",
  "sender_id": "Sweego",
  "sms_type": "market",
  "sms_price": 0.04,
  "campaign_id": "random-campaign-id",
  "test_mode": false,
  "send_date": "2024-09-02T14:03:01.359985",
  "mobile_network_code": 10,
  "mobile_country_code": 208
}
```

### sms_undelivered

`{"key": "[object Object]"}`

**[sms_undelivered format]**

```json
{
    "event_type": "sms_undelivered",
    "timestamp": timestamp,
    "swg_uid": string,
    "event_id": UUID,
    "channel": "sms",
    "client_id": UUID,
    "country_code": string,
    "phone_number": string,
    "sender_id": string,
    "sms_type": string,
    "sms_price": float,
    "nb_segments": int,
    "campaign_id": string,
    "transaction_id": UUID,
    "test_mode": true/false,
    "send_date": timestamp,
    "status": "undelivered",
    "mobile_network_code": int,
    "mobile_country_code": int
}
```

**[sms_undelivered example]**

```json
{
    "campaign_id": "random-campaign-id",
    "channel": "sms",
    "client_id": "73d177d7-3cc3-4286-bbdd-a87ad778e2ed",
    "country_code": "PT",
    "event_id": "454ed966-7fda-44e4-94d0-31fb35049b50",
    "event_type": "sms_undelivered",
    "mobile_country_code": 268,
    "mobile_network_code": 1,
    "nb_segments": 1,
    "phone_number": "00351919888456",
    "send_date": "2026-02-05T10:55:31.581886",
    "sender_id": "ReservasPT",
    "sms_price": 0.02,
    "sms_type": "transactional",
    "status": "undelivered",
    "swg_uid": "03-ec11d5b8-0578-49aa-9ecc-73966fb829ec",
    "test_mode": false,
    "timestamp": "2026-02-05T11:55:38",
    "transaction_id": "f5c0c329-fa69-4c6e-afee-8e95963a8e56"
}
```

### sms_stop

`{"key": "[object Object]"}`

**[sms_stop format]**

```json
{
    "event_type": sms_stop,
    "timestamp": timestamp,
    "swg_uid": string,
    "event_id": UUID,
    "details": string,
    "channel": sms,
    "client-id": string,
    "country_code": string,
    "phone_number": string,
    "sender_id": string,
    "sms_type": string,
    "stop_date": timestamp,
    "price": int
}
```

**[sms_stop example]**

```json
{
  "event_type": "sms_stop",
  "timestamp": "2024-09-03T10:57:30",
  "swg_uid": "03-601d19d5-ed83-4f11-b6be-739f8742335b",
  "event_id": "02bdd4e1-2683-4e5d-8811-e16cd10f9b74",
  "channel": "sms",
  "client_id": "0c8cc711-c85e-45b7-918e-68e49b64944f",
  "country_code": "FR",
  "phone_number": "0033600000000",
  "sender_id": "36047",
  "stop_date": "2024-09-03T10:57:30",
  "price": 0.04
}
```

### sms_clicked

`{"key": "[object Object]"}`

**[sms_clicked format]**

```json
{
  "event_type": "sms_clicked",
  "channel": "sms",
  "sms_type": string ("transactional|market"),
  "campaign_id": null,
  "test_mode": bool,
  "timestamp": timestamp,
  "swg_uid": string,
  "event_id": UUID,
  "transaction_id": UUID,
  "client_id": UUID,
  "country_code": string,
  "phone_number": String,
  "sender_id": string,
  "click": {
    "ip_address": string,
    "url": string,
    "proxy": bool
  }
}
```

**[sms_clicked example]**

```json
{
  "event_type": "sms_clicked",
  "channel": "sms",
  "sms_type": "transactional",
  "campaign_id": null,
  "test_mode": false,
  "timestamp": "2024-12-11T15:52:26",
  "swg_uid": "03-74929862-f85f-477d-b96f-70628cc27d89",
  "event_id": "efed9be1-16ba-4327-89b5-126da530b080",
  "transaction_id": null,
  "client_id": "f8367456-3323-4429-8d05-0cf4bc83e058",
  "country_code": "FR",
  "phone_number": "0033781734878",
  "sender_id": "38082",
  "click": {
    "ip_address": "80.215.185.60",
    "url": "https://google.com",
    "proxy": false
  }
}
```
