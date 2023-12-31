from smtp2discord import Smtp2DiscordController, Smtp2DiscordHandler
from glob import glob
import smtplib, aiohttp, asyncio

from secret import WEBHOOK_URL

async def deleteHandlerMessages(handler):
  async with aiohttp.ClientSession() as session:
    for message in handler.messages:
      if "id" in message: 
        async with session.delete(WEBHOOK_URL + "/messages/" + message["id"]): pass

handler = Smtp2DiscordHandler(WEBHOOK_URL, attachOriginal=True, wait=True)
controller = Smtp2DiscordController(handler, "127.0.0.1", 2525)
controller.start()
print(controller.hostname, controller.port)

server = smtplib.SMTP("127.0.0.1", 2525)
try:
  for emailFile in glob("*.eml"):
    with open(emailFile, "rb") as messageFile:
      server.sendmail("test@asdf.lan", "test2@asdf.lan", messageFile.read())
finally:
  input("Press RETURN to delete test messages and stop server")
  
  asyncio.run(deleteHandlerMessages(handler))
  
  controller.stop()