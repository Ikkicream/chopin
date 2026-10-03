# Setup Inbound emails

Source : https://learn.sweego.io/docs/inbound/setup_inbound

> Inbound email allows you to receive incoming emails and automatically extract their content via a webhook.

# Inbound Email

Inbound email allows you to receive incoming emails and automatically extract their content via a webhook.

### **Benefits of Inbound Email**

With this service, you can :

- Retrieve replies to the emails you send.

- Provide a dedicated address to directly integrate incoming emails into your application.

- Set up two-way email communication flows.

---

**Note:** Inbound feature is reserved for paying users.

[https://www.sweego.io/pricing](https://www.sweego.io/pricing)

**Prerequisite: We recommend using a subdomain for this service to avoid impacting the email deliverability of your main domain.**

### **How to Activate Inbound Email?**

- **Access your Sweego account.**
  
  Log in to [app.sweego.io](https://app.sweego.io) and navigate to the **Email** section.

- **Add a New Inbound Email.**
  
  Click on the **Inbound Email** tab, then on **Add new inbound email**.

![Inbound](undefined)

- **Configure Your Domain Information.**
  
  Fill in the required fields as follows :
  
  
  
  - **Inbound Subdomain**: The subdomain you want to use.
    
    Example : If you want to receive emails at `XXX@myinbound.mydomain.com`, enter `myinbound`.
  
  - **Domain**: The subdomain ior domain you want to use(which has to be verified first)
    
    Example : `mysubdomain.com`.

**Be careful: If you use your main domain, it will impact the email deliverability of that domain. It is therefore better to always use a subdomain.**

> Once configured, you will be able to receive all emails sent to addresses like `XXX@myinbound.mydomain.com`.

![Inbound2](undefined)

- **Add the New Inbound Email.**
  
  Click on **Add new inbound** to save the configuration.

![Inbound3](undefined)

As you can see, status is "not verified".

- **Set Up the MX Record with Your Registrar.**
  
  Add an MX record for your subdomain with the following details :
  
  
  ```
  myinbound.mydomain.com MX 10 inbound.sweego.co
  ```
  
  
  Refer to the documentation for adding the necessary DNS records : [Setting up Domains for Emails](https://learn.sweego.io/docs/emails/set_up_a_domain).

As soon as you'll have correctly added MX on your DNS zone, You'll be able to reverify your domain and will see Inbound is now verified.

Steps to reverify your domain:
[https://app.sweego.io/home/domains](https://app.sweego.io/home/domains)
Click on your subdomain, and click on "Reverify"

![Inbound4](undefined)

---

### **Test Your Configuration**

Once the setup is complete :

- Send an email to any address like `anything@myinbound.mydomain.com`.

- You will receive a webhook at the URL you specified during the configuration.

### **Webhook example**

```
{
  "event_type": "email_inbound",
  "timestamp": "2024-12-19T13:49:28.849638+00:00",
  "swg_uid": "04-601790a1-5fd4-4106-8e5a-469ec1af1c93",
  "from_": {
    "email": "my@mailaddress.com",
    "name": "My Name"
  },
  "to": [
    {
      "email": "anything@myinbound.mydomain.com",
      "name": ""
    }
  ],
  "cc": [],
  "text": "Receiv",
  "html": null,
  "subject": "test",
  "inbound_domain": "myinbound.mydomain.com",
  "attachments": [
    {
      "uuid": "02b8f2b6-b491-4450-9231-c3912ab28850",
      "name": "random.pdf",
      "content_type": "application/pdf",
      "size": 38408
    },
        {
      "uuid": "5dcd1ef8-abbd-4f77-b60d-6984aa404b51",
      "name": "screenshot.jpg",
      "content_type": "image/jpeg",
      "size": 19458
    },
  ],
  "event_id": "10c072f1-7821-4f30-9574-f13e3890701a",
  "channel": "email",
  "transaction_id": null
}
```

### Attachments

Attachments metadata are returned in webhook payloads but not the content in itself. In order to retrieves attachment content, you need to use the UUID attachment returned and query sweego API, documentation available [here](https://learn.sweego.io/docs/sweego/get-clients-uuid-client-domains-inbound-attachments-uuid-email-inbound-attachment).

The message size limit is 30MB

### Retry

In case the destination is unavailable, inbound email routing applies the following retry policy:

- **Retry frequency:** every 5 minutes

- **Maximum number of attempts:** 20

- **Maximum retry window:** up to 1 hour and 40 minutes of potential downtime coverage

---

**More informations about Inbound**: [https://www.sweego.io/product/new-inbound-email-routing](https://www.sweego.io/product/new-inbound-email-routing)
