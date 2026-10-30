# Retrieve email logs by Sftp

Source : https://learn.sweego.io/docs/sftp/how_to_use_sftp

> SFTP (Secure File Transfer Protocol) provides a secure way to transfer files between systems. This guide covers basic commands and usage for SFTP access.

# Sftp : Retrieve email logs

SFTP (Secure File Transfer Protocol) provides a secure way to transfer files between systems. This guide covers basic commands and usage for SFTP access.

## How do i get an SFTP access?

SFTP accesses are **not** created automatically with your account: they are provided **on request to our support
team** only. Contact our support team to ask for one, and we will set it up and send you your connection details.

## Where can i find my login details?

Once your access has been created, your Sftp connection details are sent to your contact email address.

If you've misplaced your connection details, don't hesitate to reach out to us and we'll get them back to you.

## Why are we providing you with sftp?

Sweego provides a SFTP server to access your mail sending datas such as :

- [logs](/docs/logs/email/sending)

- [feedback-loop](/docs/logs/email/feedback_loop)

- [list-unsubcribe](/docs/logs/email/list_unsubscribe)

Reports are made everyday in CSV format (Be sure to extract it from the archive).

You will find them in the `export` directory.

[Logs detail](/docs/logs/email/sending)

# Using SFTP Access

- [Connecting to a Server](#connecting-to-a-server)

- [Downloading a File](#downloading-a-file)

- [Graphical User Interface (GUI) Clients](#graphical-user-interface-gui-clients)

## Connecting to a Server

To connect to an SFTP server from the command line, use the following syntax:

```bash
sftp -P port username@hostname
```

Replace `port` with the server port, `username` with your server username and `hostname` with the server's IP address or domain.

Example:

```bash
sftp -P 2222 john@example.com
```

You will be prompted to enter your password.

## Downloading a File

To download a file from the server, use the `get` command:

```bash
sftp> get remotefile.txt localfile.txt
```

Replace `remotefile.txt` with the path to the remote file and `localfile.txt` with the desired local file name.

Example:

```bash
sftp> get documents/remotefile.txt /path/to/localfile.txt
```

## Graphical User Interface (GUI) Clients

If you prefer a graphical interface, several SFTP clients offer a user-friendly experience:

### FileZilla

- Download and install FileZilla from [filezilla-project.org](https://filezilla-project.org/).

- Open FileZilla and enter your server details:
  
  
  
  - Host: Your sftp server host
  
  - Username: Your sftp username
  
  - Password: Your sftp password
  
  - Port: Your sftp server port

- Click "Quickconnect" to establish a connection.

- Once connected, you can drag and drop files between the local and remote panes.

### WinSCP

- Download and install WinSCP from [winscp.net](https://winscp.net/).

- Launch WinSCP and enter your server details:
  
  
  
  - File protocol: SFTP
  
  - Host name: Your sftp server host
  
  - Port number: Your sftp server port
  
  - User name: Your server username
  
  - Password: Your server password

- Click "Login" to connect.

- Use the interface to navigate and transfer files between the local and remote directories.
