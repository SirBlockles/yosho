"""yosho plugin:info commands"""
from telegram import ChatAction

from utils.dynamic import DynamicCommandHandler

handlers = []


def list_plugins(update, args, plugins):
    """[list] or ["plugin name"]"""
    update.message.chat.send_action(ChatAction.TYPING)
    if args:
        if args[0].lower() == 'list':
            update.message.reply_text(text='Installed plugins:\n\n' + '\n'.join(p for p in plugins))

        elif args[0] in plugins:
            p = plugins[args[0]]
            names = '"{}" plugin has no commands.'.format(args[0])
            if hasattr(p, 'handlers') and p.handlers:
                names = '\n'.join(['[{}] {}'.format(str(', '.join('/' + c for c in h.command)), h.callback.__doc__ or
                                                    '') for h in p.handlers if isinstance(h, DynamicCommandHandler)])

            update.message.reply_text(text='"{}" plugin commands:\n{}'.format(args[0], names).strip())

        else:
            update.message.reply_text(text='No plugin named "{}".'.format(args[0]))

    else:
        update.message.reply_text(text='Proper usage:\n[/plugin, /plugins] [list] or ["plugin name"]')


handlers.append(DynamicCommandHandler(['plugins', 'plugin'], list_plugins))


def start(update):
    update.message.reply_text(text='Yosho bot by @TeamFortress and @WyreYote.')


handlers.append(DynamicCommandHandler('start', start))
