"""yosho plugin:macro processor"""
from utils.command import Command
from utils.dynamic import DynamicFilter, DynamicMessageHandler
from utils.helpers import clip, plural
from .macro import Macro
from functools import partial


def orchestrate(command, args, message, config):
    from .editor import MACROS

    if '|' in args:
        try:
            max_piped = config['macro editor']['max piped macros']

        except KeyError:
            max_piped = 5

        if message.from_user.name not in config['bot mods'] and \
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
                graph[a] = Command(func=partial(lambda *v, _pipe, m: process(m, [*v, _pipe], message), m=MACROS[a]))

        for g in graph.table.values():
            g['|'] = graph

        message.reply_text(clip(str(graph([command] + args)[-1]), config))

    else:
        message.reply_text(clip(process(MACROS[command], args, message), config))


def process(m, args, message):
    return m.contents


def _is_macro(message):
    if message.text and message.text.startswith('!'):
        from .editor import MACROS
        return message.text.split()[0] in MACROS

    return False


handlers = [DynamicMessageHandler(filters=DynamicFilter(_is_macro), callback=orchestrate)]
