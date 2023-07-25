# smtp2discord

This is an SMTP-to-Discord Webhook relay. Effectively, it's an SMTP server that listens for emails, and posts any received to a discord web hook. Just point your existing mail agents at it and it should work. 

## Setup
Setup pretty much just amounts to installing the dependencies from ```requirements.txt```, optionally in a virtual environment. 
If you want the server to run on startup, then you will have to find a way to create a service for your particular init system. 

You can also run the script in a Docker container. See [Docker Container](#docker-container).

## Usage

```
smtp2discord.py [-h] [-b BIND] [-p PORT] [-H] [-f FILECMD] [-a] webhook
```

## Options
- ```-a``` Attaches the original email file to the discord message so you can view it with a regular email client
- ```-b``` Sets the IP address for the server to bind to. 
- ```-p``` Sets the port for the server to listen to.
- ```-H``` Attaches a text file containing all of the headers
- ```-f``` Path to the executable for the ```file``` command, in case it isn't available on the path or has a different name
- ```-h``` Displays help information

## Troubleshooting

- The server must be run as root to listen on the default port.
- By default, the server listens on address ```127.0.0.1``` and port ```25```. These can be changed with the ```-b``` and ```-p``` options, respectively. 
- The shebang might need to be adjusted for your system
  - Changing the ```/usr/bin/env``` to whatever the output of ```command -v env``` is should work
  - If ```env``` isn't available on your system, then you can point it directly at the ```python3``` executable
  - If you change the shebang, then be sure the point it at your virtual environment if you are using one
- The ```file``` command is required to guess the ```Content-Type``` header. If it isn't available, then you might have some issues
  - A path to the ```file``` command can be given using the ```-f``` option

## Docker Container
In case you use docker, this script also supports being run as a docker container. The arguments may be passed as environmental variables.  
Run a container with
```
docker run -d -p 25:25 -e WEBHOOK=https://webhookurl -e BIND=0.0.0.0 limeparallelogram/smtp2discord
```
You can also use a docker-compose file if you prefer.
```yaml
services:
  main:
    image: limeparallelogram/smtp2discord
    environment:
      - WEBHOOK=https://webhookurl
      - BIND=0.0.0.0
    ports:
      - 25:25
```

The full list of environmental variables is as follows:  
| name | description | default |
| ---- | ----------- | ------- |
|\* WEBHOOK | Provide the discord webhook url | None |
| ATTACH | Attaches the original email file to the discord message so you can view it with a regular email client | False |
| BIND | Sets the IP address for the server to bind to | 127.0.0.1 |
| PORT | Sets the port for the server to listen on (Note: This is only internal to the container. In most cases you should change the left number in the ports section)  | 25 |
| SEND_HEADERS | Attaches a text file containing all of the headers | False |
| FILE_COMMAND | Path to the executable for the ```file``` command, in case it isn't available on the path or has a different name | file |

*Indicates a required variable