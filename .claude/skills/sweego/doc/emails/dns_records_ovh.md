# DNS records with OVH

Source : https://learn.sweego.io/docs/emails/dns_records_ovh

> This guide will assist you in creating the necessary DNS records if your domain is managed by OVH.

This guide will assist you in creating the necessary DNS records if your domain is managed by OVH.

## Create Your Subdomain on the Sweego App

- Visit the **[Sweego App Domains Page](https://app.sweego.io/home/domains)**.

- Click on **"Add New Domain"** to create your subdomain.

![Domain Creation on Sweego App](undefined)

---

## Add DNS Records for Your Subdomain

- After clicking "Add New Domain," the required DNS fields will be displayed.

- Go to the OVH Manager to create the two mandatory CNAME records necessary for sending emails with your subdomain.
  ![DNS Records Information](undefined)

---

Section WebCloud Section / Select Your Domain / DNS Zone

- Add 2 Records:
  
  
  
  - Copy and paste the information from the Sweego App.
  
  - Important: Make sure to remove the main domain name from the field when pasting the subdomain information.

### CNAME 1 / Sweego App:

![CNAME 1 from Sweego App](/img/docs/domains/cloudflare3.jpg)

### CNAME 1 / Ovh Manager:

![CNAME 2 from Ovh App](/img/docs/domains/ovh2.jpg)

---

### CNAME 2 / Sweego App:

![CNAME 2 from Sweego App](/img/docs/domains/cloudflare5.jpg)

### CNAME 2 / Ovh Manager:

![CNAME 2 from Ovh App](/img/docs/domains/ovh3.jpg)

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
