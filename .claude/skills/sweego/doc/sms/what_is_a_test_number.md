# What is a Test Number?

Source : https://learn.sweego.io/docs/sms/what_is_a_test_number

> To begin sending SMS, click on the card “SMS with Sweego” on the homepage of the application, and you’ll be taken to the first step to set up this channel: indicating a test number.

To begin sending SMS, click on the card “SMS with Sweego” on the homepage of the application, and you’ll be taken to the first step to set up this channel: indicating a test number.

A test number is the phone number at which you’ll receive test SMS messages, allowing you to preview what the message will actually look like, with sender name, text, links, etc.

It helps you make sure your SMS is perfect before sending it out to your contacts.

Just select the country for your phone number and we’ll check that it’s in the correct format for you.

A test number is mandatory to setting up the SMS channel.

You can come back and change it later if you need to.

![sms](undefined)

After you’ve saved a test number, you can either:

- Go to the “Sender ID” tab and indicate a custom sender name, which will help your contacts recognize you. A custom Sender ID is optional. If you don’t indicate a custom Sender ID, we will attribute a short number as the sender. Or,

- Go to “Credentials”, and under the API tab, either create a new API Key for SMS or use an existing API Key. Our API Keys are multichannel, so you can use them for both email and SMS if you wish.

Once you know which Sender ID you’ll be using (custom, or an attributed short number), and you’ve got your API Key in order, you can start sending SMS (and tests!) with an API call.
