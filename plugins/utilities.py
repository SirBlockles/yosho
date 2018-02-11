"""yosho plugin:utility commands"""
from telegram import ChatAction as Ca
from telegram.ext import CommandHandler, RegexHandler, MessageHandler

from helpers import clean

handlers = []


def start(bot, update, bot_globals):
    """start info"""
    plugins = bot_globals['PLUGINS']

    if 'macro processor' in plugins.keys():
        update.message.text = '/start_info' + bot.name.lower()
        plugins['macro processor'].call_macro(bot, update, bot_globals)
    else:
        update.message.reply_text(text='Yosho bot by @TeamFortress and @WyreYote')


handlers.append([CommandHandler('start', start), {'action': Ca.TYPING, 'name': True, 'age': False}])


def list_plugins(bot, update, bot_globals):
    """lists plugins and their commands"""
    text = ''
    name = clean(update.message.text)
    plugins = bot_globals['PLUGINS']

    if name in plugins:
        p = plugins[name]
        text += name + ':\n\n'

        if hasattr(p, 'handlers'):
            for h, m in p.handlers:
                if isinstance(h, (CommandHandler, RegexHandler, MessageHandler)):
                    desc = h.callback.__doc__.strip()
                    desc = desc if desc else ''

                    if isinstance(h, CommandHandler) and len(h.command) == 1:
                        name = '/' + h.command[0]
                        if desc:
                            name += ': '
                    else:
                        name = h.callback.__name__
                        if desc:
                            if isinstance(h, CommandHandler):
                                name += ':\n'
                            else:
                                name += ': '

                    text += '{}{}\n\n'.format(name, desc)
    else:
        text += 'Installed plugins:\n\n' + '\n'.join(plugins.keys())

    update.message.reply_text(text=text.strip())


handlers.append([CommandHandler(['plugin', 'plugins'], list_plugins), {'action': Ca.TYPING}])
