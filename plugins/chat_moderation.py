"""yosho plugin:chat moderator tools"""
import pickle

from telegram import ChatAction as Ca
from telegram.ext import CommandHandler

from helpers import db_push

ORDER = 0


# noinspection PyUnusedLocal
def sfw(bot, update, bot_globals=None):
    chat = update.message.chat
    name = chat.title if chat.username is None else '@' + chat.username
    if name in bot_globals['SFW'].keys():
        bot_globals['SFW'][name] ^= True
    else:
        bot_globals['SFW'][name] = True
    pickle.dump(bot_globals['SFW'], open(bot_globals['SFW_PATH'], 'wb+'))
    db_push(bot_globals['SFW_PATH'])
    update.message.reply_text(text='Chat {} is SFW only: {}'.format(name, bot_globals['SFW'][name]))


handlers = [[CommandHandler("sfw", sfw), {'flood': False, 'admins': True, 'action': Ca.TYPING}]]
