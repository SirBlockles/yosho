from random import randint

import pickle
import functools
import datetime
import logging
import re
import requests
import stopit
import telegram
import time
import csv
from asteval import Interpreter
from telegram import ChatAction as Ca
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.error import TelegramError
from telegram.ext import Updater, CommandHandler, InlineQueryHandler, RegexHandler

# initialize bot and logging for debugging #

TOKEN_SELECTION = 'yoshobeta_bot'
token_dict = [l for l in csv.DictReader(open('tokens.csv', 'r'))][0]
TOKEN = token_dict[TOKEN_SELECTION]

MODS = ('wyreyote', 'teamfortress', 'plusreed', 'pixxo', 'pjberri', 'pawjob')
DEBUGGING_MODE = False
MESSAGE_TIMEOUT = 1

EVAL_TIMEOUT = 1
EVAL_MAX_CHARS = 200

GLOBAL_COMMANDS = pickle.load(open('COMMANDS.pkl', 'rb'))
GLOBAL_INLINES = pickle.load(open('INLINES.pkl', 'rb'))

bot = telegram.Bot(token=TOKEN)
updater = Updater(token=TOKEN)
logging.basicConfig(format='%(asctime)s - [%(levelname)s] - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Loading bot...")


# message modifiers decorator.
# name checks if correct bot @name is present if value is True, also passes unnamed commands if value is ALLOW_UNNAMED
def modifiers(method=None, age=True, name=False, mods=False, action=None):
    if method is None:  # if method is None optional arguments have been passed, return usable decorator
        return functools.partial(modifiers, age=age, name=name, mods=mods, action=action)

    @functools.wraps(method)
    def wrap(*args, **kwargs):  # otherwise wrap function and continue
        message = args[1].message
        n = re.findall('@[\w]+\s', message.text + ' ')
        message_bot = (n[0].lower().strip() if len(n) > 0 else None)  # bot @name used in command if present
        message_user = message.from_user.username  # name of OP/user of command
        message_age = (datetime.datetime.now() - message.date).total_seconds() / 60  # age of message in minutes

        if DEBUGGING_MODE:  # log the method and various other data if in debug mode
            chat = message.chat
            title = chat.type + ' -> ' + (chat.title if chat.username is None else '@' + chat.username)
            logger.info(method.__name__ + ' command called from ' + title
                        + ', user: @' + message_user + ', with message text: "' + message.text + '"')

        # check incoming message attributes
        if (not age or message_age < MESSAGE_TIMEOUT) and\
                (not name or message_bot == '@' + TOKEN_SELECTION or (message_bot is None and name == 'ALLOW_UNNAMED'))\
                and (not mods or message_user.lower() in MODS):
            if action:
                args[0].sendChatAction(chat_id=message.chat_id, action=action)

            start = time.time()
            method(*args, **kwargs)
            end = time.time()

            if DEBUGGING_MODE:  # log the time elapsed if in debug mode
                logger.info('time elapsed (seconds): ' + str(end - start))
        else:
            if DEBUGGING_MODE:
                logger.info('Message canceled by decorator.')
    return wrap


clean = lambda s: str.strip(re.sub('/[@\w]+\s', '', s+' ', 1))  # strips command name and bot name from input


def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"' % (update, error))


updater.dispatcher.add_error_handler(error)


# start text
@modifiers(age=False, action=Ca.TYPING)
def start(bot, update):
    bot.sendMessage(chat_id=update.message.chat_id, text="Hi. I do a bunch of misc shit. Add me to a group I guess")


start_handler = CommandHandler("start", start)
updater.dispatcher.add_handler(start_handler)


# toggle debug mode command
@modifiers(mods=True, action=Ca.TYPING)
def toggle_debug(bot, update):
    global DEBUGGING_MODE
    message = ("Noodles are the best, no doubt, can't deny - tastes better than water, but don't ask you why",
               "But then again, many things can be tasty - cornbread, potatoes, rice, and even pastries")
    update.message.reply_text(text=message[DEBUGGING_MODE])
    DEBUGGING_MODE ^= True
    logger.info('Debugging mode set to ' + str(DEBUGGING_MODE).lower())


debug_handler = CommandHandler("NoodlesAreTheBestNoDoubtCantDeny", toggle_debug)
updater.dispatcher.add_handler(debug_handler)


@modifiers(action=Ca.TYPING)
def dice_roll(bot, update, args):
    if not args:
        output = randint(1, 6)
    elif str.isnumeric(args[0]):
        output = randint(1, int(args[0]))
    else:
        output = "Invalid input.\n\nProper syntax is /roll <integer>."
    update.message.reply_text(text=str(output))


dice_handler = CommandHandler("roll", dice_roll, pass_args=True)
updater.dispatcher.add_handler(dice_handler)


@modifiers(action=Ca.TYPING)
def get_chat_id(bot, update):
    update.message.reply_text(text=update.message.chat_id)


getchathandler = CommandHandler("chatid", get_chat_id)
updater.dispatcher.add_handler(getchathandler)


@modifiers(action=Ca.TYPING)
def echo(bot, update):
    reply = clean(update.message.text)

    if reply in ('', '@Yosho_bot'):
        update.message.reply_text(text="Gimmie some text to echo!")
    elif reply == "Gimmie some text to echo!":
        update.message.reply_text(text="That's my line.")
    else:
        bot.sendMessage(chat_id=update.message.chat_id, text=reply)

    logger.info("Processed echo command. Input: " + reply)


echo_handler = CommandHandler("echo", echo)
updater.dispatcher.add_handler(echo_handler)


@modifiers(mods=True, action=Ca.TYPING)
def die(bot, update):
    update.message.reply_text(text='KMS')
    quit()


die_handler = CommandHandler("die", die)
updater.dispatcher.add_handler(die_handler)


@modifiers(action=Ca.UPLOAD_PHOTO)
def e926(bot, update, tags=None):
    failed = 'Error:\n\ne926 query failed.'
    post_count = 50

    if tags is None:
        tags = clean(update.message.text)

    # construct the request
    index = 'https://e926.net/post/index.json'
    params = {'limit': str(post_count), 'tags': tags}
    headers = {'User-Agent': 'YoshoBot || @WyreYote and @TeamFortress on Telegram'}

    r = requests.get(index, params=params, headers=headers)
    time.sleep(.5)  # rate limit, can be lowered to .25 if needed.

    if r.status_code == requests.codes.ok:
        data = r.json()
        posts = [p['file_url'] for p in data if p['file_ext'] in ('jpg', 'png')]  # find image urls in json response
        p = None
        try:
            p = posts[randint(0, len(posts)-1)]
            if DEBUGGING_MODE:
                logger.info(p)
            update.message.reply_photo(photo=p)
            time.sleep(.5)  # rate limit, can be lowered to .25 if needed.

        except TelegramError:
            if DEBUGGING_MODE:
                logger.warning('TelegramError in e926 call, post value: ' + str(p))
        except ValueError:
            if DEBUGGING_MODE:
                logger.warning('ValueError in e926 call, probably incorrect tags')
            update.message.reply_text(text=failed)
    else:
        update.message.reply_text(text=failed)


e926_handler = CommandHandler("e926", e926)
updater.dispatcher.add_handler(e926_handler)


def why(bot, update):
    e926(bot, update, tags='~what_has_science_done ~where_is_your_god_now')


why_handler = CommandHandler("why", why)
updater.dispatcher.add_handler(why_handler)


@modifiers(name='ALLOW_UNNAMED', action=Ca.TYPING)
def evaluate(bot, update, cmd=None):
    result = 'Invalid input:\n\n'

    expr = cmd if cmd else clean(update.message.text)

    # replace instances of '~preceding' in input with quoted comment if present
    preceding = update.message.reply_to_message
    if '~preceding' in expr and preceding is not None:
        expr = expr.replace('~preceding', 'r"""'+preceding.text.replace('"', "'")+'"""')

    # execute command with timeout
    with stopit.ThreadingTimeout(EVAL_TIMEOUT) as ctx:
        a = Interpreter()
        out = a(expr)

    if ctx.state == ctx.TIMED_OUT:
        result += 'Timed out.'
    else:
        if out is None:
            result = 'Fuck off lol.'
        elif len(str(out)) > EVAL_MAX_CHARS:
            result = str(out)[:EVAL_MAX_CHARS] + '...'
        else:
            result = out
    update.message.reply_text(text=str(result))


eval_handler = CommandHandler("eval", evaluate)
updater.dispatcher.add_handler(eval_handler)


# creates and modifies macro commands
@modifiers(mods=True, action=Ca.TYPING)
def macro(bot, update):
    err = 'Macro editor error:\n\n'
    expr = clean(update.message.text)
    if expr is None:
        update.message.reply_text(text=err+'Invalid input.')
        return

    args = expr.split(' ')
    mode = args[0]
    name = ''

    if len(args) > 1:
        name = args[1]
    elif not mode == 'list':
        update.message.reply_text(text=err+'Missing command name.')
        return

    if not name.isalpha() and not mode == 'list':
        update.message.reply_text(text=err+'Command name must only contain letters.')
        return

    name = '/'+name

    keys = GLOBAL_COMMANDS.keys()

    if mode == 'eval' and name not in keys:
        if len(args) > 2:
            GLOBAL_COMMANDS[name] = (''.join(args[2:]), True)
            update.message.reply_text(text='Command "' + name + '" created.')
        else:
            print(GLOBAL_COMMANDS)
            update.message.reply_text(text=err+'Missing command code.')

    elif mode == 'text' and name not in keys:
        if len(args) > 2:
            GLOBAL_COMMANDS[name] = (''.join(args[2:]), False)
            update.message.reply_text(text='Command "' + name + '" created.')
        else:
            update.message.reply_text(text=err+'Missing command text.')

    elif mode == 'modify':
        if name in keys:
            GLOBAL_COMMANDS[name] = (''.join(args[2:]), GLOBAL_COMMANDS[name][1])
            update.message.reply_text(text='Command "' + name + '" modified.')
        else:
            update.message.reply_text(text=err+'No command with name ' + name + '.')

    elif mode == 'remove':
        if name in keys:
            del GLOBAL_COMMANDS[name]
            update.message.reply_text(text='Command "' + name + '" removed.')
        else:
            update.message.reply_text(text=err+'No command with name ' + name + '.')

    elif mode == 'list':
        update.message.reply_text('Existing macros:\n' + '\n'.join(keys))

    elif mode not in ('eval', 'text', 'remove', 'list', 'modify'):
        update.message.reply_text(text=err+'Unknown mode ' + mode + '.')

    elif name in GLOBAL_COMMANDS:
        update.message.reply_text(text=err + 'Command already exists.')

        pickle.dump(GLOBAL_COMMANDS, open('COMMANDS.pkl', 'wb+'))


macro_handler = CommandHandler("macro", macro)
updater.dispatcher.add_handler(macro_handler)


# inline commands
def inline_stuff(bot, update):
    results = list()
    query = update.inline_query.query

    if query:
        if query in GLOBAL_INLINES.keys():
            if DEBUGGING_MODE:
                logger.info('Inline query called: ' + query)
            results.append(InlineQueryResultArticle(id=query, title=GLOBAL_INLINES[query],
                                                    input_message_content=InputTextMessageContent(GLOBAL_INLINES[query])))
    else:
        return
    update.inline_query.answer(results)


inline_handler = InlineQueryHandler(inline_stuff)
updater.dispatcher.add_handler(inline_handler)


@modifiers
def unknown(bot, update):  # process dict reply commands
    @modifiers(age=False, name=True, action=Ca.TYPING)
    def invalid(bot, update, text):
        update.message.reply_text(text=text)

    @modifiers(age=False, name='ALLOW_UNNAMED', action=Ca.TYPING)
    def known(bot, update, text):
        update.message.reply_text(text=text)

    command = str.strip(re.sub('@[\w]+\s', '', update.message.text + ' ', 1))
    if command in GLOBAL_COMMANDS.keys():
        if GLOBAL_COMMANDS[command][1]:  # check if command is code or text
            evaluate(bot, update, cmd=GLOBAL_COMMANDS[command][0])
        else:
            known(bot, update, GLOBAL_COMMANDS[command][0])
    else:
        invalid(bot, update, 'Error:\n\nUnknown command: ' + command)


unknown_handler = RegexHandler(r'/.*', unknown)
updater.dispatcher.add_handler(unknown_handler)

logger.info("Bot loaded.")
updater.start_polling()
