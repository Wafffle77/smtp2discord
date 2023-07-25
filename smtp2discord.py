#!/usr/bin/env python3

import aiohttp, pyrfc6266, mimetypes, signal, argparse, yarl
from aiosmtpd.controller import Controller
from aiosmtpd.handlers import AsyncMessage
from aiosmtpd.smtp import SMTP
from email.message import Message
from subprocess import check_output
import os

def getContentType(msg: Message, fileCmd="file"):
  # Just return the content type if it is already specified
  if "Content-Type" in msg:
    return msg["Content-Type"]
  # Try and guess the type based on the payload
  else:
    data = msg.get_payload(decode=True)
    if type(data) == str: data = data.encode()
    try:
      return check_output([fileCmd, "-b", "--mime", "-"], input=data)
    except FileNotFoundError:
      print("WARNING: 'file' command not found. Unable to guess MIME types. Defaulting to 'text/plain'.")
      return "text/plain"
  
def getMailType(msg: Message, fileCmd="file"):
  # Get the Content-Type header
  contentType = getContentType(msg, fileCmd)
  # Initialize a new Message object because apparantly that's the offically reccommened way to parse Content-Type headers with python now
  temp = Message()
  temp["Content-Type"] = contentType

  # Get the type from the message
  return temp.get_params()[0][0]

async def processMessage(message: Message) -> list[Message]:
  # Initialize return list
  ret = []

  # If the message is multipart, then recurse over all of its parts
  if message.is_multipart():
    # Iterate over every payload of the message
    for payloadMessage in message.get_payload():
      ret.extend(await processMessage(payloadMessage))
  # If the message is not, then return it
  else:
    ret.append(message)
  
  return ret

def guessMessageFilename(msg: Message, fileIndex = 0, mailType = None, fileCmd="file"):
  # Check and see if the message has a Content-Disposition header
  if "Content-Disposition" in msg:
    # Check if the Content-Disposition header has a name for us
    filename = pyrfc6266.parse_filename(msg["Content-Disposition"])
    # If it does, then just return that name and be done with it
    if filename: 
      return filename, True
  
  # If there isn't a Content-Disposition header or it doesn't have a name, then make one up
  filename = f"File_{fileIndex}" # Very creative name

  # Guessing the type if one isn't provided
  if not mailType:
    mailType = getMailType(msg, fileCmd=fileCmd)
  
  # Try to guess the extension, and assume that the file is text if it isn't recognized. This surely won't come back to bite me later
  filename += mimetypes.guess_extension(mailType) or ".txt" 

  # Return our newly generated filename
  return filename, False

class Smtp2DiscordHandler(AsyncMessage):
  def __init__(self, webhookURL, sendHeaders=False, wait=False, fileCmd="file", attachOriginal=False, **kwargs):
    self.webhookURL  = webhookURL
    self.sendHeaders = sendHeaders
    self.wait = wait
    self.fileCmd = fileCmd
    self.attachOriginal = attachOriginal

    self.messages = []
    super().__init__(**kwargs)

  async def handle_message(self, message: Message):
    with aiohttp.MultipartWriter("form-data") as mp:
      # Process the multipart message to get a flat list of attachments
      attachmentList = await processMessage(message)
      
      # Initialize some variables for body content
      writtenContent = False

      for i, messagePart in enumerate(attachmentList):
        # Get the message payload for later use
        data = messagePart.get_payload(decode=True)

        # Get the mime type
        messageType = getMailType(messagePart, fileCmd=self.fileCmd)

        # Get the filename
        messageName, hasName = guessMessageFilename(messagePart, fileIndex=i, mailType=messageType)

        # If the file doesn't have a name and there hasn't been any body content yet, then use this file as the body
        if not hasName and not writtenContent:
          # Decode the data into a string for future ease of use
          contentString: str = data.decode()

          # Prepend the message subject as a nice big title
          if "Subject" in message:
            subject = message["Subject"]
            contentString = f"# {subject}\r\n" + contentString

          # If the content is longer than discord's limit of 2000, then truncate it and inform the user
          if len(contentString) > 2000:

            # Initialize the overflow string
            overflowString = f"\nMessage Body Overflow into {messageName}"

            # Create a new content part of the message
            contentPart = mp.append(contentString[:2000 - len(overflowString)] + overflowString, {"Content-Type": messageType})
            # Set the Content-Disposition header for the discord message body
            contentPart.set_content_disposition("form-data", name=f"content")

            # Get the multipart writer ready
            filePart = mp.append(contentString, {"Content-Type": messageType})
            # Set the Content-Disposition header for the attached body file
            filePart.set_content_disposition("form-data", name=f"files[{i}]", filename=messageName)
          else:
            # Move the content part over since no truncation is needed
            contentPart = mp.append(contentString, {"Content-Type": messageType})
            # Set the Content-Disposition header for the discord message body
            contentPart.set_content_disposition("form-data", name=f"content")

          # Set the flag for body content being written
          writtenContent = True
        else:
          # Get the multipart writer ready
          filePart = mp.append(data, {"Content-Type": messageType})

          # Set the Content-Disposition header for the discord file attachments
          filePart.set_content_disposition("form-data", name=f"files[{i}]", filename=messageName)

      # Set the username for discord based on the sender of the email
      if "X-MailFrom" in message:
        usernamePart = mp.append(message["X-MailFrom"])
        usernamePart.set_content_disposition("form-data", name="username")
      elif "From" in message:
        usernamePart = mp.append(message["From"])
        usernamePart.set_content_disposition("form-data", name="username")
      
      # If enabled, then send the headers in a txt attatchment, for reference
      # Also make it look nice
      if self.sendHeaders:
        keyColumnLength = max(*map(len, message.keys()))
        headerBlock = mp.append('\n'.join(f"{key.ljust(keyColumnLength)} {value}" for key, value in message.items()))
        headerBlock.set_content_disposition("form-data", name=f'files[{len(attachmentList)}]', filename="headers.txt")
      
      # If enabled, attach the original email to the message
      if self.attachOriginal:
        emailPart = mp.append(message.as_bytes(), {"Content-Type": "multipart/rfc822"})
        emailPart.set_content_disposition("form-data", name=f'files[{len(attachmentList)+1}]', filename="message.eml")

      async with aiohttp.ClientSession() as session:
        async with session.post(self.webhookURL, data=mp, params={"wait": "true" if self.wait else "false"}) as response: 
          if self.wait: self.messages.append(await response.json())

class Smtp2DiscordController(Controller):
  def factory(self):
    return SMTP(self.handler)


def parseArgs(args = None):
  parser = argparse.ArgumentParser()

  WEBHOOK = os.environ.get("WEBHOOK", None)
  FILE_CMD = os.environ.get("FILE_COMMAND", "file")
  BIND = os.environ.get("BIND", "127.0.0.1")

  # Additional error checking for type conversion
  SEND_HEADERS = os.environ.get("SEND_HEADERS", "False").lower() in ('true', '1', 't')
  ATTACH = os.environ.get("ATTACH", "False").lower() in ('true', '1', 't')
  try:
    PORT = int(os.environ.get("PORT", 25))
  except ValueError:
    print("Invalid type provided for PORT. Using default 25")
    PORT = 25

  parser.add_argument("webhook",          action="store",      type=yarl.URL,            help="Webhook URL to forward messages to", default=WEBHOOK, nargs="?" if WEBHOOK else 1) # Allow exclusion of positional argument where environment variable set
  parser.add_argument("-b", "--bind",     action="store",      type=str,                 help="Address to bind the SMTP server to",           default=BIND)
  parser.add_argument("-p", "--port",     action="store",      type=int,                 help="Port for the SMTP server to listen on",        default=PORT)
  parser.add_argument("-H", "--headers",  action="store_true",                           help="Send the headers of each email as an additional attachment", default=SEND_HEADERS)
  parser.add_argument("-f", "--file-cmd", action="store",      type=str, dest="fileCmd", help="Path to an executable for the 'file' command", default=FILE_CMD)
  parser.add_argument("-a", "--attach",   action="store_true",                           help="Attach a copy of the original email to the message", default=ATTACH)

  return parser.parse_args(args)

if __name__ == "__main__":
  args = parseArgs()
  controller = Smtp2DiscordController(Smtp2DiscordHandler(args.webhook, sendHeaders=args.headers, fileCmd=args.fileCmd), args.bind, args.port)

  # Start the listener
  controller.start()
  print("Running SMTP-Discord relay on:", controller.hostname, controller.port)
  print("Press Ctrl-C to stop the server")

  # Wait for a signal to exit, and catch the expected keyboard interrupt
  try: signal.pause()
  except KeyboardInterrupt: pass

  controller.stop()