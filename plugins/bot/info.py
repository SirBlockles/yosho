"""yosho plugin:bot info"""
from inspect import getdoc

from telegram import ChatAction
from telegram.ext import Filters

from utils.dynamic import DynamicCommandHandler

handlers = []


def _func_summary(h):
    return f'[{", ".join("/" + c for c in h.command)}] {getdoc(h.callback) or ""}'


def list_plugins(args, chat, message, plugins):
    """[list] or ["plugin name"] Lists plugins and their commands."""
    chat.send_action(ChatAction.TYPING)
    if args:
        if args[0].lower() == 'list':
            message.reply_text(text='Installed plugins:\n\n' + '\n'.join(p for p in plugins))

        elif args[0] in plugins:
            p = plugins[args[0]]
            names = f'"{args[0]}" plugin has no commands.'
            if hasattr(p, 'handlers') and p.handlers:
                if any(True for h in p.handlers if isinstance(h, DynamicCommandHandler)):
                    names = f'"{args[0]}" plugin commands:\n'
                    names += '\n'.join(_func_summary(h) for h in p.handlers if isinstance(h, DynamicCommandHandler))

            message.reply_text(names.strip())

        else:
            message.reply_text(f'No plugin named "{args[0]}".')

    else:
        message.reply_text('Proper usage:\n[/plugin, /plugins] [list] or ["plugin name"]')


handlers.append(DynamicCommandHandler(['plugins', 'plugin'], list_plugins))


def documentation(args, chat, message, plugins):
    """[/command] Lists command aliases and documentation."""
    chat.send_action(ChatAction.TYPING)
    if args:
        cmd = args[0].lstrip('/')
        h_list = (h for p in plugins.values() if hasattr(p, 'handlers')
                  for h in p.handlers if isinstance(h, DynamicCommandHandler))

        try:
            h = next(h for h in h_list if cmd in h.command)
            message.reply_text(_func_summary(h).strip())

        except StopIteration:
            message.reply_text(f'No command named "/{cmd}" found.')

    else:
        message.reply_text('Proper usage:\n[/docs, /doc, /sig, /args] [/command]]')


handlers.append(DynamicCommandHandler(['docs', 'doc', 'sig', 'args'], documentation))


def start(message):
    message.reply_text('Yosho bot by @TeamFortress and @WyreYote.')


handlers.append(DynamicCommandHandler('start', start, Filters.private))
