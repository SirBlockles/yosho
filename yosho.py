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

import stopit
import telegram
from asteval import Interpreter
from telegram import ChatAction as Ca
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.error import TelegramError
from telegram.ext import Updater, CommandHandler, InlineQueryHandler, RegexHandler

from helpers import is_mod, clean, db_push, db_pull
from macro import Macro, MacroSet

TOKEN_DICT = [l for l in csv.DictReader(open('tokens.csv', 'r'))][0]
TELEGRAM_TOKEN = TOKEN_DICT['yoshobeta_bot']
WOLFRAM_TOKEN = TOKEN_DICT['wolfram']

SFW_PATH = 'SFW.pkl'
db_pull(SFW_PATH)
SFW = pickle.load(open(SFW_PATH, 'rb'))

GLOBALS_PATH = 'GLOBALS.pkl'
db_pull(GLOBALS_PATH)
GLOBALS = pickle.load(open(GLOBALS_PATH, 'rb'))

MACROS_PATH = 'MACROS.json'
db_pull(MACROS_PATH)
MACROS = MacroSet.load(open(MACROS_PATH, 'rb'))

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

INTERPRETERS = {}

bot = telegram.Bot(token=TELEGRAM_TOKEN)
updater = Updater(token=TELEGRAM_TOKEN)
jobs = updater.job_queue
logging.basicConfig(format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)
logger.info("Loading bot...")
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
        name_check = not name or message_bot == bot.name.lower() or (message_bot is None and name == 'ALLOW_UNNAMED')
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

            for h, m in plugin.handlers:
                if 'bot_globals' in inspect.signature(h.callback).parameters:
                    h.callback = globals_sender(h.callback)

                if m:
                    h.callback = modifiers(h.callback, **m)
                updater.dispatcher.add_handler(h)
            logger.info('Loaded plugin {}: {}'.format(fn, name))


load_plugins()


def no_flood(u):
    last_commands[u] = time.time() - MESSAGE_TIMEOUT * 2


# noinspection PyUnusedLocal
def error(bot, update, error):
    logger.warning('Update "{}" caused error "{}"'.format(update, error))


updater.dispatcher.add_error_handler(error)


# start text
@modifiers(age=False, action=Ca.TYPING, level=logging.DEBUG)
def start(bot, update):
    update.message.text = '/start_info' + bot.name.lower()
    call_macro(bot, update)


updater.dispatcher.add_handler(CommandHandler("start", start))


@modifiers(action=Ca.TYPING)
def evaluate(bot, update, cmd=None, symbols=None):
    global INTERPRETERS
    user = update.message.from_user
    message_user = user.username if user.username is not None else user.name

    err = 'Invalid input:\n\n'
    result = err

    expr = (cmd if cmd else clean(update.message.text)).replace('#', '\t')

    if expr == '':
        update.message.text = '/eval_info' + bot.name.lower()
        no_flood(message_user)
        call_macro(bot, update)
        return

    if len(expr) > EVAL_MAX_INPUT:
        update.message.reply_text(err + 'Maximum input length exceeded.')
        return

    name = update.message.from_user.name
    interp = Interpreter()
    if EVAL_MEMORY and name in INTERPRETERS.keys():
        interp.symtable = {**INTERPRETERS[name], **Interpreter().symtable}
        logger.debug('Loaded interpreter "{}": {}'.format(name, INTERPRETERS[name]))

    quoted = update.message.reply_to_message
    preceding = '' if quoted is None else quoted.text
    them = '' if quoted is None else quoted.from_user.name

    if not symbols:
        symbols = {}
    chat = update.message.chat

    symbols = {**symbols, **{'MY_NAME': name,
                             'THEIR_NAME': them,
                             'PRECEDING': preceding,
                             'GROUP': (chat.title if chat.username is None else '@' + chat.username),
                             'REPLY': True}}

    interp.symtable = {**interp.symtable, **symbols}

    with stopit.ThreadingTimeout(EVAL_TIMEOUT) as ctx:
        out = interp(expr)

    reply = interp.symtable['REPLY']

    if EVAL_MEMORY and cmd is None:
        INTERPRETERS[name] = {k: v for k, v in interp.symtable.items() if k not in
                              Interpreter().symtable.keys() and k not in symbols.keys()}
        logger.debug('Saved interpreter "{}": {}'.format(name, INTERPRETERS[name]))

    if ctx.state == ctx.TIMED_OUT:
        result += 'Timed out.'
    else:
        if out is None:
            result = 'Code returned nothing.'
        elif len(str(out)) > EVAL_MAX_OUTPUT:
            result = str(out)[:EVAL_MAX_OUTPUT] + '...'
        else:
            result = str(out)
    if result == '':
        result = err + 'Code returned nothing.\nMaybe missing input?'

    if reply:
        if quoted is None:
            update.message.reply_text(text=result)
        else:
            quoted.reply_text(text=result)
    else:
        bot.send_message(text=result, chat_id=update.message.chat.id)


updater.dispatcher.add_handler(CommandHandler("eval", evaluate))


# creates and modifies macro commands
@modifiers(action=Ca.TYPING)
def macro(bot, update):
    global MACROS
    message = update.message
    message_user = message.from_user.username if message.from_user.username is not None else message.from_user.name

    modes = {'eval': 'macro',
             'text': 'macro',
             'inline': 'macro',
             'photo': 'macro',
             'e621': 'macro',
             'alias': 'macro',
             'remove': 'write',
             'hide': 'write',
             'protect': 'write',
             'clean': 'write',
             'modify': 'write',
             'rename': 'write',
             'nsfw': 'write',
             'contents': 'read',
             'list': 'read'}

    err = 'Macro editor error:\n\n'
    expr = clean(message.text)

    if expr == '':
        update.message.text = '/macro_help' + bot.name.lower()
        no_flood(message_user)
        call_macro(bot, update)
        return

    args = re.split('\s+', expr)
    mode = args[0]
    name = ''

    if mode not in modes.keys():
        message.reply_text(text=err + 'Unknown mode {}.'.format(mode))
        return

    if len(args) > 1:
        name = args[1].split('\n')[0]
    elif not (modes[mode] == 'read' or mode == 'clean'):
        message.reply_text(text=err + 'Missing macro name.')
        return

    user = message_user.lower()
    if name in MACROS:
        if MACROS[name].protected and not is_mod(user) and not modes[mode] == 'read':
            message.reply_text(text=err + 'Macro {} is write protected.'.format(name))
            return

    if len(args) > 2:
        expr = expr.replace(' '.join(args[:2]), '').strip()
        if len(args[1].split('\n')) == 2:
            expr = args[1].split('\n')[1] + expr
    else:
        expr = None

    if modes[mode] == 'macro' and name not in MACROS:
        if expr:
            try:
                MACROS.add(Macro(name, mode.upper(), expr, hidden=False, protected=is_mod(user), nsfw=False,
                                 creator={'user': message_user,
                                          'chat': message.chat.id,
                                          'chat_type': message.chat.type}))

                message.reply_text(text='{} macro "{}" created.'.format(mode, name))
            except ValueError:
                message.reply_text(text=err + 'Bad photo url.')
        else:
            message.reply_text(text=err + 'Missing macro contents.')

    elif mode == 'modify':
        if name in MACROS and expr is not None:
            try:
                MACROS[name].content = expr
                message.reply_text(text='Macro "{}" modified.'.format(name))
            except ValueError:
                message.reply_text(text=err + 'Bad photo url.')
        elif expr is None:
            message.reply_text(text=err + 'Missing macro text/code.')
        else:
            message.reply_text(text=err + 'No macro with name {}.'.format(name))

    elif mode == 'clean':
        if is_mod(user):
            MACROS = MACROS.subset(protected=True)
            message.reply_text('Cleaned up macros.')
        else:
            message.reply_text(text=err + 'Only bot mods can do that.')

    elif mode == 'remove':
        if name in MACROS:
            MACROS.remove(name)
            message.reply_text(text='Macro "{}" removed.'.format(name))
        else:
            message.reply_text(text=err + 'No macro with name {}.'.format(name))

    elif mode == 'rename':
        if name in MACROS:
            new_name = args[1]
            MACROS[name].name = new_name
            message.reply_text(text='Macro "{}" renamed to {}'.format(name, new_name))
        else:
            message.reply_text(text=err + 'No macro with name {}.'.format(name))

    elif mode == 'list':
        if is_mod(user):
            filt = {i.split(':')[0]: i.split(':')[1] for i in args[1:] if ':' in i}
            include = {i.split(':')[0]: i.split(':')[1] for i in args[1:] if ':' in i and not i.startswith('-')}
            exclude = {i.split(':')[0][1:]: i.split(':')[1] for i in args[1:] if ':' in i and i.startswith('-')}

            try:
                macros = MACROS.subset(filt=include)
                if exclude:
                    macros -= MACROS.subset(filt=exclude)
            except ValueError:
                message.reply_text(text=err + 'Unknown key in list filter: {}.'.format(filt))
                return

            if macros:
                names = ((bot.name + ' ') * (m.variety == Macro.INLINE) + m.name for m in macros.sort())
                message.reply_text('Macros:\n' + ', '.join(names))
            else:
                message.reply_text(text=err + 'No macros found.')
        else:
            names = ((bot.name + ' ') * (m.variety == Macro.INLINE) + m.name for m in MACROS.subset())
            message.reply_text('Visible macros:\n' + ', '.join(names))

    elif mode == 'contents':
        if name in MACROS:
            if not MACROS[name].hidden or is_mod(user):
                message.reply_text('Contents of {} macro {}: {}'
                                   .format(MACROS[name].variety.lower(), name, MACROS[name].content))
            else:
                message.reply_text(text=err + 'Macro {} contents hidden.'.format(name))
        else:
            message.reply_text(text=err + 'No macro with name {}.'.format(name))

    elif mode == 'hide':
        if name in MACROS:
            if is_mod(user):
                MACROS[name].hidden ^= True
                message.reply_text('Hide macro {}: {}'.format(name, MACROS[name].hidden))
            else:
                message.reply_text(text=err + 'Only bot mods can hide or show macros.')
        else:
            message.reply_text(text=err + 'No macro with name {}.'.format(name))

    elif mode == 'protect':
        if name in MACROS:
            if is_mod(user):
                MACROS[name].protected ^= True
                message.reply_text('Protect macro {}: {}'.format(name, MACROS[name].protected))
            else:
                message.reply_text(text=err + 'Only bot mods can protect macros.')
        else:
            message.reply_text(text=err + 'No macro with name {}.'.format(name))

    elif mode == 'nsfw':
        if name in MACROS:
            if is_mod(user):
                MACROS[name].nsfw ^= True
                message.reply_text('NSFW macro {}: {}'.format(name, MACROS[name].nsfw))
            else:
                message.reply_text(text=err + 'Only bot mods can change macro nsfw state.')
        else:
            message.reply_text(text=err + 'No macro with name {}.'.format(name))

    elif name in MACROS:
        message.reply_text(text=err + 'Macro already exists.')


updater.dispatcher.add_handler(CommandHandler("macro", macro))


# noinspection PyUnusedLocal
def inline_stuff(bot, update):
    results = list()
    query = update.inline_query.query

    if query in MACROS:
        if MACROS[query].variety == Macro.INLINE:
            logger.info('Inline query called: ' + query)
            results.append(
                InlineQueryResultArticle(id=query, title=query,
                                         input_message_content=InputTextMessageContent(MACROS[query].content)))
        else:
            return

    update.inline_query.answer(results)


updater.dispatcher.add_handler(InlineQueryHandler(inline_stuff))


@modifiers(name='ALLOW_UNNAMED', flood=False, level=logging.DEBUG)
def call_macro(bot, update):  # process macros and invalid commands.
    message = update.message
    quoted = message.reply_to_message
    chat = update.message.chat
    name = chat.title if chat.username is None else '@' + chat.username

    # noinspection PyUnusedLocal
    @modifiers(age=False, name=True, action=Ca.TYPING)
    def invalid(bot, update, text):
        update.message.reply_text(text=text)

    # noinspection PyUnusedLocal
    @modifiers(age=False, action=Ca.TYPING)
    def known(bot, update, text):
        if quoted is None:
            update.message.reply_text(text=text)
        else:
            quoted.reply_text(text=text)

    # noinspection PyUnusedLocal
    @modifiers(age=False, action=Ca.UPLOAD_PHOTO)
    def photo(bot, update, url):
        try:
            if quoted is None:
                update.message.reply_photo(photo=url, timeout=IMAGE_SEND_TIMEOUT)
            else:
                quoted.reply_photo(photo=url, timeout=IMAGE_SEND_TIMEOUT)
        except TelegramError:
            logger.debug('TelegramError in photo macro call: ' + str(url))

    def run(command=None):
        global quoted

        if command is None:
            command = re.sub('@[@\w]+', '', re.split('\s+', message.text)[0])

        if command in MACROS:
            variety = MACROS[command].variety
            content = MACROS[command].content
            if MACROS[command].nsfw and name in SFW.keys():
                if SFW[name]:
                    known(bot, update, "Macro error:\n\n{} is NSFW, this chat has been marked as SFW by the admins!"
                          .format(command))
                    return

            if variety == Macro.EVAL:
                symbols = {'INPUT': clean(message.text),
                           'HIDDEN': MACROS[command].hidden,
                           'PROTECTED': MACROS[command].protected}
                evaluate(bot, update, cmd=content, symbols=symbols)

            elif variety == Macro.TEXT:
                known(bot, update, content)

            elif variety == Macro.PHOTO:
                photo(bot, update, content)

            elif variety == Macro.E621:
                if 'e621 command' in PLUGINS.keys():
                    PLUGINS['e621 command'].e621(bot, update, globals(), tags=content + ' ' + clean(message.text))
                else:
                    update.message.reply_text("Macro error:\n\ne621 plugin isn't installed.")

            elif variety == Macro.INLINE:
                quoted = None
                known(bot, update, "Macro error:\n\nThat's an inline macro! Try @yosho_bot " + command)

            elif variety == Macro.ALIAS:
                run(content)

        else:
            invalid(bot, update, 'Error:\n\nUnknown command: ' + command)

    run()


updater.dispatcher.add_handler(RegexHandler(r'/.*', call_macro))


# noinspection PyUnusedLocal,PyUnusedLocal
def flush(bot, job):
    MacroSet.dump(MACROS, open(MACROS_PATH, 'w+'))
    db_push(MACROS_PATH)
    global INTERPRETERS
    INTERPRETERS = {}


logger.info("bot loaded")
updater.start_polling()
jobs.run_repeating(flush, interval=FLUSH_INTERVAL)
