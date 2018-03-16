"""yosho plugin:macro processor"""
from telegram import ChatAction

from utils.command import Command
from utils.dynamic import DynamicFilter, DynamicMessageHandler
from utils.helpers import clip, plural, arg_replace, valid_photo
from .macro import Macro


def orchestrate(command, args, message, user, chat, config, plugins, tokens):
    from .editor import MACROS

    if '|' in args:
        try:
            max_piped = config['macro editor']['max piped macros']

        except KeyError:
            max_piped = 5

        if user.name not in config['bot mods'] and \
                sum(1 for a in args if a == '|') > max_piped - 1:
            message.reply_text(f'Too many piped macros. (max {max_piped})')
            return

        def is_macro_name(a):
            return a.startswith('!') and not a == '|'

        if any(is_macro_name(a) and a not in MACROS for a in args):
            not_found = [f'"{a}"' for a in args if is_macro_name(a) and a not in MACROS]
            message.reply_text(f'Macro{plural(not_found)} {" ,".join(not_found)} not found.')
            return

        if MACROS[command].variety not in {Macro.Variety.TEXT,
                                           Macro.Variety.EVAL,
                                           Macro.Variety.MARKOV}:
            message.reply_text(f"Pipe start macro must be eval, text, "
                               f"or markov, not {MACROS[command].variety.name.lower()}.")
            return

        bad = [MACROS[a].variety.name.lower() for a in args if is_macro_name(a) and MACROS[a].variety not in
               {Macro.Variety.EVAL, Macro.Variety.MARKOV}]

        if bad:
            message.reply_text(f'Subsequent pipe macro{plural(bad)} must be eval or markov, not {" ,".join(bad)}')
            return

        graph = Command(func=lambda _pipe: _pipe)

        for a in [command] + args:
            if is_macro_name(a):
                graph[a] = Command(func=lambda *v, _pipe, m=MACROS[a]:
                                   process(m=m,
                                           args=[_pipe, *v],
                                           message=message,
                                           chat=chat,
                                           config=config,
                                           plugins=plugins,
                                           tokens=tokens,
                                           pipe=True))

        for g in graph.table.values():
            g['|'] = graph

        result = str(graph([command] + arg_replace(args))[-1])

        chat.send_action(ChatAction.TYPING)
        message.reply_text(clip(result, config))

    else:
        process(m=MACROS[command],
                args=arg_replace(args),
                message=message,
                chat=chat,
                config=config,
                plugins=plugins,
                tokens=tokens,
                pipe=False)


def process(m: Macro, args, message, chat, config, plugins, tokens, pipe):
    if m.variety is Macro.Variety.TEXT:
        if pipe:
            return m.contents

        else:
            chat.send_action(ChatAction.TYPING)
            message.reply_text(clip(m.contents, config))

    elif m.variety is Macro.Variety.EVAL:
        ...

    elif m.variety is Macro.Variety.MARKOV:
        ...

    elif m.variety in {Macro.Variety.PHOTO, Macro.Variety.IMAGE}:
        if valid_photo(m.contents):
            timeout = config.get('photo timeout', 10)

            chat.send_action(ChatAction.UPLOAD_PHOTO)
            message.reply_photo(photo=m.contents, timeout=timeout)

        else:
            chat.send_action(ChatAction.TYPING)
            message.reply_text(f'Photo macro "{m.name}" contains broken url.')

    elif m.variety in {Macro.Variety.E621, Macro.Variety.E926}:
        e621 = plugins.get('e621 plugin')
        if e621:
            e621.e621(message=message,
                      chat=chat,
                      args=[m.contents] + args,
                      command=m.variety.name.lower(),
                      tokens=tokens,
                      config=config)

        else:
            chat.send_action(ChatAction.TYPING)
            message.reply_text('e621 plugin not installed.')

    elif m.variety is Macro.Variety.ALIAS:
        from .editor import MACROS
        try:
            m = MACROS[m.contents]

        except KeyError:
            chat.send_action(ChatAction.TYPING)
            message.reply_text(f'Alias macro "{m.name}" references macro "{m.contents}" which does not exist.')

        else:
            if m.variety is Macro.Variety.ALIAS:
                chat.send_action(ChatAction.TYPING)
                message.reply_text(f'Cannot process an alias macro that references another alias macro.')

            else:
                process(m=m,
                        args=args,
                        message=message,
                        chat=chat,
                        config=config,
                        plugins=plugins,
                        tokens=tokens,
                        pipe=pipe)


def _is_macro(message):
    if message.text and message.text.startswith('!'):
        from .editor import MACROS
        return message.text.split()[0] in MACROS

    return False


handlers = [DynamicMessageHandler(filters=DynamicFilter(_is_macro), callback=orchestrate)]
