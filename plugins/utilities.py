"""yosho plugin:utility commands"""
from telegram import ChatAction as Ca
from telegram.ext import CommandHandler, RegexHandler, MessageHandler

from helpers import clean, is_mod

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

    message = update.message
    user = message.from_user
    chat = message.chat
    message_user = user.username if user.username is not None else user.name

    if chat.type == 'private':
        admins_list = [message_user]
    else:
        admins_list = [x.user.username for x in bot.getChatAdministrators(chat_id=message.chat_id,
                                                                          message_id=message.message_id)]

    def scope(modifiers):
        if modifiers:
            if 'mods' in modifiers.keys() and modifiers['mods'] and not is_mod(message_user):
                return False

            admin = message_user in admins_list or is_mod(message_user)

            if 'admins' in modifiers.keys() and modifiers['admins'] and not admin:
                return False

        return True

    text = ''
    name = clean(update.message.text)
    plugins = bot_globals['PLUGINS']

    if name in plugins:
        p = plugins[name]
        text += name + ':\n\n'

        if hasattr(p, 'handlers'):
            for l in p.handlers:
                if isinstance(l[0], (CommandHandler, RegexHandler, MessageHandler)) and scope(l[1]):
                    desc = l[0].callback.__doc__.strip()
                    desc = desc if desc else ''

                    if isinstance(l[0], CommandHandler) and len(l[0].command) == 1:
                        name = '/' + l[0].command[0]
                        if desc:
                            name += ': '
                    else:
                        name = l[0].callback.__name__
                        if desc:
                            if isinstance(l[0], CommandHandler):
                                name += ':\n'
                            else:
                                name += ': '

                    text += '{}{}\n\n'.format(name, desc)

    else:
        text += 'Installed plugins:\n\n' + '\n'.join(plugins.keys())

    update.message.reply_text(text=text.strip())


handlers.append([CommandHandler(['plugin', 'plugins'], list_plugins), {'action': Ca.TYPING}])
