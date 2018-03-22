"""yosho plugin:macro processor"""
from telegram import ChatAction

from utils.command import Command
from utils.dynamic import DynamicFilter, DynamicMessageHandler
from utils.helpers import clip, translate_args, valid_photo, nested_get
from .macro import Macro

MACROS = {}
SFW = set()


def orchestrate(command, args, text, message, user, chat, config, plugins, tokens):
    global SFW
    SFW = chat.id in nested_get(plugins, ['chat administration', 'CHAT_CONFIG', 'sfw'], set())

    text = text.lstrip(command).strip()

    if '|' in args:
        chat.send_action(ChatAction.TYPING)

        max_piped = nested_get(config, ['macro editor', 'max piped macros'], 3)
        if user.name not in config['bot mods'] and \
                sum(1 for a in args if a == '|') > max_piped - 1:
            message.reply_text(f'Too many piped macros. (max {max_piped})')
            return

        def is_macro_name(i, a):
            return (i == 0 or args[i - 1] == '|') and a.startswith('!')

        for i, a in enumerate([command] + args):
            if is_macro_name(i, a):
                if i > 0:
                    if a not in MACROS:
                        message.reply_text(f'Macro "{a}" not found.')
                        return

                    m = MACROS[a]
                    if m.variety not in {Macro.Variety.EVAL, Macro.Variety.MARKOV}:
                        message.reply_text(f'Subsequent pipe macros must be eval or markov, '
                                           f'"{m.name}" is a {m.variety.name.lower()} macro.')
                        return

                else:
                    m = MACROS[a]
                    if m.variety not in {Macro.Variety.EVAL, Macro.Variety.MARKOV, Macro.Variety.TEXT}:
                        message.reply_text(f'Initial pipe macro must be eval, text or markov, '
                                           f'"{m.name}" is a {m.variety.name.lower()} macro.')
                        return

                if m.nsfw and chat.id in SFW:
                    message.reply_text(f'Macro "{a}" is NSFW, this chat is SFW.')
                    return

        graph = Command(callback=lambda _pipe: _pipe)

        for i, a in enumerate([command] + args):
            if is_macro_name(i, a):
                graph[a] = Command(callback=lambda *v, _pipe, _m=MACROS[a]:
                                   process(m=_m,
                                           args=[_pipe, *v],
                                           text=text,
                                           message=message,
                                           chat=chat,
                                           config=config,
                                           plugins=plugins,
                                           tokens=tokens,
                                           pipe=True))

        for g in graph.table.values():
            g['|'] = graph

        result = str(graph([command] + translate_args(args))[-1])
        message.reply_text(clip(result, config))

    else:
        process(m=MACROS[command],
                args=translate_args(args),
                text=text,
                message=message,
                chat=chat,
                config=config,
                plugins=plugins,
                tokens=tokens,
                pipe=False)


def process(m: Macro, args, text, message, chat, config, plugins, tokens, pipe):
    if m.variety is Macro.Variety.TEXT:
        if pipe:
            return m.contents

        else:
            chat.send_action(ChatAction.TYPING)
            message.reply_text(clip(m.contents, config))

    elif m.variety is Macro.Variety.EVAL:
        if pipe:
            return ...

        else:
            chat.send_action(ChatAction.TYPING)

    elif m.variety is Macro.Variety.MARKOV:
        if pipe:
            return ...

        else:
            chat.send_action(ChatAction.TYPING)

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
            site = 'e621'
            if m.variety is Macro.Variety.E926:
                site = 'e926'

            e621.e621(message=message,
                      chat=chat,
                      args=m.contents.split() + args,
                      command=site,
                      tokens=tokens,
                      config=config,
                      plugins=plugins)

        else:
            chat.send_action(ChatAction.TYPING)
            message.reply_text('e621 plugin not installed.')

    elif m.variety is Macro.Variety.ALIAS:
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
                        text=text,
                        message=message,
                        chat=chat,
                        config=config,
                        plugins=plugins,
                        tokens=tokens,
                        pipe=pipe)


def _is_macro(message):
    if message.text and message.text.startswith('!'):
        from .editor import MACROS as M
        global MACROS
        MACROS = M
        return message.text.split()[0] in MACROS

    return False


handlers = [DynamicMessageHandler(filters=DynamicFilter(_is_macro), callback=orchestrate)]
