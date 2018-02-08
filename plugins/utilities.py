"""yosho plugin:utility commands"""
from telegram import ChatAction as Ca
from telegram.ext import CommandHandler

handlers = []


def start(bot, update, bot_globals):
    if 'macro processor' in bot_globals['PLUGINS'].keys():
        update.message.text = '/start_info' + bot.name.lower()
        bot_globals['PLUGINS']['macro processor'].call_macro(bot, update, bot_globals)
    else:
        update.message.reply_text(text='Yosho bot by @TeamFortress and @WyreYote')


handlers.append([CommandHandler('start', start), {'action': Ca.TYPING, 'name': True, 'age': False}])


def list_plugins(bot, update, bot_globals):
    update.message.reply_text(text='Installed plugins:\n'+'\n'.join(bot_globals['PLUGINS'].keys()))


handlers.append([CommandHandler('plugins', list_plugins), {'action': Ca.TYPING}])
