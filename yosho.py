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
EVAL_MAX_DIGITS = 50

GLOBAL_MESSAGES = {
'/help':
    r"""Available commands:
/echo <text> - echoes text
/roll <int> - rolls a number between 1 and x
/eval - does math
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


# message age filter, mod filter and /command@botname filter decorator
def silence(method=None, age=True, name=False, mods=False):
    if method is None:
        return functools.partial(silence, age=age, name=name, mods=mods)

    @functools.wraps(method)
    def wrap(*args, **kwargs):
        n = re.findall('@[\w]+\s', args[1].message.text + ' ')
        message_bot = (n[0].lower().strip() if len(n) > 0 else None)
        message_user = args[1].message.from_user.username.lower()
        message_age = (datetime.datetime.now() - args[1].message.date).total_seconds() / 60

        if (message_age < MESSAGE_TIMEOUT or not age) and\
                (message_bot == '@' + TOKEN_SELECTION or not name) and\
                (message_user in MODS or not mods):
            return method(*args, **kwargs)
        else:
            return
    return wrap


clean = lambda s: str.strip(re.sub('/[@\w]+\s', '', s+' ', 1))  # fuck off PyCharm idc if it's PEP8 compliant


def error(bot, update, error):
    logger.warning('Update "%s" caused error "%s"' % (update, error))


updater.dispatcher.add_error_handler(error)


# start text
def start(bot, update):
    bot.sendMessage(chat_id=update.message.chat_id, text="Hi. I do a bunch of misc shit. Add me to a group I guess")


start_handler = CommandHandler("start", start)
updater.dispatcher.add_handler(start_handler)


# toggle debug mode command
@silence(mods=True)
def toggle_debug(bot, update):
    global DEBUGGING_MODE
    message = ("Noodles are the best, no doubt, can't deny - tastes better than water, but don't ask you why",
               "But then again, many things can be tasty - cornbread, potatoes, rice, and even pastries")
    bot.sendMessage(chat_id=update.message.chat_id, text=message[DEBUGGING_MODE])
    DEBUGGING_MODE ^= True


debug_handler = CommandHandler("NoodlesAreTheBestNoDoubtCantDeny", toggle_debug)
updater.dispatcher.add_handler(debug_handler)


@silence
def dice_roll(bot, update, args):
    if not args:
        output = randint(1, 6)
    elif str.isnumeric(args[0]):
        output = randint(1, int(args[0]))
    else:
        output = "Invalid input.\n\nProper syntax is /roll <integer>."
    bot.sendMessage(chat_id=update.message.chat_id, text=str(output))


dice_handler = CommandHandler("roll", dice_roll, pass_args=True)
updater.dispatcher.add_handler(dice_handler)


@silence
def get_chat_id(bot, update):
    bot.sendMessage(chat_id=update.message.chat_id, text=update.message.chat_id)


getchathandler = CommandHandler("chatid", get_chat_id)
updater.dispatcher.add_handler(getchathandler)


@silence
def echo(bot, update):
    bot.sendChatAction(chat_id=update.message.chat_id, action=telegram.ChatAction.TYPING)
    reply = clean(update.message.text)

    if reply in ('', '@Yosho_bot'):
        bot.sendMessage(chat_id=update.message.chat_id, text="Gimmie some text to echo!")
    elif reply == "Gimmie some text to echo!":
        bot.sendMessage(chat_id=update.message.chat_id, text="That's my line.")
    else:
        bot.sendMessage(chat_id=update.message.chat_id, text=reply)

    logger.info("Processed echo command. Input: " + reply)


echo_handler = CommandHandler("echo", echo)
updater.dispatcher.add_handler(echo_handler)


@silence(mods=True)
def die(bot, update):
    bot.sendMessage(chat_id=update.message.chat_id, text='KMS')
    quit()


die_handler = CommandHandler("die", die)
updater.dispatcher.add_handler(die_handler)


@silence
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
                bot.sendMessage(chat_id=update.message.chat_id, text=p)
            bot.sendPhoto(chat_id=update.message.chat_id, photo=p)
            time.sleep(.5)
        except TelegramError:
            logger.warning('TelegramError in e926 call, post value: ' + str(p))
        except ValueError:
            logger.warning('ValueError in e926 call, probably incorrect tags')
            bot.sendMessage(chat_id=update.message.chat_id, text=failed)
    else:
        bot.sendMessage(chat_id=update.message.chat_id, text=failed)


e926_handler = CommandHandler("e926", e926)
updater.dispatcher.add_handler(e926_handler)


def why(bot, update):
    e926(bot, update, tags='~what_has_science_done ~where_is_your_god_now')


why_handler = CommandHandler("why", why)
updater.dispatcher.add_handler(why_handler)


@silence
def evaluate(bot, update):
    result = 'Invalid input:\n\n'
    expr = clean(update.message.text)

    with stopit.ThreadingTimeout(EVAL_TIMEOUT) as ctx:
        a = Interpreter()
        out = a(expr)

    if ctx.state == ctx.TIMED_OUT:
        result += 'Timed out.'
    else:
        if out is None:
            result += 'Fuck off lol.'
        elif len(str(out)) > EVAL_MAX_DIGITS:
            result += 'Fuck off lol.'
        else:
            result = out

    logger.info("Processed eval command. Input: " + expr + ", output: " + str(result))
    bot.sendMessage(chat_id=update.message.chat_id, text=str(result))


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


@silence
def unknown(bot, update):
    command = str.strip(re.sub('@[\w]+\s', '', update.message.text + ' ', 1))
    if command in GLOBAL_MESSAGES.keys():
        bot.sendMessage(chat_id=update.message.chat_id, text=GLOBAL_MESSAGES[command])
    else:
        unknown_reply(bot, update, command)


@silence(age=False, name=True)
def unknown_reply(bot, update, command):
    bot.sendMessage(chat_id=update.message.chat_id, text='Error:\n\nUnknown command: ' + command)


unknown_handler = RegexHandler(r'/.*', unknown)
updater.dispatcher.add_handler(unknown_handler)

logger.info("Bot loaded.")
updater.start_polling()
