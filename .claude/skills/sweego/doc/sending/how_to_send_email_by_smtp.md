#  How to Send an Email by SMTP

Source : https://learn.sweego.io/docs/sending/how_to_send_email_by_smtp

> You can send email by SMTP or API according your needs.

You can send email by SMTP or API according your needs.

## Prerequisites for sending your first email

Before sending you have to configure your sub-domain and create SMTP access.

### Configure and verify a Subdomain

A best pratice in delivrability for sending email is to use a subdomain rather than the domain name directly.

Utilizing a subdomain separates the sender reputation of your core domain from email marketing activities especially but it could be usefull to to protect you from being sent by mistake, for example.

With that you can easily seperate your sending by using dedicated subdomain for marketing or transactionnal parts.

In Sweego, we've decided to make the use of a sub-domain dedicated to emailing mandatory.

You can follow [our guide to setup your domain](https://learn.sweego.io/docs/domains/set_up_a_domain)  in Sweego.

```
You have to verify the good configuration of your subdomain before sending. 
A subdomain not verified can't send email.
```

The verification have two functions:

- Sub-domain verification allows us to ensure that the user has sufficient rights with the domain name owner to add records.

- The records created are used for authentication (SPF & DKIM) and bounce management.

You can read our article if you want to know more about email authentication.

### Create a SMTP Access

You can follow our guide to [create a SMTP Access](https://learn.sweego.io/docs/auth/smtp)

### STARTTLS

You have to send email with STARTTLS support. (You can use 2525 or 587 port)

## Send a simple email

### Prerequisites

- [Create and verify your domain or subdomain](#configure-and-verify-a-subdomain)

### Sending email

Explore various methods for sending emails in the examples provided below.

We recommand to use Swaks for test to send email by SMTP.

Swaks means Swiss Army Knife for SMTP and that's true!

`{"key": "[object Object]"}`

**[Swaks]**

```js
    swaks --to <EMAIL_TO> \
          --from <EMAIL_FROM> \
          --server <HOSTNAME> --port 2525 -tls \
          --auth-user "<LOGIN>" --auth-password "<PASSWORD>" \
          --body "Email body" \
          --h-Subject "Email subject"
```

**[Python]**

```py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import smtplib
import ssl
from email.message import EmailMessage
import sys

zmta_host = "<HOSTNAME>"
email_to = "<EMAIL_TO>"
email_from = "<EMAIL_FROM>"
login_user = "<LOGIN>"
login_password = "<PASSWORD>"

EMAIL_SUBJECT = "Email subject"
EMAIL_BODY = """
Email body
"""

# SSL configuration
context = ssl.SSLContext(ssl.PROTOCOL_TLS)

# SMTP connection
con = smtplib.SMTP(host=zmta_host, port=2525)

con.ehlo()
con.starttls(context=context)
con.ehlo()

# Login
con.login(user=login_user, password=login_password)

# Email body
message = EmailMessage()
message.set_content(EMAIL_BODY)
message["To"] = email_to
message["From"] = email_from
message["Subject"] = EMAIL_SUBJECT

# Send email
con.sendmail(from_addr=email_from, to_addrs=email_to, msg=message.as_string())

# Exit
sys.exit(0)

```

**[Powershell]**

```js
# SMTP parameters
$smtpServer = "<HOSTNAME>"
$smtpFrom = "<EMAIL_FROM>"
$smtpTo = "<EMAIL_TO>"
$messageSubject = "Email subject"
$messageBody = "Email body>"

# PSCredential objec creation
$secpasswd = ConvertTo-SecureString '<PASSWORD>' -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential ('<LOGIN>', $secpasswd)

# Send-MailMessage configuration with ServerCertificateValidationCallback
$null = [System.Net.ServicePointManager]::ServerCertificateValidationCallback -eq { $true }

# Send email
Send-MailMessage -From $smtpFrom -To $smtpTo -Subject $messageSubject -Body $messageBody -BodyAsHtml -SmtpServer $smtpServer -Port 2525 -UseSsl -Credential $cred

# Certificate config restaure
$null = [System.Net.ServicePointManager]::ServerCertificateValidationCallback -eq $null
```

**[.net]**

```js

/*
System.Net.ServicePointManager.ServerCertificateValidationCallback =
     (sender, certificate, chain, sslPolicyErrors) =\> true;
*/

System.Net.Mail.MailMessage email = new System.Net.Mail.MailMessage(emailFrom,emailTo);
email.Subject = "Email subject";
email.IsBodyHtml = true;
email.Body = "Email Body";

System.Net.Mail.SmtpClient smtp = new System.Net.Mail.SmtpClient(<HOSTNAME>,2525);
var cred = new System.Net.NetworkCredential(<LOGIN>, <PASSWORD>);
smtp.Credentials = cred;
smtp.EnableSsl = true;
smtp.Send(email);
```

## Send an email with attachment

### Prerequisites

- [Create and verify your domain or subdomain](#configure-and-verify-a-subdomain)

### Sending email

`{"key": "[object Object]"}`

**[Swaks]**

```js
    swaks --to <EMAIL_TO> \
          --from <EMAIL_FROM> \
          --server <HOSTNAME> --port 2525 -tls \
          --auth-user "<LOGIN>" --auth-password "<PASSWORD>" \
          --body "Email body" \
          --h-Subject "Email subject"
          --attach <ATTACHMENT_FILE>
```

**[Python]**

```py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
This script sends an email via SMTP with optional file attachment.
"""

import smtplib
import ssl
from email.message import EmailMessage
from email.mime.base import MIMEBase
from email import encoders
import sys
import os
import argparse

# SMTP configuration constants
ZMTA_HOST = "<ZMTA_HOST>"
EMAIL_TO = "<EMAIL_TO>"
EMAIL_FROM = "<EMAIL_FROM>"
LOGIN_USER = (
    "<LOGIN_USER>"
)
LOGIN_PASSWORD = "<LOGIN_PASSWORD>"

EMAIL_SUBJECT = "Email subject"
EMAIL_BODY = """
Email body
"""

# Function to encode the file to base64
def encode_file_to_base64(filepath):
    """
    Encodes the given file to base64 format.

    Args:
        filepath (str): The path to the file to encode.

    Returns:
        bytes: The base64 encoded content of the file.
    """
    with open(filepath, "rb") as file_content:
        return file_content.read()

# Parse arguments
parser = argparse.ArgumentParser(description="Send an email with optional attachment.")
parser.add_argument("--attachment-file", type=str, help="Path to the attachment file.")
args = parser.parse_args()

# SSL configuration
context = ssl.SSLContext(ssl.PROTOCOL_TLS)

# SMTP connection
con = smtplib.SMTP(host=ZMTA_HOST, port=2525)

con.ehlo()
con.starttls(context=context)
con.ehlo()

# Login
con.login(user=LOGIN_USER, password=LOGIN_PASSWORD)

# Email body
message = EmailMessage()
message.set_content(EMAIL_BODY)
message["To"] = EMAIL_TO
message["From"] = EMAIL_FROM
message["Subject"] = EMAIL_SUBJECT

# Attaching the file if provided
if args.attachment_file:
    # Check if the file exists
    if os.path.isfile(args.attachment_file):
        attachment = encode_file_to_base64(args.attachment_file)
        mime_base = MIMEBase("application", "octet-stream")
        mime_base.set_payload(attachment)
        encoders.encode_base64(mime_base)
        mime_base.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(args.attachment_file)}",
        )
        message.add_attachment(mime_base)
    else:
        print(f"Attachment file {args.attachment_file} not found!")
        sys.exit(1)

# Send email
con.sendmail(from_addr=EMAIL_FROM, to_addrs=EMAIL_TO, msg=message.as_string())

# Exit
sys.exit(0)
```
