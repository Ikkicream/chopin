# Create Templates

Source : https://learn.sweego.io/docs/templates/create

> With Sweego, you have the ability to create email templates

With Sweego, you have the ability to create email templates

To create a template, follow these steps:

- Navigate to the Templates section in the App.

![access email templates](undefined)

- Click on Create template

![create template](undefined)

## Methods

There are 2 methods available :

- [Import from html](/docs/templates/create#html-import): If you want to import your own html that you're already using

- [Create from scratch](/docs/templates/create#create-from-scratch): If you want to create your template step by step

![choose template mode](undefined)

### HTML Import

Below is an example with html import

Here you can copy paste your html template.
![html import](undefined)

Code example:

**[Html]**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Template</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f4f4f4;
            color: #333;
        }
        .container {
            width: 80%;
            margin: 0 auto;
            padding: 20px;
            background-color: #fff;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
            border-radius: 5px;
            margin-top: 20px;
        }
        h1 {
            text-align: center;
            margin-bottom: 20px;
        }
        p {
            line-height: 1.6;
        }
        .footer {
            text-align: center;
            margin-top: 20px;
            padding-top: 10px;
            border-top: 1px solid #ccc;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Hello, World!</h1>
        <p>This is a sample HTML template.</p>
        <p>You can customize it according to your needs.</p>
    </div>
    <div class="footer">
        <p>Copyright &copy; 2024. All rights reserved.</p>
    </div>
</body>
</html>
```

Click on import.
Now you can see your template result : with mobile or Desktop view

| ![Siamese cat](/assets/images/sweego_desktop_preview-fd15c4c31485ef89f5915bb00379f614.png) | ![Siamese cat](/assets/images/sweego_mobile_preview-e729f9edcb63f2e2e559263524ca253b.png) |

### Create from scratch

Simply drag and drop the element you want to add to the template (Content)

You can customise your email template using the left tab

`{"className": "react-player", "url": "/video/video.mp4", "width": "100%", "height": "100%", "controls": "rue"}`

Don't forget to save your templates!

#### Related

🔗 [More details on template use](/docs/sweego/send-send-post)
