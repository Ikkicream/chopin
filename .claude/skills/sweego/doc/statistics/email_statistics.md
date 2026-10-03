# Email Statistics Overview

Source : https://learn.sweego.io/docs/statistics/email_statistics

> This documentation provides detailed explanations of statistics page and various metrics associated with the statuses of email deliveries. These metrics are crucial for assessing the performance of your email campaigns and ensuring effective deliverability.

This documentation provides detailed explanations of statistics page and various metrics associated with the statuses of email deliveries. These metrics are crucial for assessing the performance of your email campaigns and ensuring effective deliverability.

## Email Metrics Timeline

This diagram shows the different email metrics from a chronological point of view, from the server that sends the email to the server that receives it, right up to certain user actions.

![Hello](undefined)

## Metrics

***accepted:*** The number of emails that have been accepted by the recipient's mail server. This indicates that the message was successfully delivered without any issues.

***bounced:*** The number of emails that were bounced due to temporary or permanent issues on the recipient's mail server.

***complaints:*** The number of complaints received from recipients regarding the content or nature of the emails. Complaints may come from users who consider the messages unwanted or abusive.

***hardbounce:*** The number of emails that were bounced due to permanent issues, such as invalid email addresses or non-existent domains.

***softbounce:*** The number of emails that were bounced due to temporary issues, such as full inboxes or temporary errors from the recipient's mail server.

***list_unsubscribe:*** The number of e-mails that have generated a request to unsubscribe from the mailing list through the use of the "List-Unsubscribe" header. This indicates that the recipient no longer wishes to receive e-mails from the sender.

Note that this metric will only appear if you don't insert the "List-Unsubscribe" header yourself.

***rejected:*** The number of e-mails rejected by the recipient's mail server during the SMTP transaction. Unlike bounce messages, rejection notifications are generated during the initial connection between the sender's and recipient's servers, before the e-mail content is transmitted. This is usually due to strict filtering policies or invalid e-mail addresses.

***sent:*** The number of emails that were successfully sent, whether or not they were accepted by the recipient's mail server.

## Using the Metrics

It is recommended to regularly monitor these metrics to assess the health of your email campaigns. A thorough understanding of these statistics will enable you to optimize your sending strategies, reduce bounce rates, and maximize deliverability.

Feel free to adjust your campaigns based on feedback, minimizing complaints, addressing bounce errors, and maintaining a clean mailing list.
