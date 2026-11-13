# Why do I need to verify an email domain?

Source : https://learn.sweego.io/docs/emails/verify_an_email_domain

> You’ll need to verify your email domain in Sweego in order to authenticate it, for reliability and security reasons. It allows us to make sure you have the permissions necessary to send emails from that domain.

You’ll need to verify your email domain in Sweego in order to authenticate it, for reliability and security reasons. It allows us to make sure you have the permissions necessary to send emails from that domain.

In addition, adding a Return-Path header will allow us to track bounces for you.

To start sending emails with Sweego, you’ll need to add two CNAME records (CNAME 1 and CNAME 2) to your domain with your hosting provider. These two records are mandatory.

We also recommend adding the DMARC record. This third record is optional.

### CNAME 1 (for SPF)

This first CNAME allows us to create two records. First, the TXT record which will contain the SPF record. And secondly, the MX record which will allow us to track bounces with a Return-Path header.

We consider these records must-haves for both deliverability (to have the best chance of your emails arriving in your contacts’ inbox) and security. That’s why CNAME 1 is mandatory.

Once you’ve verified you email domain, you should see that the CNAME 1 record is either “Verified” or “Not verified” in the Verify domain panel. If the status is not verified for CNAME 1, you can always modify the record on your hosting provider and verify again from the Sweego platform.

### CNAME 2 (for DKIM)

This second CNAME allows us to create your DKIM records. We will be able to update your DKIM public key without you having to modify your DNS Records.

DKIM helps ensure email integrity, authenticity and security, which improves overall reliability of email communication. CNAME 2 is also mandatory to send emails with Sweego.

As with CNAME 1, once you’ve verified you email domain, you should see that the CNAME 2 record is either “Verified” or “Not verified” in the Verify domain panel. Again, you can always modify the record on your hosting provider and reverify the email domain from the Sweego application.

### DMARC

Adding a DMARC record is optional but we recommend that you do so. This is because Gmail and Yahoo! block emails for senders sending over 5000 emails a day since early 2024. And other MSPs seem to be following their lead.

When you verify your email domain, you’ll see one of two statuses for the DMARC record: “Record exists”, or “Record doesn’t exist.” As with CNAME 1 and CNAME 2, you can always modify the record and reverify the email domain in Sweego.

### Also, some definitions:

#### TXT Record

A TXT record is a DNS record that stores text information for a domain. It is used for domain verification and email security (SPF, DKIM, DMARC).

#### MX Record

An MX (Mail Exchange) record is a DNS record that directs emails to the mail servers responsible for receiving email for a domain.

#### SPF Record

An SPF (Sender Policy Framework) record is a DNS record that identifies which mail servers are authorized to send emails on behalf of a domain. It helps prevent email spoofing.

#### DKIM Signature

A DKIM (DomainKeys Identified Mail) signature is a digital signature added to email headers. It uses encryption to check that an email hasn’t been altered and that it’s from an authorized server.

#### DMARC Record

A DMARC (Domain-based Message Authentication, Reporting & Conformance) record is a DNS record that tells how to handle emails that fail SPF or DKIM checks. It boosts email security by giving rules for email validation and reporting.
