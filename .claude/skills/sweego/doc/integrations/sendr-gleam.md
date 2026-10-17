# sendr (Gleam)

Source : https://learn.sweego.io/docs/integrations/sendr-gleam

> Send emails from Gleam applications through Sweego using the sendr library

# sendr (Gleam)

[sendr](https://hex.pm/packages/sendr) is a community email library for [Gleam](https://gleam.run/) that unifies email sending across multiple providers behind a single message-building API. Sweego support is provided by the companion package **`sendr_sweego`**.

It is an open-source project developed by [schutm](https://www.wommm.nl/cv/) and published on Hex under the ISC license.

## Prerequisites

Before starting, make sure you have:

- A Gleam project ([installation guide](https://gleam.run/getting-started/installing/))

- A Sweego account with an active API key

- A verified sending domain (or sender) in Sweego

You can find how to create your Sweego API key in [our guide](/docs/auth/api_keys).

## Installation

Add both the core library and the Sweego backend to your project:

```sh
gleam add sendr sendr_sweego
```

## Usage

Build a message with `sendr`'s builders, configure the Sweego backend with your API key, then generate and send the HTTP request:

```gleam
import sendr/message
import sendr/mailbox
import sendr/body
import sendr_sweego

pub fn main() {
  // Configure the Sweego backend with your API key
  let cfg = sendr_sweego.config("YOUR_API_KEY")

  // Build the message
  let msg =
    message.new()
    |> message.set_from(mailbox.new("Alice", "alice@example.com"))
    |> message.set_to([mailbox.new("Bob", "bob@example.com")])
    |> message.set_subject("Hello from sendr_sweego")
    |> message.set_body(body.new() |> body.set_text("Hello world!"))

  // Turn the message into an HTTP request, send it with your HTTP client,
  // then process the response
  let request = sendr_sweego.request(msg, cfg)
  // send `request` with your HTTP client of choice, then:
  // let result = sendr_sweego.response(resp)
}
```

The typical workflow is:

- Build a message using `sendr`'s builder functions

- Call `sendr_sweego.request(msg, cfg)` to generate the HTTP request

- Send the request with your HTTP client

- Process the response with `sendr_sweego.response(resp)`

Sweego supports a single `reply_to` address. If more than one is provided, `sendr_sweego` returns an `Error`.

## Additional Resources

- [sendr_sweego documentation (HexDocs)](https://sendr-sweego.hexdocs.pm/)

- [sendr documentation (HexDocs)](https://sendr.hexdocs.pm/)

- [sendr on Hex](https://hex.pm/packages/sendr)

- [Source repository](https://tangled.sh/wommm.nl/sendr)
