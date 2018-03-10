"""yosho plugin:plugin template"""
# Docstring must be of the format """yosho plugin:<plugin name>""" or plugin will be ignored.
from telegram import ChatAction

from utils.specialhandlers import DynamicCommandHandler

# Load order, higher loads later. For preventing plugin conflicts. Removing this defaults load order to 0.
order = -1

# List of telegram update handlers or [handler, group] lists.
handlers = []


def command(update):
    update.message.chat.send_action(ChatAction.TYPING)
    update.message.reply_text(text="Template plugin reply.")


handlers.append(DynamicCommandHandler('template_command', command))
