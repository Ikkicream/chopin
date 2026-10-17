# Attachments

Source : https://learn.sweego.io/docs/emails/attachments

> The maximum size allowed for emails, including attachments and email content, is 20 MB.

# Maximum Email Size for Transactional Emails

The maximum size allowed for emails, including attachments and email content, is **20 MB**.

If your email exceeds this limit, we recommend hosting the file externally and providing a public link to the file within the email.

---

## Allowed Formats for Files in Attachments

| **Extension** | **File Type** |
| --- | --- |
| 7z | Compressed archive |
| adoc | Signed document container (Estonia) |
| asice | Signed document container (ASiC-E) |
| bdoc | Estonian signed document container |
| bmp | Bitmap image |
| cdoc | Encrypted document container |
| csv | Comma-separated values file |
| ddoc | Legacy Estonian signed document container |
| doc | Microsoft Word document |
| docx | Microsoft Word document (OpenXML) |
| edoc | Electronic signed document container |
| epub | EPUB e-book |
| gif | GIF image |
| jpeg | JPEG image |
| jpg | JPEG image |
| json | JSON file |
| md | Markdown file |
| mobi | MOBI e-book |
| odp | OpenDocument presentation |
| ods | OpenDocument spreadsheet |
| odt | OpenDocument text document |
| pdf | PDF document |
| png | PNG image |
| ppt | Microsoft PowerPoint presentation |
| pptx | PowerPoint presentation (OpenXML) |
| rar | Compressed RAR archive |
| rtf | Rich Text Format document |
| svg | Scalable Vector Graphics image |
| tar.gz | Compressed TAR GZ archive |
| tiff | TIFF image |
| txt | Text file |
| xls | Microsoft Excel spreadsheet |
| xlsx | Excel spreadsheet (OpenXML) |
| xml | XML file |
| yaml | YAML file |
| yml | YAML file (alternative extension) |
| zip | Compressed ZIP archive |

---

## Using the API ior SMTP to Include Attachments

Using our API and SMTP, you can either include files that you have hosted externally or directly attach base64-encoded files in your API/SMTP request.
