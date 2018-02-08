import csv
import datetime
import functools
import inspect
import logging
import os
import pickle
import re
import time
from importlib import import_module

import telegram
from telegram import ChatAction as Ca
from telegram.ext import Updater, CommandHandler

from helpers import is_mod, db_pull

TOKEN_DICT = [l for l in csv.DictReader(open('tokens.csv', 'r'))][0]
TELEGRAM_TOKEN = TOKEN_DICT['yosho_bot']
WOLFRAM_TOKEN = TOKEN_DICT['wolfram']

SFW_PATH = 'SFW.pkl'
db_pull(SFW_PATH)
SFW = pickle.load(open(SFW_PATH, 'rb'))

GLOBALS_PATH = 'GLOBALS.pkl'
db_pull(GLOBALS_PATH)
GLOBALS = pickle.load(open(GLOBALS_PATH, 'rb'))

# defaults
LOGGING_LEVEL = logging.DEBUG
MESSAGE_TIMEOUT = 60
FLOOD_TIMEOUT = 20
EVAL_MEMORY = True
EVAL_TIMEOUT = 1
EVAL_MAX_OUTPUT = 128
EVAL_MAX_INPUT = 1000
FLUSH_INTERVAL = 60 * 10
IMAGE_SEND_TIMEOUT = 40


bot = telegram.Bot(token=TELEGRAM_TOKEN)
updater = Updater(token=TELEGRAM_TOKEN)
jobs = updater.job_queue
logging.basicConfig(format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)

last_commands = dict()

PLUGINS = dict()


def load_globals():
    for k, g in globals().items():
        if isinstance(g, (int, bool)):
            if k in GLOBALS.keys():
                globals()[k] = GLOBALS[k]
    logger.level = LOGGING_LEVEL


load_globals()


# message modifiers decorator
# name checks if correct bot @name is present if value is True, also passes unnamed commands if value is ALLOW_UNNAMED
# mods is bot mods, admin is chat admins/owner
def modifiers(method=None, age=True, name=False, mods=False, flood=True, admins=False, nsfw=False, action=None,
              level=logging.INFO):
    if method is None:  # if method is None optional arguments have been passed, return usable decorator
        return functools.partial(modifiers, age=age, name=name, mods=mods, flood=flood,
                                 admins=admins, nsfw=nsfw, action=action, level=level)

    @functools.wraps(method)
    def wrap(*args, **kwargs):  # otherwise wrap function and continue
        global last_commands
        message = args[1].message
        user = message.from_user
        n = re.match('/\w+(@\w+)\s', message.text + ' ')  # matches "/command@bot"
        message_bot = (n.group(1).lower() if n else None)  # bot @name used in command if present
        message_user = user.username if user.username is not None else user.name  # name of OP/user of command
        message_age = (datetime.datetime.now() - message.date).total_seconds()  # age of message in minutes
        chat = message.chat
        title = chat.title if chat.username is None else '@' + chat.username

        if chat.type == 'private':
            admins_list = [message_user]
        else:
            admins_list = [x.user.username for x in bot.getChatAdministrators(chat_id=message.chat_id,
                                                                              message_id=message.message_id)]

        # check incoming message attributes
        time_check = not age or message_age < MESSAGE_TIMEOUT
        name_check = any((not name,
                          chat.type == 'private',
                          message_bot == bot.name.lower(),
                          message_bot is None and name == 'ALLOW_UNNAMED'))
        mod_check = not mods or is_mod(message_user)
        admin_check = (not admins or message_user in admins_list) or is_mod(message_user)
        nsfw_check = not nsfw or (title in SFW.keys() and not SFW[title])
        if all((time_check, name_check, mod_check, admin_check, nsfw_check)):

            logger.log(level, '{} command called from {} -> {{{}, {}}}, user: @{}, with message: "{}"'
                       .format(method.__name__, chat.type, title, chat.id, message_user, message.text))

            # flood detector
            start = time.time()
            if flood and not chat.type == 'private':
                if message_user in last_commands.keys() and not is_mod(message_user):
                    elapsed = start - last_commands[message_user]
                    if elapsed < FLOOD_TIMEOUT:
                        if bot.username in admins_list:
                            bot.deleteMessage(chat_id=message.chat_id, message_id=message.message_id)
                        else:
                            bot.send_message(chat_id=message.chat_id, reply_to_message_id=message.message_id,
                                             text="There's a {} second cooldown between commands!\n"
                                                  "Mod me for automatic flood deletion.".format(FLOOD_TIMEOUT))

                            logger.debug("flood detector couldn't delete command")

                        logger.info('message canceled by flood detector: ' + str(elapsed))
                        return
                last_commands[message_user] = time.time()

            if action:
                args[0].sendChatAction(chat_id=message.chat_id, action=action)

            method(*args, **kwargs)
            end = time.time()

            logger.debug('time elapsed (seconds): ' + str(end - start))

    return wrap


def load_plugins():
    global PLUGINS

    def globals_sender(method):
        def wrapper(*args, **kwargs):
            return method(*args, globals(), **kwargs)

        return wrapper

    for fn in (n for n in os.listdir('plugins') if n.endswith('.py')):
        plugin = import_module('plugins.' + fn[:len(fn) - 3])

        if plugin.__doc__ and plugin.__doc__.startswith('yosho plugin'):
            name = plugin.__doc__.split(':')[1]
            PLUGINS[name] = plugin

    for n in sorted(PLUGINS.keys(), key=lambda n: PLUGINS[n].ORDER):
        for h, m in PLUGINS[n].handlers:
            if m:
                h.callback = modifiers(h.callback, **m)

            if 'bot_globals' in inspect.signature(h.callback).parameters:
                h.callback = globals_sender(h.callback)

            updater.dispatcher.add_handler(h)

        logger.info('Loaded plugin {}'.format(n))


# noinspection PyUnusedLocal
def error(bot, update, error):
    logger.warning('Update "{}" caused error "{}"'.format(update, error))


updater.dispatcher.add_error_handler(error)


# start text
@modifiers(age=False, name=True, action=Ca.TYPING, level=logging.DEBUG)
def start(bot, update):
    if 'macro processor' in PLUGINS.keys():
        update.message.text = '/start_info' + bot.name.lower()
        PLUGINS['macro processor'].call_macro(bot, update, globals())
    else:
        update.message.reply_text(text='Yosho bot by @MuddyTK and @WyreYote')


updater.dispatcher.add_handler(CommandHandler("start", start))


load_plugins()
if 'macro processor' in PLUGINS.keys():
    jobs.run_repeating(PLUGINS['macro processor'].flush, interval=FLUSH_INTERVAL)

logger.info("bot loaded")
updater.start_polling()
