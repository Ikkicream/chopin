# Expiration date

Source : https://learn.sweego.io/docs/emails/headers/expiration_date

> Introduction

## Introduction

This document outlines the method for adding an expiration date to emails sent via our API and SMTP. The expiration date allows you to define a validity period for emails, after which they could be deleted.

## The context

This initiative is backed by [Badsender](https://www.badsender.com/), a French marketing agency specializing in email, which has set up a working group on how to reduce the digital footprint of email.

This working group is behind the [ZeroCarbon.email website](https://www.zerocarbon.email/fr/accueil/)

## The objective

To enable the sender to specify a validity date for the e-mails he sends, and to enable a recipient (and his Mailbox Service Provider) to avoid storing messages that no longer have any reason to exist and limit
This will avoid unnecessary email storage and limit the digital footprint of email.

An RFC proposal has been submitted to the IETF replaced by this one and it’s actively studied.

### API

#### Specifying the Expiration Date

In the JSON containing the information to be sent, you simply need to specify the following variable:

```
    "expires": "XXX"
```

The expires option can be set in two different formats:

##### - Relative Duration:

```
"expires": "1 day"
```

In this example, the email will expire 1 day after it is sent

##### - Absolute Date and Time:

```
"expires": "2024-08-20 16:31:00"
```

Here, the email will expire on August 20, 2024, at 16:31:00 (server time zone or UTC, depending on your configuration).

### SMTP

It's possible to add directly Expires header directly like this:

```
Expires: Thu, 6 Jun 2024 07:42:00 +0200
```

Header in the Received Email

When the email is received, the header will include the following line, indicating the expiration date and time:

```
Expires: Tue, 20 Aug 2024 14:18:31 -0000
```

This header follows the standard RFC 2822 format for dates and times.

## Conclusion

Adding an expiration date to emails allows you to control their validity period, ensuring better communication management. This feature also helps you reduce the carbon footprint of the emails you send by allowing them to expire (and to be deleted) at a certain date. If you need further assistance or clarification, our support team is available to help.
