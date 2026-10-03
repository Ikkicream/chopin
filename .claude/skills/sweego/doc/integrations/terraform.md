# Terraform Provider

Source : https://learn.sweego.io/docs/integrations/terraform

> Manage your Sweego domains as infrastructure as code using the community Terraform provider

# Terraform Provider

The Sweego Terraform provider allows you to manage your Sweego domains as code. It is an open-source community project developed by [j6s](https://github.com/j6s) and available on GitHub.

With this provider, you can provision domains, retrieve the required DNS records (DKIM, DMARC, tracking, inbound), and integrate them directly into your existing Terraform infrastructure — for example by automatically creating the DNS records with your DNS provider.

## Prerequisites

Before starting, make sure you have:

- [Terraform](https://developer.hashicorp.com/terraform/install) installed (v1.x or higher)

- A Sweego account with an active API key and a Client ID

You can find how to create your Sweego API credentials in [our guide](/docs/auth/api_keys).

## Installation

The provider is published on the [Terraform Registry](https://registry.terraform.io/providers/j6s/sweego-provider/latest). Declare it in your Terraform configuration:

```hcl
terraform {
  required_providers {
    sweego = {
      source  = "j6s/sweego-provider"
      version = "~> 0.2"
    }
  }
}
```

Then run:

```bash
terraform init
```

## Configuration

Authenticate the provider using your Sweego API key and Client ID:

```hcl
provider "sweego" {
  api_key   = "YOUR_API_KEY"
  client_id = "YOUR_CLIENT_ID"
}
```

For security, avoid hardcoding credentials in your `.tf` files. Use variables or environment variables instead:

```hcl
provider "sweego" {
  api_key   = var.sweego_api_key
  client_id = var.sweego_client_id
}
```

## Resource: `sweego_domain`

The `sweego_domain` resource creates and manages a domain in your Sweego account. Once created, it exposes all the DNS records needed to verify the domain and enable sending.

### Example

```hcl
resource "sweego_domain" "example" {
  domain = "mail.yourdomain.com"
}
```

### Attributes

After applying, the resource exposes the following attributes:

| Attribute | Type | Description |
| --- | --- | --- |
| `domain` | string | Full domain name |
| `uuid` | string | Domain ID in Sweego |
| `is_verified` | bool | Whether the domain is verified |
| `tracking_click_enabled` | bool | Whether click tracking is enabled |
| `tracking_open_enabled` | bool | Whether open tracking is enabled |
| `domain_record` | object | CNAME record required to verify the domain |
| `dkim_record` | object | DKIM TXT record required to send emails |
| `dmarc_record` | object | DMARC TXT record required to send emails |
| `tracking_record` | object | CNAME record required for tracking |
| `inbound_record_list` | list | DNS records required to receive emails via inbound routing |

Each DNS record object (`DnsRecord`) contains:

| Field | Type | Description |
| --- | --- | --- |
| `type` | string | Record type (`TXT`, `CNAME`, etc.) |
| `name` | string | Record name, without the root domain |
| `data` | string | Record value |

## Example: Full domain setup with DNS records

The following example creates a Sweego domain and automatically provisions the required DNS records using a DNS provider (here `inwx` as an example — replace with your own DNS provider):

```hcl
resource "sweego_domain" "example" {
  domain = "mail.yourdomain.com"
}

# Verification CNAME
resource "inwx_nameserver_record" "sweego_domain_record" {
  domain  = "yourdomain.com"
  type    = resource.sweego_domain.example.domain_record.type
  name    = "${resource.sweego_domain.example.domain_record.name}.yourdomain.com"
  content = resource.sweego_domain.example.domain_record.data
}

# DKIM TXT record
resource "inwx_nameserver_record" "sweego_dkim" {
  domain  = "yourdomain.com"
  type    = resource.sweego_domain.example.dkim_record.type
  name    = "${resource.sweego_domain.example.dkim_record.name}.yourdomain.com"
  content = resource.sweego_domain.example.dkim_record.data
}

# DMARC TXT record
resource "inwx_nameserver_record" "sweego_dmarc" {
  domain  = "yourdomain.com"
  type    = resource.sweego_domain.example.dmarc_record.type
  name    = "${resource.sweego_domain.example.dmarc_record.name}.yourdomain.com"
  content = resource.sweego_domain.example.dmarc_record.data
}
```

The `name` attribute returned by the provider does not include the root domain. Depending on your DNS provider's Terraform resource, you may need to append the domain manually, as shown in the examples above.

## Importing an existing domain

If you already have a domain configured in Sweego and want to manage it with Terraform, you can import it using its UUID:

```bash
terraform import sweego_domain.example 3923bb62-f1e2-4362-ad1f-1af9f54d10f0
```

The UUID can be retrieved from the DNS record names visible in your Sweego domain settings.

## Additional Resources

- [terraform-provider-sweego-provider on GitHub](https://github.com/j6s/terraform-provider-sweego-provider)

- [Sweego Provider on Terraform Registry](https://registry.terraform.io/providers/j6s/sweego-provider/latest)

- [Sweego Domain Authentication Guide](/docs/emails/set_up_a_domain)
