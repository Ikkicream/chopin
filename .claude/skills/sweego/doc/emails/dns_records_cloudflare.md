# DNS records with Cloudflare

Source : https://learn.sweego.io/docs/emails/dns_records_cloudflare

> This guide will assist you in creating the necessary DNS records if your domain is managed by Cloudflare.

This guide will assist you in creating the necessary DNS records if your domain is managed by Cloudflare.

## Create Your Subdomain on the Sweego App

- Visit the **[Sweego App Domains Page](https://app.sweego.io/home/domains)**.

- Click on **"Add New Domain"** to create your subdomain.

![Domain Creation on Sweego App](undefined)

---

## Add DNS Records for Your Subdomain

- After clicking **"Add New Domain"**, the required DNS fields will be displayed.

- Go to your **Cloudflare manager** to create the **two mandatory CNAME records** necessary for sending emails with your subdomain.

![DNS Records Information](undefined)

---

### CNAME 1 / Sweego App:

![CNAME 1 from Sweego App](/img/docs/domains/cloudflare3.jpg)

### CNAME 1 / Cloudflare Manager:

![Adding CNAME in Cloudflare](undefined)

---

### CNAME 2 / Sweego App:

![CNAME 2 from Sweego App](/img/docs/domains/cloudflare5.jpg)

### CNAME 2 / Cloudflare Manager:

![Adding CNAME in Cloudflare](undefined)

---

## Verify Your Domain

Once you have added the DNS records, return to the **Sweego App** and click **"Verify Domain"**.

![Domain Verification](/img/docs/domains/cloudflare7.jpg)

If everything is set up correctly, you should see the message indicating that your subdomain has been verified.

![Domain Verified](undefined)

---

## Troubleshooting

- **Verification failed?**

This might be due to incomplete DNS propagation, which can take **24 to 48 hours**.

If the issue persists beyond this period, double-check your DNS records and ensure everything is correctly configured.

You can always re-check your DNS configuration by clicking the **"Reverify"** button in the Sweego App.
