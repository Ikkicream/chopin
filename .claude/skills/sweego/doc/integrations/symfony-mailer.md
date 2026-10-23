# Symfony Mailer & Notifier

Source : https://learn.sweego.io/docs/integrations/symfony-mailer

> Send emails and SMS from your Symfony applications using Sweego

# Symfony Mailer & Notifier

Sweego provides official Symfony components for sending emails and SMS messages directly from your Symfony applications.

## Available Components

Sweego offers two Symfony components:

- **[SweegoMailer](https://symfony.com/packages/SweegoMailer)**: For sending transactional emails

- **[SweegoNotifier](https://symfony.com/packages/SweegoNotifier)**: For sending SMS notifications

## Email Integration (Symfony Mailer)

### Installation

Install the Symfony Mailer component:

```bash
composer require symfony/mailer
```

The Sweego transport is automatically available when you install `symfony/mailer`.

### Configuration

Add the Sweego DSN to your `.env` file:

```bash
MAILER_DSN=sweego://YOUR_API_KEY@default
```

Or configure it directly in `config/packages/mailer.yaml`:

```yaml
framework:
    mailer:
        dsn: 'sweego://YOUR_API_KEY@default'
```

You can find how to configure your Sweego API key in [our guide](/docs/auth/api_keys).

### Sending Emails

Use the `MailerInterface` to send emails from your controllers or services:

```php
use Symfony\Component\Mailer\MailerInterface;
use Symfony\Component\Mime\Email;

class NewsletterController
{
    public function sendWelcomeEmail(MailerInterface $mailer): void
    {
        $email = (new Email())
            ->from('no-reply@example.com')
            ->to('user@example.com')
            ->subject('Welcome to Sweego!')
            ->text('Thank you for joining us.')
            ->html('<p>Thank you for joining us.</p>');

        $mailer->send($email);
    }
}
```

### Advanced Email Features

#### Attachments

```php
use Symfony\Component\Mime\Email;

$email = (new Email())
    ->from('no-reply@example.com')
    ->to('user@example.com')
    ->subject('Invoice')
    ->attachFromPath('/path/to/invoice.pdf')
    ->text('Please find your invoice attached.');
```

#### CC and BCC

```php
$email = (new Email())
    ->from('no-reply@example.com')
    ->to('user@example.com')
    ->cc('manager@example.com')
    ->bcc('archive@example.com')
    ->subject('Monthly Report');
```

#### Custom Headers

```php
$email = (new Email())
    ->from('no-reply@example.com')
    ->to('user@example.com')
    ->subject('Newsletter')
    ->getHeaders()
        ->addTextHeader('X-Custom-Header', 'value');
```

## SMS Integration (Symfony Notifier)

### Installation

Install the Symfony Notifier component and the Sweego notifier bridge:

```bash
composer require symfony/notifier symfony/sweego-notifier
```

### Configuration

Add the Sweego DSN to your `.env` file:

```bash
SWEEGO_DSN=sweego://YOUR_API_KEY@default
```

Configure the notifier in `config/packages/notifier.yaml`:

```yaml
framework:
    notifier:
        chatter_transports:
            sweego: '%env(SWEEGO_DSN)%'
```

### Sending SMS

Use the `ChatterInterface` to send SMS messages:

```php
use Symfony\Component\Notifier\ChatterInterface;
use Symfony\Component\Notifier\Message\ChatMessage;

class NotificationController
{
    public function sendSmsNotification(ChatterInterface $chatter): void
    {
        $message = new ChatMessage('Your verification code is: 123456');
        
        // Send to a specific phone number
        $message->options((new SweegoOptions())
            ->recipientId('+33612345678'));

        $chatter->send($message);
    }
}
```

### SMS Options

Configure SMS-specific options using `SweegoOptions`:

```php
use Symfony\Component\Notifier\Bridge\Sweego\SweegoOptions;
use Symfony\Component\Notifier\Message\ChatMessage;

$message = new ChatMessage('Your package has been shipped!');

$options = (new SweegoOptions())
    ->recipientId('+33612345678')
    ->from('YourBrand');

$message->options($options);

$chatter->send($message);
```

## Combined Notifications

You can combine multiple channels (email and SMS) using Symfony's notification system:

```php
use Symfony\Component\Notifier\NotifierInterface;
use Symfony\Component\Notifier\Notification\Notification;
use Symfony\Component\Notifier\Recipient\Recipient;

class OrderController
{
    public function sendOrderConfirmation(NotifierInterface $notifier): void
    {
        $notification = (new Notification('Order Confirmed'))
            ->content('Your order #12345 has been confirmed.')
            ->importance(Notification::IMPORTANCE_HIGH);

        $recipient = new Recipient(
            'user@example.com',
            '+33612345678'
        );

        // This will send both email and SMS
        $notifier->send($notification, $recipient);
    }
}
```

## Testing

### Testing Email Delivery

Symfony provides tools to test your email sending:

```php
use Symfony\Bundle\FrameworkBundle\Test\KernelTestCase;
use Symfony\Component\Mailer\MailerInterface;

class EmailTest extends KernelTestCase
{
    public function testEmailIsSent(): void
    {
        $mailer = self::getContainer()->get(MailerInterface::class);
        
        // Your email sending logic here
        
        $this->assertEmailCount(1);
        $this->assertEmailAddressContains('to', 'user@example.com');
    }
}
```

### Testing in Development

Use Symfony's mailer test mode during development:

```yaml
# config/packages/dev/mailer.yaml
framework:
    mailer:
        dsn: 'null://null'
```

## Troubleshooting

### Authentication Errors

If you receive authentication errors:

- Verify your API key is correct and active

- Ensure the API key has the necessary permissions

- Check that you're using the correct DSN format: `sweego://YOUR_API_KEY@default`

### Viewing Logs

Check Symfony logs for detailed error information:

```bash
tail -f var/log/dev.log
```

Enable verbose logging in development:

```yaml
# config/packages/dev/monolog.yaml
monolog:
    handlers:
        main:
            type: stream
            path: "%kernel.logs_dir%/%kernel.environment%.log"
            level: debug
```

### Email Not Received

- Check your email logs in the Sweego dashboard

- Verify the sender email is verified in Sweego

- Check spam/junk folders

- Ensure your domain has proper SPF/DKIM records configured

### SMS Not Delivered

- Verify the phone number format (E.164 format: +33612345678)

- Check your SMS quota in the Sweego dashboard

- Ensure the recipient's country is supported

- Verify your account has SMS credits

## Additional Resources

- [Symfony Mailer Documentation](https://symfony.com/doc/current/mailer.html)

- [Symfony Notifier Documentation](https://symfony.com/doc/current/notifier.html)

- [SweegoMailer Package](https://symfony.com/packages/SweegoMailer)

- [SweegoNotifier Package](https://symfony.com/packages/SweegoNotifier)

- [Sweego API Documentation](https://docs.sweego.io)
