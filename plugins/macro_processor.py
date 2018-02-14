"""yosho plugin:macro processor"""
import logging
import re
import time

import stopit
from asteval import Interpreter
from telegram import ChatAction as Ca
from telegram import InlineQueryResultArticle, InputTextMessageContent
from telegram.error import TelegramError
from telegram.ext import CommandHandler, InlineQueryHandler, MessageHandler
from telegram.ext.filters import Filters

from helpers import clean
from helpers import is_mod, db_push, db_pull
from macro import Macro, MacroSet

ORDER = 2

MACROS_PATH = 'MACROS.json'
db_pull(MACROS_PATH)
MACROS = MacroSet.load(open(MACROS_PATH, 'rb'))

EVAL_MEMORY = True
EVAL_TIMEOUT = 1
EVAL_MAX_OUTPUT = 256
EVAL_MAX_INPUT = 1000

INTERPRETERS = {}
handlers = []


def evaluate(bot, update, bot_globals, cmd=None, symbols=None):
    """safely evaluates simple python code"""
    def no_flood(u):
        bot_globals['last_commands'][u] = time.time() - bot_globals['MESSAGE_TIMEOUT'] * 2

    global INTERPRETERS
    user = update.message.from_user
    message_user = user.username if user.username is not None else user.name

    err = 'Invalid input:\n\n'
    result = err

    expr = (cmd if cmd else clean(update.message.text)).replace('#', '\t')

    if expr == '':
        update.message.text = '/eval_info' + bot.name.lower()
        no_flood(message_user)
        call_macro(bot, update, bot_globals)
        return

    if len(expr) > EVAL_MAX_INPUT:
        update.message.reply_text(err + 'Maximum input length exceeded.')
        return

    name = update.message.from_user.name
    interp = Interpreter()
    if EVAL_MEMORY and name in INTERPRETERS.keys():
        interp.symtable = {**INTERPRETERS[name], **Interpreter().symtable}
        bot_globals['logger'].debug('Loaded interpreter "{}": {}'.format(name, INTERPRETERS[name]))

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
        bot_globals['logger'].debug('Saved interpreter "{}": {}'.format(name, INTERPRETERS[name]))

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


handlers.append([CommandHandler("eval", evaluate), {'action': Ca.TYPING}])


# creates and modifies macro commands
def macro(bot, update, bot_globals):
    """user defined macro editor"""
    def no_flood(u):
        bot_globals['last_commands'][u] = time.time() - bot_globals['MESSAGE_TIMEOUT'] * 2

    global MACROS

    message = update.message
    message_user = message.from_user.username if message.from_user.username is not None else message.from_user.name

    modes = {'eval': 'macro',
             'text': 'macro',
             'inline': 'macro',
             'photo': 'macro',
             'e621': 'macro',
             'alias': 'macro',
             'markov': 'macro',
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
        call_macro(bot, update, bot_globals)
        return

    args = expr.split()
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


handlers.append([CommandHandler("macro", macro), {'action': Ca.TYPING}])


def inline_stuff(bot, update, bot_globals):
    results = list()
    query = update.inline_query.query

    if query in MACROS:
        if MACROS[query].variety == Macro.INLINE:
            bot_globals['logger'].info('Inline query called: ' + query)
            results.append(
                InlineQueryResultArticle(id=query, title=query,
                                         input_message_content=InputTextMessageContent(MACROS[query].content)))
        else:
            return

    update.inline_query.answer(results)


handlers.append([InlineQueryHandler(inline_stuff), None])


def manual_flush(bot, update, bot_globals):
    """flushes interpreters and macro edits"""
    flush(bot, None)
    update.message.reply_text(text='Cleared interpreters and pushed macro updates.')


handlers.append([CommandHandler("flush", manual_flush), {'mods': True, 'action': Ca.TYPING, 'level': logging.DEBUG}])


def call_macro(bot, update, bot_globals):  # process macros and invalid commands.
    """processes macro calls"""
    message = update.message
    quoted = message.reply_to_message
    chat = update.message.chat
    name = chat.title if chat.username is None else '@' + chat.username

    def invalid(text):
        n = re.match('/\w+(@\w+)\s', message.text + ' ')
        message_bot = (n.group(1).lower() if n else None)
        if message_bot == bot.name.lower():
            bot.sendChatAction(chat_id=message.chat_id, action=Ca.TYPING)
            update.message.reply_text(text=text)

    def known(text):
        bot.sendChatAction(chat_id=message.chat_id, action=Ca.TYPING)
        if quoted is None:
            update.message.reply_text(text=text)
        else:
            quoted.reply_text(text=text)

    def photo(url):
        bot.sendChatAction(chat_id=message.chat_id, action=Ca.UPLOAD_PHOTO)
        try:
            if quoted is None:
                update.message.reply_photo(photo=url, timeout=bot_globals['IMAGE_SEND_TIMEOUT'])
            else:
                quoted.reply_photo(photo=url, timeout=bot_globals['IMAGE_SEND_TIMEOUT'])
        except TelegramError:
            bot_globals['logger'].debug('TelegramError in photo macro call: ' + str(url))

    def run(command=None):
        global quoted

        err = "Macro error:\n\n"

        if command is None:
            command = re.sub('@[@\w]+', '', message.text.split()[0])

        if command in MACROS:
            variety = MACROS[command].variety
            content = MACROS[command].content
            if MACROS[command].nsfw and name in bot_globals['SFW'].keys():
                if bot_globals['SFW'][name]:
                    known("{}{} is NSFW, this chat has been marked as SFW by the admins!"
                          .format(command, err))
                    return

            if variety == Macro.EVAL:
                symbols = {'INPUT': clean(message.text),
                           'HIDDEN': MACROS[command].hidden,
                           'PROTECTED': MACROS[command].protected}
                evaluate(bot, update, bot_globals, cmd=content, symbols=symbols)

            elif variety == Macro.TEXT:
                known(content)

            elif variety == Macro.PHOTO:
                photo(content)

            elif variety == Macro.E621:
                if 'e621 command' in bot_globals['PLUGINS'].keys():
                    bot.sendChatAction(chat_id=message.chat_id, action=Ca.UPLOAD_PHOTO)
                    bot_globals['PLUGINS']['e621 command'].e621(bot, update, bot_globals,
                                                 tags='{} {}'.format(content, clean(message.text)))
                else:
                    update.message.reply_text(err + "e621 plugin isn't installed.")

            elif variety == Macro.MARKOV:
                if 'markov generator' in bot_globals['PLUGINS'].keys():
                    bot.sendChatAction(chat_id=message.chat_id, action=Ca.UPLOAD_PHOTO)
                    bot_globals['PLUGINS']['markov generator'].markov(bot, update, bot_globals, seed=
                    '{}{}'.format(content, (bool(clean(message.text)) * ' ') + clean(message.text)))
                else:
                    update.message.reply_text(err + "Markov generator plugin isn't installed.")

            elif variety == Macro.INLINE:
                quoted = None
                known(err + "That's an inline macro! Try @yosho_bot " + command)

            elif variety == Macro.ALIAS:
                run(content)

        else:
            invalid('Error:\n\nUnknown command: ' + command)

    run()


handlers.append([MessageHandler(filters=Filters.command, callback=call_macro), {'name': 'ALLOW_UNNAMED'}])


def flush(bot, job):
    global INTERPRETERS
    INTERPRETERS = {}
    MacroSet.dump(MACROS, open(MACROS_PATH, 'w+'))
    db_push(MACROS_PATH)


def init(bot_globals):
    bot_globals['jobs'].run_repeating(flush, interval=bot_globals['FLUSH_INTERVAL'])
