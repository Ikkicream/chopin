# Error codes

Source : https://learn.sweego.io/docs/api-error-codes

> Introduction

# API Error Codes

## Introduction

This documentation provides a comprehensive overview of the API error codes that developers may encounter when interacting with our system. Understanding these error codes is crucial for effective troubleshooting and proper handling of various scenarios.

## HTTP Status Codes

| Code | Description |
| --- | --- |
| 200 | Request handled successfully |
| 201 | Resource created |
| 204 | Request handled successfully without any data returned |
| 400 | Bad request (Usually malformed data provided) |
| 401 | Unauthorized |
| 403 | Access forbidden / restricted account |
| 404 | Resource not found |
| 409 | A conflict occurred while handling the request (may indicate a duplicated value) |
| 410 | Route is gone |
| 413 | Request size exceeds maximum size allowed |
| 418 | I'm a teapot |
| 422 | Request is missing attribute(s) or wrong attribute type |
| 422 | Field 'channel' is missing |
| 422 | Wrong 'channel' value |
| 422 | Either 'message-txt', 'message-html' or 'template-id' is required |
| 422 | You have to choose between 'message-html' and 'template-id' |
| 422 | Field 'headers' limited to 5 headers |
| 500 | Internal server Error |
| 500 | Unable to send message |
| 501 | Route not implemented yet |
| 501 | Channel not yet implemented |

## Conclusion

By familiarizing yourself with these error codes, you can efficiently address issues and improve the robustness of your integration with our API. If you encounter any issues not covered here, please refer to the API documentation or contact our support team for assistance.
