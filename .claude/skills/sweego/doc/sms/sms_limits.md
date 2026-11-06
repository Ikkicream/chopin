# Rules for sms

Source : https://learn.sweego.io/docs/sms/sms_limits

> Specific limits and rules govern the use of SMS.

Specific limits and rules govern the use of SMS.

### SenderId

- In France, it is possible to use either a numeric or alphanumeric Sender ID.

- For countries outside of France, it is strongly recommended to use an alphanumeric Sender ID."

### Displayed Numbers for Received SMS

The number displayed on the received SMS (if the Sender ID has not been defined) will be:

- 38082 for transactional SMS messages

- 36047 for marketing SMS messages

Please note that the number displayed on the client's received SMS may vary, especially depending on the volume of SMS sent.
However, in the app logs, the displayed number will always be 38082 or 36047."

### Number of Characters in an SMS

An SMS allows for a maximum of 160 characters per message.

This limit includes spaces, punctuation, and special characters.

If the message exceeds 160 characters, it is typically split into multiple segments, each within the 160-character limit, and sent as a concatenated message.

Each segment counts as 1 SMS in terms of cost.

For example, if you write an SMS with 2 segments, the message will cost you 2 SMS per recipient.

### Special characters

In an SMS, the 160-character limit applies to messages using the standard GSM-7 encoding, which supports basic Latin characters and some special characters.

However, if the message includes special characters like accented letters, non-Latin scripts, or emojis, the encoding often switches to UCS-2, which supports a wider range of characters but reduces the character limit to 70 per message.

Keep in mind, not all special characters are equal! Each special character impacts the overall number of remaining characters differently.

In the Sweego UI, as you create your template, we show you the number of characters remaining on your current SMS and the total number of SMS you’ll be charged for per recipient.

### Using links in SMS

When including links in SMS messages, there are a few important rules and best practices to keep in mind:

- Character Count: Links count toward the SMS character limit, which is typically 160 characters for standard messages or 70 characters if special characters are used. Using long URLs can quickly eat up this limit, so it's often better to use shortened URLs.

- Short Links: Shortened links are useful for conserving space. However, be aware that some carriers or spam filters may flag or block SMS messages containing short links due to their potential association with phishing. In addition, some countries have regulations that restrict or block the use of short links due to concerns with fraudulent activities. With Sweego, you can choose to enable or disable short links when you send your SMS.

- Compliance: When using links in SMS, make sure you are following the regulations of your destination country or countries. In particular, check rules on the use of shortlinks and opt-out options in marketing messages. Failing to comply can result in fines or your messages being blocked by carriers.

### Stop SMS

As we’ve seen, there are two types of messages: transactional and marketing.
For marketing messages, 'STOP XXXX' will automatically be added to your SMS if the destination country is France, as this is mandatory for marketing SMS in France. Otherwise, 'STOP XXXX' will not be added.
