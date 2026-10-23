# Custom headers

Source : https://learn.sweego.io/docs/emails/headers/custom_headers

> This documentation outlines the use of custom headers for personalizing email delivery in our SaaS email sending application. Custom headers provide a flexible way to tailor the behavior of email delivery and gather additional information for tracking and analysis. Below are the predefined headers along with instructions for customization.

This documentation outlines the use of custom headers for personalizing email delivery in our SaaS email sending application. Custom headers provide a flexible way to tailor the behavior of email delivery and gather additional information for tracking and analysis. Below are the predefined headers along with instructions for customization.

You can add headers with SMTP or by API as shown in the examples below.

## Predefined Headers

### x-swg-dry-run

**Description:** If set to `true`, this header prevents the email from being sent to the address specified in the "To:" header. Instead, it redirects the flow to an internal server for testing purposes.

**Format:** `x-swg-dry-run: bool`

**SMTP Example:**

```
x-swg-dry-run: yes
```

**API Example (JSON):**

```json
{
    "dry-run": true
}
```

---

### x-campaign-id

**Description:** Associates the email with a custom campaign identifier of your choice. This value is recorded in the logs and can be used to group and filter messages by campaign.

**Format:** `x-campaign-id: string`

**SMTP Example:**

```
x-campaign-id: my-campaign-2024
```

**API Example (JSON):**

```json
{
    "campaign-id": "my-campaign-2024"
}
```

---

### x-campaign-tags

**Description:** Allows you to insert tags that will be recorded in the logs for campaign tracking. Limited to 5 tags. Each tag must be between 1 and 20 characters and may only contain the following characters: `[A-Za-z0-9-]`.

**Format:** `x-campaign-tags: string`

**SMTP Example:**

```
x-campaign-tags: "billing,a-tag"
```

**API Example (JSON):**

```json
{
    "campaign-tags": ["billing", "a-tag"]
}
```

---

### x-campaign-type

**Description:** Specifies the type of email. Accepted values are `transac`, `newsletter`, and `market`.

**Format:** `x-campaign-type: string`

**SMTP Example:**

```
x-campaign-type: transac
```

**API Example (JSON):**

```json
{
    "campaign-type": "transac"
}
```

---

### x-swg-dis-t-o

**Description:** if this header is added, it will disable open tracking for this email

**Format:** `x-swg-dis-t-o: yes`

**API Example (JSON):**

```json
{
  "tracking_open": false
}
```

---

## Custom Headers

### X-Your-Custom-Header

**Description:** You can add up to five (5) custom headers starting with `X-` to gather additional information for tracking. These headers will be recorded in the logs.

When using the API, the `X-` prefix is stripped automatically. Pass your headers in the `headers` object without the `X-` prefix, as shown in the example below.

**Format:** `X-Your-Custom-Header: string`

**SMTP Example:**

```
X-Ref-1: 643524
X-Ref-2: lervcn
X-Ref-3: o10icr
```

**API Example (JSON):**

```json
{
    "headers": {
        "Ref-1": "643524",
        "Ref-2": "lervcn",
        "Ref-3": "o10icr"
    }
}
```

---

## Usage Guidelines

- Ensure that headers are correctly formatted and follow the specified examples.

- Custom headers starting with `X-` must not exceed a maximum of five (5).

- Utilize these headers to tailor email campaigns, track specific information, and enhance analysis.

---

## Example Use Case

Suppose you want to test an email without sending it to the actual recipient, associate it with a campaign ID, tag it as part of the "billing" campaign, specify it as a transactional email, and include additional custom information for billing tracking:

**SMTP Example:**

```
x-swg-dry-run: yes
x-campaign-id: billing-2024
x-campaign-tags: "billing"
x-campaign-type: transac
X-Bill-Id: 643524
X-Bill-Due-Date: 20231120
X-Customer-Id: 424242
```

**API Example (JSON):**

```json
{
    "dry-run": true,
    "campaign-id": "billing-2024",
    "campaign-tags": ["billing"],
    "campaign-type": "transac",
    "headers": {
        "Bill-Id": "643524",
        "Bill-Due-Date": "20231120",
        "Customer-Id": "424242"
    }
}
```

In this example, the email will not be sent to the recipient specified in the "To:" header but will be redirected for internal testing. It will be associated with the campaign ID `billing-2024`, tagged as part of the "billing" campaign, identified as a transactional email, and include additional custom billing information.
