"""yosho plugin:plugin template"""  # docstring must be of the format """yosho plugin:<plugin name>"""
from telegram import ChatAction as Ca
from telegram.ext import CommandHandler

# Load order, higher loads later. For preventing plugin conflicts. Removing this defaults load order to 0.
ORDER = -1


# Include bot_globals as an optional argument if needed.
def command(bot, update):
    update.message.reply_text(text="Template plugin reply.")


# You may include init to be executed on plugin load. Include bot_globals as an optional argument if needed.
def init(bot_globals=None):
    bot_globals['logger'].info("Template plugin loaded.")  # Example usage of bot globals.


# Make sure to include a list of [handler, modifier] dict pairs if your plugin introduces new commands.

# Modifier dict values may include:
# age <bool>: Dictates if the bot should check if the command has expired or not. Defaults to True.
# name <bool|str>: If True, checks for bot's @name proceeding command. Defaults to False.
# -> If value is 'ALLOW_UNNAMED' will only block commands with incorrect bot @names proceeding them.
# mods <bool>: Only allow bot moderators to use command. Defaults to False
# flood <bool>: Check flood detector. Defaults to True.
# admins <bool>: Only allow chat administrators to execute this command. Defaults to False.
# nsfw <bool>: Only executes in chats not marked SFW. Defaults to False.
# action <ChatAction>: Action to send to chat while processing command. Defaults to None.
# level <logging.LEVEL aka int>: Console logging level to display when this command is processed. Defaults to INFO.

# NOTE: you may pass None instead of a modifier dict if you don't wish to use any modifiers.
handlers = [[CommandHandler('template_plugin', command), {'action': Ca.TYPING}]]
