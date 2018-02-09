"""yosho plugin:utility commands"""
from telegram import ChatAction as Ca
from telegram.ext import CommandHandler, RegexHandler

from helpers import clean

handlers = []


def start(bot, update, bot_globals):
    """start info"""
    if 'macro processor' in bot_globals['PLUGINS'].keys():
        update.message.text = '/start_info' + bot.name.lower()
        bot_globals['PLUGINS']['macro processor'].call_macro(bot, update, bot_globals)
    else:
        update.message.reply_text(text='Yosho bot by @TeamFortress and @WyreYote')


handlers.append([CommandHandler('start', start), {'action': Ca.TYPING, 'name': True, 'age': False}])


def list_plugins(bot, update, bot_globals):
    """lists plugins and their commands"""
    text = ''
    expr = clean(update.message.text)

    if expr in bot_globals['PLUGINS']:
        p = bot_globals['PLUGINS'][expr]
        text += expr + ':\n\n'

        if hasattr(p, 'handlers'):
            for h, m in p.handlers:
                if isinstance(h, (CommandHandler, RegexHandler)):
                    desc = h.callback.__doc__
                    desc = ': ' + desc if desc else ''
                    names = [h.callback.__name__] if isinstance(h, RegexHandler) else h.command
                    text += '/{}{}\n'.format(', /'.join(names), desc)

    else:
        text += 'Installed plugins:\n\n' + '\n'.join(bot_globals['PLUGINS'].keys())

    update.message.reply_text(text=text)


handlers.append([CommandHandler('plugin', list_plugins), {'action': Ca.TYPING}])
