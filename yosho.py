from random import randint

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

TOKEN_SELECTION = 'yosho_bot'
token_dict = [l for l in csv.DictReader(open('tokens.csv', 'r'))][0]
TOKEN = token_dict[TOKEN_SELECTION]

MODS = ('wyreyote', 'teamfortress', 'plusreed', 'pixxo', 'pjberri', 'pawjob')
DEBUGGING_MODE = False
MESSAGE_TIMEOUT = 1

EVAL_TIMEOUT = 1
EVAL_MAX_CHARS = 200

GLOBAL_MESSAGES = {
'/help':
    r"""Available commands:
/echo <text> - echoes text
/roll <int> - rolls a number between 1 and x
/eval <expression> - does math
/e926 <tags> - search e926
/why - post random cursed image

Inline subcommands:
shrug - sends an ascii shrug.
badtime - fucken love undertale""",

'/badtime':
    r"""…………/´¯/)…………….(\¯`.…………..
………../…//……….i…….\….…………..
………./…//…fuken luv….\….………….
…../´¯/…./´¯..undertale./¯` .…\¯`.…….
.././…/…./…./.|_.have._|..….……..…..
(.(b.(..a.(..d./..)..)……(..(.\ti.)..m.)..e.).)….
..……………\/…/………\/……………./….
……………….. /……….……………..""",

'/effective.':
    "Power لُلُصّ؜بُلُلصّبُررًً ॣ h؜ ॣ؜ ॣ ॣ",

'/ointments':
    "Ointments."}

GLOBAL_INLINE = {
'badtime':
    r"""…………/´¯/)…………….(\¯`.…………..
………../…//……….i…….\….…………..
………./…//…fuken luv….\….………….
…../´¯/…./´¯..undertale./¯` .…\¯`.…….
.././…/…./…./.|_.have._|..….……..…..
(.(b.(..a.(..d./..)..)……(..(.\ti.)..m.)..e.).)….
..……………\/…/………\/……………./….
……………….. /……….……………..""",

'shrug':
    r"¯\_(ツ)_/¯"}

bot = telegram.Bot(token=TOKEN)
updater = Updater(token=TOKEN)
logging.basicConfig(format='%(asctime)s - [%(levelname)s] - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("Loading bot...")


# message modifiers decorator.
def modifiers(method=None, age=True, name=False, mods=False, action=False):
    if method is None:
        return functools.partial(modifiers, age=age, name=name, mods=mods, action=action)

    @functools.wraps(method)
    def wrap(*args, **kwargs):
        n = re.findall('@[\w]+\s', args[1].message.text + ' ')
        message_bot = (n[0].lower().strip() if len(n) > 0 else None)
        message_user = args[1].message.from_user.username.lower()
        message_age = (datetime.datetime.now() - args[1].message.date).total_seconds() / 60

        if (not age or message_age < MESSAGE_TIMEOUT) and\
                (not name or message_bot == '@' + TOKEN_SELECTION) and\
                (not mods or message_user in MODS):
            if action:
                args[0].sendChatAction(chat_id=args[1].message.chat_id, action=action)
            return method(*args, **kwargs)
        else:
            return
    return wrap


clean = lambda s: str.strip(re.sub('/[@\w]+\s', '', s+' ', 1))  # fuck off PyCharm idc if it's PEP8 compliant


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

    index = 'https://e926.net/post/index.json'
    params = {'limit': str(post_count), 'tags': tags}
    headers = {'User-Agent': 'YoshoBot || @WyreYote and @TeamFortress on Telegram'}

    r = requests.get(index, params=params, headers=headers)
    time.sleep(.5)

    if r.status_code == requests.codes.ok:
        data = r.json()
        posts = [p['file_url'] for p in data if p['file_ext'] in ('jpg', 'png')]
        p = None
        try:
            p = posts[randint(0, len(posts)-1)]
            if DEBUGGING_MODE:
                update.message.reply_text(text=p)
            update.message.reply_photo(photo=p)
            time.sleep(.5)
        except TelegramError:
            logger.warning('TelegramError in e926 call, post value: ' + str(p))
        except ValueError:
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


@modifiers(action=Ca.TYPING)
def evaluate(bot, update):
    result = 'Invalid input:\n\n'
    expr = clean(update.message.text)

    repl = update.message.reply_to_message
    if '~preceding' in expr and repl is not None:
        expr = expr.replace('~preceding', repl.text)

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

    logger.info("Processed eval command. Input: " + expr + ", output: " + str(result))
    update.message.reply_text(text=str(result))


eval_handler = CommandHandler("eval", evaluate)
updater.dispatcher.add_handler(eval_handler)


# inline commands
def inline_stuff(bot, update):
    results = list()
    query = update.inline_query.query

    if query:
        if query in GLOBAL_INLINE.keys():
            results.append(InlineQueryResultArticle(id=query, title=GLOBAL_INLINE[query],
                                                    input_message_content=InputTextMessageContent(GLOBAL_INLINE[query])))
    else:
        return
    update.inline_query.answer(results)


inline_handler = InlineQueryHandler(inline_stuff)
updater.dispatcher.add_handler(inline_handler)


@modifiers
def unknown(bot, update):
    command = str.strip(re.sub('@[\w]+\s', '', update.message.text + ' ', 1))
    if command in GLOBAL_MESSAGES.keys():
        bot.sendChatAction(chat_id=update.message.chat_id, action=Ca.TYPING)
        update.message.reply_text(text=GLOBAL_MESSAGES[command])
    else:
        unknown_reply(bot, update, 'Error:\n\nUnknown command: ' + command)


@modifiers(age=False, name=True, action=Ca.TYPING)
def unknown_reply(bot, update, text):
    update.message.reply_text(text=text)


unknown_handler = RegexHandler(r'/.*', unknown)
updater.dispatcher.add_handler(unknown_handler)

logger.info("Bot loaded.")
updater.start_polling()
