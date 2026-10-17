# Email sender authentication

Source : https://learn.sweego.io/docs/auth/sender_authentication

> Email providers require the implementation of email authentication mechanisms such as SPF, DKIM, and DMARC.

Email providers require the implementation of email authentication mechanisms such as SPF, DKIM, and DMARC.

SPF (Sender Policy Framework) ensures that the IP address used to send an email is authorized.

DKIM (DomainKeys Identified Mail) signs an email to ensure it hasn't been altered during transmission.

DMARC (Domain-based Message Authentication, Reporting, and Conformance) provides guidelines on how to handle emails in case of an attack or non-compliance with SPF and DKIM.

## Setting up SPF & MX Records (for Return-Path)

The sending domain must have our SPF (Sender Policy Framework) record.

We provide an include for SPF that clients can add to their TXT records:

```
include:spf.swg-srv.net
```

However, to handle bounces transmitted to the Return-Path, a CNAME (Canonical Name) record needs to be created as follows:

```
news.domain.com IN CNAME 1-cname-par-client.swg-srv.net
```

The record 1-cname-par-client.swg-srv.net will contain a TXT record with the SPF information and an MX (Mail Exchange) record, allowing bounces to be routed to our bounce management servers.

## Setting up DKIM

To have control over the update of DKIM key pairs, we prefer using a CNAME (Canonical Name) record in the following format:

```
client-dkim.sweego.co
```

The CNAME will be specific to each client.

This record will be a TXT record containing the Selector information:

```
client-dkim   199     IN      TXT     "v=DKIM1;t=s;p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAyABOEdpIYHjPahZ7zxSeoHe1+l+kQEA4y566bNBMtDcyCdMJMixnhHqiCsnwQp6vvNJvcouuLVFvm/cJMsVPAOHoqGfFyuQugdUQm8UXK23VKOkQbsgP1RNWBIgmxZABBVwe+SG4SHX3l6vH9eBLby1FpxZRc8Gh893GDgnwz/0V/CbwCniJNakHy6/xAJe4MI7n7UsB7yrQQPJ34fn9mc3tqrHKizrrzcG0rVw44LZh/bf6ccBj+UBKx2OSVrRuATqBiFRYxL3yWyfHl4yLi/vvVAf8ijdqNyj1kk1IMfkEK2ptM1RDtuVHgKmI/Qz8qIlc4QXTo3jsuH5HWLGBWQIDAQAB"
```

All our DKIM keys must have a minimum encryption level of 2048.

To set up DKIM, the client needs to create a record of type:

```
selector1._domainkey.domain.com IN CNAME client-dkim.sweego.co
```

## Setting up DMARC

DMARC (Domain-based Message Authentication, Reporting, and Conformance) is a protocol that allows domain owners to protect their domain from unauthorized use, such as email spoofing.

DMARC builds on SPF and DKIM by instructing receiving email servers on how to handle emails that fail these authentication checks.

It also provides reporting capabilities so domain owners can monitor and adjust their email authentication strategy.

To set up DMARC, the client needs to add a DMARC record to their DNS in the following format:

```
_dmarc.domain.com. IN TXT "v=DMARC1; p=none; rua=mailto:dmarc-reports@domain.com; ruf=mailto:dmarc-failures@domain.com; fo=1"
```

- **v=DMARC1**: Indicates this is a DMARC record.

- **p=none**: Specifies the policy for handling emails that fail SPF/DKIM (can be set to none, quarantine, or reject).

- **rua=mailto:dmarc-reports@domain.com**: Defines where aggregate reports (daily statistics of email authentication results) should be sent.

- **ruf=mailto:dmarc-failures@domain.com**: Defines where forensic reports (detailed information on individual email failures) should be sent.

- **fo=1**: Ensures that detailed forensic reports are sent whenever SPF or DKIM fail.

The **p** policy can be adjusted based on the level of enforcement the client wants:

- **none**: Only monitors email traffic without impacting delivery.

- **quarantine**: Marks suspicious emails, which may be delivered to the spam/junk folder.

- **reject**: Blocks emails that fail the DMARC check.

Setting up DMARC helps clients gain visibility on unauthorized use of their domain and progressively tighten security to prevent phishing attacks and improve email deliverability.
