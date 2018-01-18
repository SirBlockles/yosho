import csv
import datetime
import functools
import logging
import pickle
import re
import time
import requests
import stopit
import telegram

from random import randint
from asteval import Interpreter
from telegram import ChatAction as Ca
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.error import TelegramError
from telegram.ext import Updater, CommandHandler, InlineQueryHandler, RegexHandler

# initialize bot and logging for debugging #

token_dict = [l for l in csv.DictReader(open('tokens.csv', 'r'))][0]

TOKEN = token_dict['yosho_bot']
MODS = ('wyreyote', 'teamfortress', 'plusreed', 'pixxo', 'radookal', 'pawjob')
LOGGING_MODE = True
LOGGING_LEVEL = logging.DEBUG
MESSAGE_TIMEOUT = 60
FLOOD_TIMEOUT = 20
EVAL_MEMORY = True
EVAL_TIMEOUT = 1
EVAL_MAX_CHARS = 128
COMMANDS = pickle.load(open('COMMANDS.pkl', 'rb'))
INTERPRETERS = pickle.load(open('INTERPRETERS.pkl', 'rb'))

bot = telegram.Bot(token=TOKEN)
updater = Updater(token=TOKEN)
logging.basicConfig(format='%(asctime)s - [%(levelname)s] - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
logger.level = LOGGING_LEVEL + ((not LOGGING_MODE)*100)
logger.info("Loading bot...")
last_commands = {}


# message modifiers decorator.
# name checks if correct bot @name is present if value is True, also passes unnamed commands if value is ALLOW_UNNAMED
def modifiers(method=None, age=True, name=False, mods=False, flood=True, action=None):
    if method is None:  # if method is None optional arguments have been passed, return usable decorator
        return functools.partial(modifiers, age=age, name=name, mods=mods, flood=flood, action=action)

    @functools.wraps(method)
    def wrap(*args, **kwargs):  # otherwise wrap function and continue
        global last_commands
        message = args[1].message

        n = re.findall('(?<=[\w])@[\w]+\s', message.text + ' ')
        message_bot = (n[0].lower().strip() if len(n) > 0 else None)  # bot @name used in command if present
        message_user = message.from_user.username  # name of OP/user of command
        message_age = (datetime.datetime.now() - message.date).total_seconds()  # age of message in minutes
        chat = message.chat

        title = chat.type + ' -> ' + (chat.title if chat.username is None else '@' + chat.username)
        logger.info(method.__name__ + ' command called from ' +
               title + ', user: @' + message_user + ', with message text: "' + message.text + '"')

        # check incoming message attributes
        if (not age or message_age < MESSAGE_TIMEOUT) and\
                (not name or message_bot == bot.name.lower() or (message_bot is None and name == 'ALLOW_UNNAMED'))\
                and (not mods or message_user.lower() in MODS):
            if action:
                args[0].sendChatAction(chat_id=message.chat_id, action=action)

            # flood detector
            start = time.time()
            if flood and not chat.type == 'private':
                if message_user in last_commands.keys() and not message_user.lower() in MODS:
                    elapsed = start-last_commands[message_user]
                    if elapsed < FLOOD_TIMEOUT:
                        admins = [x.user.username for x in bot.getChatAdministrators(chat_id=message.chat_id,
                                                                                     message_id=message.message_id)]
                        if bot.username in admins:
                            bot.deleteMessage(chat_id=message.chat_id, message_id=message.message_id)
                        elif LOGGING_MODE:
                            logger.debug("flood detector couldn't delete command")
                        logger.info('message canceled by flood detection: ' + str(elapsed))
                        return
                last_commands[message_user] = time.time()

            method(*args, **kwargs)
            end = time.time()

            logger.debug('time elapsed (seconds): ' + str(end - start))
        else:
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
    global LOGGING_MODE
    message = ("Noodles are the best, no doubt, can't deny - tastes better than water, but don't ask you why",
               "But then again, many things can be tasty - cornbread, potatoes, rice, and even pastries")
    update.message.reply_text(text=message[LOGGING_MODE])
    LOGGING_MODE ^= True
    logger.level = LOGGING_LEVEL + ((not LOGGING_MODE)*100)
    logger.info('Debugging mode set to ' + str(LOGGING_MODE).lower())


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

    logger.debug("Processed echo command. Input: " + reply)


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
            logger.debug(p)
            update.message.reply_photo(photo=p)
            time.sleep(.5)  # rate limit, can be lowered to .25 if needed.

        except TelegramError:
            logger.debug('TelegramError in e926 call, post value: ' + str(p))
        except ValueError:
            logger.info('ValueError in e926 call, probably incorrect tags')
            update.message.reply_text(text=failed)
    else:
        update.message.reply_text(text=failed)


e926_handler = CommandHandler("e926", e926)
updater.dispatcher.add_handler(e926_handler)


def why(bot, update):
    e926(bot, update, tags='~what_has_science_done ~where_is_your_god_now')


why_handler = CommandHandler("why", why)
updater.dispatcher.add_handler(why_handler)


@modifiers(mods=True)
def interpreters(bot, update):
    global INTERPRETERS
    global EVAL_MEMORY
    msg = clean(update.message.text)
    if msg == 'clear':
        INTERPRETERS = {}
        pickle.dump(INTERPRETERS, open('INTERPRETERS.pkl', 'wb+'))
        update.message.reply_text(text='Cleared interpreters.')
    elif msg == 'toggle':
        EVAL_MEMORY ^= True
        update.message.reply_text(text='Eval interpreter memory: ' + str(EVAL_MEMORY))
    else:
        update.message.reply_text(text='Invalid input:\n\nUnknown command: ' + msg)


interpreters_handler = CommandHandler("interp", interpreters)
updater.dispatcher.add_handler(interpreters_handler)


@modifiers(name='ALLOW_UNNAMED', action=Ca.TYPING)
def evaluate(bot, update, cmd=None, symbols=None):
    global INTERPRETERS
    result = 'Invalid input:\n\n'

    expr = cmd if cmd else clean(update.message.text)

    # execute command with timeout
    name = update.message.from_user.username
    with stopit.ThreadingTimeout(EVAL_TIMEOUT) as ctx:
        interp = Interpreter()
        if EVAL_MEMORY and name in INTERPRETERS.keys():
            interp.symtable = {**INTERPRETERS[name], **Interpreter().symtable}
            logger.debug('Loaded interpreter "' + name + '": ' + str(INTERPRETERS[name]))

        preceding = update.message.reply_to_message
        preceding = '' if preceding is None else update.message.reply_to_message.text

        if not symbols:
            symbols = {}
        symbols = {**symbols, **{'MY_NAME': name, 'PRECEDING': preceding}}
        interp.symtable = {**interp.symtable, **symbols}

        out = interp(expr)

        if EVAL_MEMORY:
            INTERPRETERS[name] = {k: interp.symtable[k] for k in interp.symtable.keys() if k not in
                                  Interpreter().symtable.keys() and k not in symbols.keys()}
            pickle.dump(INTERPRETERS, open('INTERPRETERS.pkl', 'wb+'))
            logger.debug('Saved interpreter "' + name + '": ' + str(INTERPRETERS[name]))

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
@modifiers(action=Ca.TYPING)
def macro(bot, update):
    global COMMANDS
    err = 'Macro editor error:\n\n'
    expr = clean(update.message.text)

    if expr == '':
        update.message.reply_text(text='Macro modes:\n\neval (create eval macro)\n'
                                       'inline (create inline macro)\n'
                                       'text (create text macro)\nremove (remove macro)\n'
                                       'list (list macros)\nmodify (modify macro)\n'
                                       'contents (list contents of a macro)\n'
                                       'hide (toggles hiding macro from macro list)')
        return

    args = expr.split(' ')
    mode = args[0]
    name = ''

    if mode not in ('eval', 'text', 'remove', 'list', 'modify', 'contents', 'hide', 'inline'):
        update.message.reply_text(text=err + 'Unknown mode ' + mode + '.')
        return

    if len(args) > 1:
        name = args[1]
    elif not mode == 'list':
        update.message.reply_text(text=err+'Missing macro name.')
        return

    protected = COMMANDS['protected'][0].split(' ')

    user = update.message.from_user.username.lower()
    if name in protected and user not in MODS and mode not in ('contents', 'list'):
        update.message.reply_text(text=err+'Macro ' + name + ' is write protected.')
        return

    if len(args) > 2:
        expr = expr.replace(' '.join(args[:2]), '').strip()
    else:
        expr = None

    keys = COMMANDS.keys()
    if mode == 'eval' and name not in keys:
        if expr is not None:
            COMMANDS[name] = [expr, 'EVAL', False]
            update.message.reply_text(text='Eval macro "' + name + '" created.')
        else:
            print(COMMANDS)
            update.message.reply_text(text=err+'Missing macro code.')

    elif mode == 'text' and name not in keys:
        if expr is not None:
            COMMANDS[name] = [expr, 'TEXT', False]
            update.message.reply_text(text='Text macro "' + name + '" created.')
        else:
            update.message.reply_text(text=err+'Missing macro text.')

    elif mode == 'inline' and name not in keys:
        if expr is not None:
            COMMANDS[name] = [expr, 'INLINE', False]
            update.message.reply_text(text='Inline macro "' + name + '" created.')
        else:
            update.message.reply_text(text=err+'Missing macro text.')

    elif mode == 'modify':
        if name in keys and expr is not None:
            COMMANDS[name][0] = expr
            update.message.reply_text(text='Macro "' + name + '" modified.')
        elif expr is None:
            update.message.reply_text(text=err + 'Missing macro text/code.')
        else:
            update.message.reply_text(text=err+'No macro with name ' + name + '.')

    elif mode == 'remove':
        if name in keys:
            del COMMANDS[name]
            update.message.reply_text(text='Macro "' + name + '" removed.')
        else:
            update.message.reply_text(text=err+'No macro with name ' + name + '.')

    elif mode == 'list':
        if user in MODS and not name == 'visible':
            update.message.reply_text('Existing macros:\n'
                                      + '\n'.join([(bot.name + ' ') * (COMMANDS[k][1] == 'INLINE')
                                                   + k for k in keys if not k == 'protected']))
        else:
            update.message.reply_text('Existing macros:\n'
                                      + '\n'.join([(bot.name + ' ') * (COMMANDS[k][1] == 'INLINE')
                                                   + k for k in keys if not COMMANDS[k][2]]))

    elif mode == 'contents':
        if name in keys:
            if not COMMANDS[name][2] or user in MODS:
                update.message.reply_text('Contents of ' + COMMANDS[name][1].lower() + ' macro ' + name +
                                          ':\n\n' + COMMANDS[name][0])
            else:
                update.message.reply_text(text=err + 'Macro ' + name + ' contents hidden.')
        else:
            update.message.reply_text(text=err + 'No macro with name ' + name + '.')

    elif mode == 'hide':
        if name in keys:
            if user in MODS:
                COMMANDS[name][2] ^= True
                update.message.reply_text('Hide macro ' + name + ': ' + str(COMMANDS[name][2]))
            else:
                update.message.reply_text(text=err + 'Only mods can hide or show macros.')
        else:
            update.message.reply_text(text=err + 'No macro with name ' + name + '.')

    elif name in COMMANDS:
        update.message.reply_text(text=err + 'Macro already exists.')

    COMMANDS = {k: COMMANDS[k] for k in sorted(COMMANDS.keys())}
    pickle.dump(COMMANDS, open('COMMANDS.pkl', 'wb+'))


macro_handler = CommandHandler("macro", macro)
updater.dispatcher.add_handler(macro_handler)


# inline commands
def inline_stuff(bot, update):
    results = list()
    query = update.inline_query.query

    if query in COMMANDS.keys():
        if COMMANDS[query][1] == 'INLINE':
            logger.info('Inline query called: ' + query)
            results.append(
                InlineQueryResultArticle(id=query, title=query,
                                         input_message_content=InputTextMessageContent(COMMANDS[query][0])))
        else:
            return

    update.inline_query.answer(results)


inline_handler = InlineQueryHandler(inline_stuff)
updater.dispatcher.add_handler(inline_handler)


@modifiers(flood=False)
def unknown(bot, update):  # process dict reply commands
    @modifiers(age=False, name=True, action=Ca.TYPING)
    def invalid(bot, update, text):
        update.message.reply_text(text=text)

    @modifiers(age=False, name='ALLOW_UNNAMED', action=Ca.TYPING)
    def known(bot, update, text):
        update.message.reply_text(text=text)

    command = str.strip(re.sub('@[\w]+\s', '', update.message.text + ' ', 1)).split(' ')[0]
    if command in COMMANDS.keys():
        if COMMANDS[command][1] == 'EVAL':  # check if command is code or text
            evaluate(bot, update, cmd=COMMANDS[command][0], symbols={'INPUT': clean(update.message.text)})
        elif COMMANDS[command][1] == 'TEXT':
            known(bot, update, COMMANDS[command][0])
        else:
            update.message.reply_text(text="Macro error:\n\n~That's an inline macro! Try @yosho_bot " + command)
    else:
        invalid(bot, update, 'Error:\n\nUnknown command: ' + command)


unknown_handler = RegexHandler(r'/.*', unknown)
updater.dispatcher.add_handler(unknown_handler)

logger.info("Bot loaded.")
updater.start_polling()
