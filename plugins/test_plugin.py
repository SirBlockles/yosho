"""yosho plugin:test plugin"""
from telegram import ChatAction as Ca
from telegram.ext import CommandHandler

ORDER = 0


# noinspection PyUnusedLocal
def test(bot, update, bot_globals):
    update.message.reply_text(text='Plugins are working.')


handlers = [[CommandHandler('plugintest', test), {'action': Ca.TYPING}]]
