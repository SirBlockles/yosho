import csv
import datetime
import functools
import io
import logging
import pickle
import re
import time
import xml.etree.ElementTree as Xml
from random import choice

import dropbox
import requests
import stopit
import telegram
from PIL import Image, ImageOps
from asteval import Interpreter
from dropbox.files import WriteMode
from telegram import ChatAction as Ca
from telegram import InlineQueryResultArticle, InputTextMessageContent, InputMediaPhoto
from telegram.error import TelegramError
from telegram.ext import Updater, CommandHandler, InlineQueryHandler, RegexHandler, CallbackQueryHandler

from macro import Macro, MacroSet

TOKEN_DICT = [l for l in csv.DictReader(open('tokens.csv', 'r'))][0]
TELEGRAM_TOKEN = TOKEN_DICT['yosho_bot']
DROPBOX_TOKEN = TOKEN_DICT['dropbox']
WOLFRAM_TOKEN = TOKEN_DICT['wolfram']

db = dropbox.Dropbox(DROPBOX_TOKEN)

MODS = {'wyreyote', 'teamfortress', 'plusreed', 'pixxo', 'radookal', 'pawjob'}

# not PEP8 compliant but idc
is_mod = lambda name: name.lower() in MODS
clean = lambda s: str.strip(re.sub('/[@\w]+\s+', '', s + ' ', 1))  # strips command name and bot name from input
db_pull = lambda name: db.files_download_to_file(name, '/' + name)
db_push = lambda name: db.files_upload(open(name, 'rb').read(), '/' + name, mode=WriteMode('overwrite'))
db_make = lambda name: db.files_upload(open(name, 'rb').read(), '/' + name, mode=WriteMode('add'))

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
WOLFRAM_TIMEOUT = 20
LOGGING_LEVEL = logging.DEBUG
MESSAGE_TIMEOUT = 60
FLOOD_TIMEOUT = 20
EVAL_MEMORY = True
EVAL_TIMEOUT = 1
EVAL_MAX_OUTPUT = 128
EVAL_MAX_INPUT = 1000
INTERPRETER_TIMEOUT = 60 * 60
IMAGE_SEND_TIMEOUT = 40

WOLFRAM_RESULTS = {}
INTERPRETERS = {}

bot = telegram.Bot(token=TELEGRAM_TOKEN)
updater = Updater(token=TELEGRAM_TOKEN)
jobs = updater.job_queue
logging.basicConfig(format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger(__name__)
logger.info("Loading bot...")
last_commands = dict()


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
# TODO use kwargs instead of multiple optional arguments.
def modifiers(method=None, age=True, name=False, mods=False, flood=True, admins=False, nsfw=False, action=None):
    if method is None:  # if method is None optional arguments have been passed, return usable decorator
        return functools.partial(modifiers, age=age, name=name, mods=mods, flood=flood,
                                 admins=admins, nsfw=nsfw, action=action)

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
        admin_check = not admins or message_user in admins_list
        nsfw_check = not nsfw or (title in SFW.keys() and not SFW[title])
        if all((time_check, name_check, mod_check, admin_check, nsfw_check)):

            logger.info('{} command called from {} -> {{{}, {}}}, user: @{}, with message: "{}"'
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
                            bot.send_message(chat_id=message.chat_id, reply_to_message_id=message.message_id, text=
                            "There's a {} second cooldown between commands!\n"
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


def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


def no_flood(u):
    last_commands[u] = time.time() - MESSAGE_TIMEOUT * 2


# noinspection PyUnusedLocal
def error(bot, update, error):
    logger.warning('Update "{}" caused error "{}"'.format(update, error))


updater.dispatcher.add_error_handler(error)


# start text
@modifiers(age=False, action=Ca.TYPING)
def start(bot, update):
    update.message.text = '/start_info' + bot.name.lower()
    call_macro(bot, update)


start_handler = CommandHandler("start", start)
updater.dispatcher.add_handler(start_handler)


# noinspection PyUnusedLocal
@modifiers(mods=True, action=Ca.TYPING)
def die(bot, update):
    update.message.reply_text(text='KMS')
    quit()


die_handler = CommandHandler("die", die)
updater.dispatcher.add_handler(die_handler)


# noinspection PyUnusedLocal
@modifiers(flood=False, admins=True, action=Ca.TYPING)
def sfw(bot, update):
    chat = update.message.chat
    name = chat.title if chat.username is None else '@' + chat.username
    if name in SFW.keys():
        SFW[name] ^= True
    else:
        SFW[name] = True
    pickle.dump(SFW, open(SFW_PATH, 'wb+'))
    db_push(SFW_PATH)
    update.message.reply_text(text='Chat {} is SFW only: {}'.format(name, SFW[name]))


sfw_handler = CommandHandler("sfw", sfw)
updater.dispatcher.add_handler(sfw_handler)


@modifiers(mods=True, action=Ca.TYPING)
def leave(bot, update):
    chat = clean(update.message.text)
    try:
        if chat.replace('-', '').isnumeric():
            bot.leave_chat(chat_id=int(chat))
        else:
            bot.leave_chat(chat_id=chat)
        update.message.reply_text(text='Left chat {}.'.format(chat))
    except TelegramError:
        update.message.reply_text(text='Error leaving chat {}.\nMake sure chat name/id is valid!'.format(chat))


leave_handler = CommandHandler('leave', leave)
updater.dispatcher.add_handler(leave_handler)


# noinspection PyUnusedLocal
@modifiers(action=Ca.UPLOAD_PHOTO)
def e621(bot, update, tags=None):
    failed = 'Error:\n\ne621 query failed.'

    index = 'https://e621.net/post/index.json'
    chat = update.message.chat
    name = chat.title if chat.username is None else '@' + chat.username
    if name in SFW.keys() and SFW[name]:
        index = 'https://e926.net/post/index.json'

    if tags is None:
        tags = clean(update.message.text)

    # construct the request
    params = {'limit': '50', 'tags': tags}
    headers = {'User-Agent': 'YoshoBot || @WyreYote and @TeamFortress on Telegram'}

    r = requests.get(index, params=params, headers=headers)
    time.sleep(.5)

    if r.status_code == requests.codes.ok:
        data = r.json()
        posts = [p['file_url'] for p in data if p['file_ext'] in ('jpg', 'png')]  # find image urls in json response

        if posts:
            url = choice(posts)
            logger.debug(url)
            try:
                update.message.reply_photo(photo=url, timeout=IMAGE_SEND_TIMEOUT)
            except TelegramError:
                logger.debug('TelegramError in e621.')
                update.message.reply_text(text=failed)
        else:
            logger.debug('Bad tags entered in e621.')
            update.message.reply_text(text=failed)
    else:
        update.message.reply_text(text=failed)


e621_handler = CommandHandler("e621", e621)
updater.dispatcher.add_handler(e621_handler)


# noinspection PyUnusedLocal
@modifiers(mods=True)
def set_global(bot, update):
    global GLOBALS
    args = [a.strip() for a in clean(update.message.text).split('=')]
    names = (k for k, v in globals().items() if type(v) in (int, bool))
    listed = ('{} = {}'.format(k, v) for k, v in globals().items() if type(v) in (int, bool))
    if len(args) > 1:
        if args[0] in names:
            if str(args[1]).isnumeric():
                GLOBALS[args[0]] = int(args[1])
                load_globals()
                pickle.dump(GLOBALS, open(GLOBALS_PATH, 'wb+'))
                db_push(GLOBALS_PATH)
                update.message.reply_text(text='Global {} updated.'.format(args[0]))
            else:
                update.message.reply_text(text='Globals type error.\n\nValue must be int.\nUse 1 or 0 for booleans.')
        else:
            update.message.reply_text(text='Globals key error.\n\nThat global does not exist.')
    elif args[0] == '':
        update.message.reply_text(text='Globals:\n\n' + '\n'.join(listed))
    else:
        update.message.reply_text(text='Globals syntax error.\n\nProper usage is /global <global>=<value>')


globals_handler = CommandHandler("global", set_global)
updater.dispatcher.add_handler(globals_handler)


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


eval_handler = CommandHandler("eval", evaluate)
updater.dispatcher.add_handler(eval_handler)


# creates and modifies macro commands
@modifiers(action=Ca.TYPING)
def macro(bot, update):
    global MACROS
    message = update.message
    user = update.message.from_user
    message_user = user.username if user.username is not None else user.name

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

    user = message.from_user.username.lower()
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
        if expr is not None:
            try:
                MACROS.add(Macro(name, mode.upper(), expr, hidden=False, protected=is_mod(user), nsfw=False))
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
            MACROS = MACROS.subset(protected=False)
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
            names = ((bot.name + ' ') * (m.variety == Macro.INLINE) + m.name for m in MACROS.subset(filt=filt))
            message.reply_text('Macros:\n' + ', '.join(names))
        else:
            names = ((bot.name + ' ') * (m.variety == Macro.INLINE) + m.name for m in
                     MACROS.subset(hidden=False))
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
                MACROS[name].nsfw ^= True
                message.reply_text('NSFW macro {}: {}'.format(name, MACROS[name].nsfw))
        else:
            message.reply_text(text=err + 'No macro with name {}.'.format(name))

    elif name in MACROS:
        message.reply_text(text=err + 'Macro already exists.')

    MacroSet.dump(MACROS, open(MACROS_PATH, 'w+'))
    db_push(MACROS_PATH)


macro_handler = CommandHandler("macro", macro)
updater.dispatcher.add_handler(macro_handler)


# noinspection PyUnusedLocal
@modifiers(action=Ca.TYPING)
def wolfram(bot, update):
    global WOLFRAM_RESULTS
    message = update.message
    name = message.from_user.name

    err = 'Wolfram|Alpha error:\n\n'
    failed = err + 'Wolfram|Alpha query failed.'

    query = clean(update.message.text)

    if name not in WOLFRAM_RESULTS.keys():
        WOLFRAM_RESULTS[name] = None

    if query != '':
        # construct the request
        base = 'http://api.wolframalpha.com/v2/query'
        params = {'appid': WOLFRAM_TOKEN, 'input': query, 'width': 800}

        r = requests.get(base, params=params)
        tree = Xml.XML(r.text)
        if r.status_code == requests.codes.ok:
            if (tree.attrib['success'], tree.attrib['error']) == ('true', 'false'):
                pods = tree.iterfind('pod')
                buttons = [telegram.InlineKeyboardButton(p.attrib['title'], callback_data='w' + str(i))
                           for i, p in enumerate(pods) if not p.attrib['id'] == 'Input']
                markup = telegram.InlineKeyboardMarkup(build_menu(buttons, n_cols=2))

                interp = re.sub(' +', ' ', tree.find('pod').find('subpod').find('plaintext').text)

                pods = tree.iterfind('pod')
                WOLFRAM_RESULTS[name] = {i: (p.attrib['title'], [s for s in p.iterfind('subpod')], interp)
                                         for i, p in enumerate(pods)}

                if len(WOLFRAM_RESULTS[name]) > 1:
                    m = message.reply_text('Input interpretation: {}\nChoose result to view:'.format(interp),
                                           reply_markup=markup)
                    jobs.run_once(wolfram_timeout, WOLFRAM_TIMEOUT, context=(m.message_id, m.chat.id,
                                                                             message.message_id, message.chat_id))
                else:
                    message.reply_text(text=failed)
            else:
                message.reply_text(text=err + "Wolfram|Alpha can't understand your query.")
        else:
            message.reply_text(text=failed)
    else:
        message.reply_text(text=err + 'Empty query.')


wolfram_handler = CommandHandler("wolfram", wolfram)
updater.dispatcher.add_handler(wolfram_handler)


def wolfram_callback(bot, update):
    def album(data):
        output = []
        for idx, subpod in enumerate(data[1]):
            url = subpod.find('img').attrib['src']
            title = subpod.attrib['title']
            caption = 'Selection: {}{}\nInput: {}'.format(data[0], '\nSubpod: ' * bool(title) + title, data[2])

            img_b = io.BytesIO(requests.get(url).content)
            img = Image.open(img_b)
            minimum = 100
            if img.size[0] < minimum or img.size[1] < minimum:  # Hacky way to make sure any image sends.
                pad = sorted([minimum - img.size[0], minimum - img.size[1]])
                img = ImageOps.expand(img, border=pad[1] // 2, fill=255)
            fn = 'temp{}.png'.format(idx)
            img.save(fn, format='PNG')
            output.append(InputMediaPhoto(caption=caption, media=fn))
        return output

    query = update.callback_query
    idx = int(query.data.replace('w', ''))
    name = query.from_user.name
    message = query.message

    if name not in WOLFRAM_RESULTS.keys():
        WOLFRAM_RESULTS[name] = None
        return

    bot.sendChatAction(chat_id=message.chat.id, action=Ca.TYPING)

    if message.chat.type == 'private':
        images = album(WOLFRAM_RESULTS[name][idx])
        for i in images:
            bot.send_photo(caption=i.caption, photo=open(i.media, 'rb'), chat_id=message.chat.id,
                           timeout=IMAGE_SEND_TIMEOUT)

    elif query.from_user.id == message.reply_to_message.from_user.id:
        images = album(WOLFRAM_RESULTS[name][idx])
        for i in images:
            bot.send_photo(caption=i.caption, photo=open(i.media, 'rb'), chat_id=message.chat.id,
                           reply_to_message_id=message.reply_to_message.message_id, timeout=IMAGE_SEND_TIMEOUT)

    message.delete()
    WOLFRAM_RESULTS[name] = None


wolfram_callback_handler = CallbackQueryHandler(wolfram_callback, pattern='^w[0-9]+')
updater.dispatcher.add_handler(wolfram_callback_handler)


def wolfram_timeout(bot, job):
    try:
        bot.deleteMessage(message_id=job.context[0], chat_id=job.context[1])
    except TelegramError:
        return
    bot.send_message(reply_to_message_id=job.context[2], chat_id=job.context[3],
                     text='Failed to choose an option within {} seconds.\nResults timed out.'.format(WOLFRAM_TIMEOUT))


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


inline_handler = InlineQueryHandler(inline_stuff)
updater.dispatcher.add_handler(inline_handler)


@modifiers(name='ALLOW_UNNAMED', flood=False)
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
                e621(bot, update, tags=content + ' ' + clean(message.text))

            elif variety == Macro.INLINE:
                quoted = None
                known(bot, update, "Macro error:\n\nThat's an inline macro! Try @yosho_bot " + command)

            elif variety == Macro.ALIAS:
                run(content)

        else:
            invalid(bot, update, 'Error:\n\nUnknown command: ' + command)
    run()


macro_handler = RegexHandler(r'/.*', call_macro)
updater.dispatcher.add_handler(macro_handler)


# noinspection PyUnusedLocal,PyUnusedLocal
def clear(bot, job):
    global INTERPRETERS
    INTERPRETERS = {}


logger.info("bot loaded")
updater.start_polling()
jobs.run_repeating(clear, interval=INTERPRETER_TIMEOUT)  # clear interpreters regularly to prevent high memory usage
