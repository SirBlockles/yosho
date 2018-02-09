"""yosho plugin:chat moderator tools"""
import collections
import pickle
import re

from telegram import ChatAction as Ca
from telegram.ext import CommandHandler, RegexHandler, filters

from helpers import db_push, db_pull, clean, MODS

ENABLED_PATH = 'ENABLED.pkl'
db_pull(ENABLED_PATH)
ENABLED = set(pickle.load(open(ENABLED_PATH, 'rb')))

handlers = []


def sfw(bot, update, bot_globals):
    """toggles per-chat SFW setting"""
    chat = update.message.chat
    name = chat.title if chat.username is None else '@' + chat.username

    if name in bot_globals['SFW'].keys():
        bot_globals['SFW'][name] ^= True
    else:
        bot_globals['SFW'][name] = True

    pickle.dump(bot_globals['SFW'], open(bot_globals['SFW_PATH'], 'wb+'))
    db_push(bot_globals['SFW_PATH'])

    update.message.reply_text(text='Chat {} is SFW only: {}'.format(name, bot_globals['SFW'][name]))


handlers.append([CommandHandler("sfw", sfw), {'age': False, 'flood': False, 'admins': True, 'action': Ca.TYPING}])


def init(bot_globals):
    for i in ENABLED:
        enabled(None, None, bot_globals, do=i)


def enabled(bot, update, bot_globals, do=None):
    """allows chat mods to enable or disable plugin commands"""
    global ENABLED

    text = do[0] if do else update.message.text.lower()
    name = clean(text)

    if update:
        chat = update.message.chat
    else:
        chat = None

    chat_id = do[2] if do else chat.id

    if do:
        title = do[1]
    else:
        title = chat.title if chat.username is None else '@' + chat.username

    name = name[1:] if name.startswith('/') else name

    def match(name, aliases):
        if isinstance(aliases, list):
            return name in aliases
        else:
            return name == aliases

    found = False
    for i, h in enumerate(bot_globals['updater'].dispatcher.handlers[0]):
        if isinstance(h, (CommandHandler, RegexHandler)):
            if match(name, h.callback.__name__ if isinstance(h, RegexHandler) else h.command):
                if isinstance(h, RegexHandler):
                    update.message.reply_text(text="/{} is a RegexHandler command, "
                                                   "which don't support filters.".format(name))
                    return

                found = True

                if isinstance(h.filters, collections.Iterable):
                    h.filters = [f for f in h.filters if not (hasattr(f.or_filter, 'chat') and
                                                              f.or_filter.chat == chat_id)]

                chat_filter = filters.Filters.chat(chat_id)

                if text.startswith('/disable'):
                    chat_filter = ~chat_filter

                info = '{}d use of "/{}" in chat {}.'.format(text.split(' ')[0][1:], name, title)
                if not do:
                    update.message.reply_text(text=str.capitalize(info))
                bot_globals['logger'].debug(info)

                chat_filter = filters.Filters.user(MODS) | chat_filter

                if isinstance(h.filters, list):
                    h.filters.append(chat_filter)
                elif not h.filters:
                    h.filters = chat_filter
                else:
                    h.filters = [h.filters, chat_filter]

    if found and not do:
        if text.startswith('/disable'):
            ENABLED.add((text, title, chat_id))
        else:
            ENABLED -= {(re.sub('^/enable', '/disable', text), title, chat_id)}

        pickle.dump(list(ENABLED), open(ENABLED_PATH, 'wb+'))
        db_push(ENABLED_PATH)
    elif not do:
        update.message.reply_text(text='No plugin command "/{}" found.'.format(name))


handlers.append([CommandHandler(command=['disable', 'enable'], callback=enabled),
                 {'age': False, 'flood': False, 'admins': True, 'action': Ca.TYPING}])
