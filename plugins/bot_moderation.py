"""yosho plugin:bot moderator tools"""
import logging
import pickle

from telegram import ChatAction as Ca
from telegram.error import TelegramError
from telegram.ext import CommandHandler

from helpers import clean, db_push

ORDER = 0

handlers = []


def die(bot, update):
    """kills bot"""
    update.message.reply_text(text='KMS')
    quit()


handlers.append([CommandHandler("die", die), {'mods': True, 'action': Ca.TYPING, 'level': logging.DEBUG}])


def leave(bot, update):
    """leaves specified chat/chatid"""
    chat = clean(update.message.text)
    try:
        if chat.replace('-', '').isnumeric():
            bot.leave_chat(chat_id=int(chat))
        else:
            bot.leave_chat(chat_id=chat)
        update.message.reply_text(text='Left chat {}.'.format(chat))
    except TelegramError:
        update.message.reply_text(text='Error leaving chat {}.\nMake sure chat name/id is valid!'.format(chat))


handlers.append([CommandHandler('leave', leave), {'mods': True, 'action': Ca.TYPING, 'level': logging.DEBUG}])


# TODO make this command less horrid
def set_global(bot, update, bot_globals):
    """sets or displays int/bool bot globals"""
    args = [a.strip() for a in clean(update.message.text).split('=')]
    names = (k for k, v in bot_globals.items() if isinstance(v, (int, bool)))
    listed = ('{} = {}'.format(k, v) for k, v in bot_globals.items() if isinstance(v, (int, bool)))

    if len(args) > 1:
        if args[0] in names:
            if str(args[1]).isnumeric():
                bot_globals['GLOBALS'][args[0]] = int(args[1])

                for k, g in bot_globals.items():
                    if isinstance(g, (int, bool)):
                        if k in bot_globals['GLOBALS'].keys():
                            bot_globals[k] = bot_globals['GLOBALS'][k]
                bot_globals['logger'].level = bot_globals['LOGGING_LEVEL']

                pickle.dump(bot_globals['GLOBALS'], open(bot_globals['GLOBALS_PATH'], 'wb+'))
                db_push(bot_globals['GLOBALS_PATH'])

                update.message.reply_text(text='Global {} updated.'.format(args[0]))
            else:
                update.message.reply_text(text='Globals type error.\n\nValue must be int.\nUse 1 or 0 for booleans.')
        else:
            update.message.reply_text(text='Globals key error.\n\nThat global does not exist.')
    elif args[0] == '':
        update.message.reply_text(text='Globals:\n\n' + '\n'.join(listed))
    else:
        update.message.reply_text(text='Globals syntax error.\n\nProper usage is /global <global> = <value>')


handlers.append([CommandHandler(['global', 'globals'], set_global), {'mods': True,
                                                                     'action': Ca.TYPING,
                                                                     'level': logging.DEBUG}])


def delet_this(bot, update):
    """delet this"""
    quoted = update.message.reply_to_message
    if quoted:
        try:
            quoted.delete()
        except TelegramError:
            return


handlers.append([CommandHandler("delet_this", delet_this), {'flood': False, 'mods': True}])
