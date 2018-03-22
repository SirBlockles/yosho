"""yosho plugin:bot administration"""
from functools import reduce
from json import dumps, loads

from telegram import ChatAction, ParseMode
from telegram.ext import Filters

from utils.command import Command
from utils.dynamic import DynamicCommandHandler
from utils.helpers import translate_args

handlers = []
mod_filter = None
config_graph = Command()


def init(config):
    global mod_filter, config_graph
    mod_filter = Filters.user(username=config['bot mods'])

    config_graph = Command({'set':  Command(callback=set_config)})
    config_graph['set']['&'] = config_graph
    config_graph['get'] = Command(callback=get_config)
    config_graph[None] = Command(callback=lambda: 'Usage: /config [[set, get]] [[path]] [[value]]')


def die(message, chat, updater):
    """Kills the bot humanely."""
    chat.send_action(ChatAction.TYPING)
    message.reply_text('KMS.')
    updater.stop()


handlers.append(DynamicCommandHandler('kys', die, filters=mod_filter))


def _get_nested_member(path, config):
    return reduce(lambda d, k: d[k], path, config)


def set_config(*args, _ctx):
    if not args:
        return 'Usage: /config set [[path]] [[value]]'

    *path, value = args
    path_str = 'config' + ''.join(f"[['{k}']]" for k in path)
    config = _ctx['config']

    try:
        old_value = _get_nested_member(path, config)

    except KeyError:
        return f'Path {path_str} does not exist.'

    # Try casting with translate_args.
    value = translate_args(value)

    if isinstance(value, str):
        try:
            # Cast from json string if possible.
            # Allows dict, list, etc. inputs.
            value = loads(f'{{"":{value}}}')['']

        except ValueError:
            pass

    if type(old_value) is not type(value):
        return f'Type mismatch, {path_str} expects type ' \
               f'"{type(old_value).__name__}" but got type "{type(value).__name__}".'

    _get_nested_member(path[:-1], config)[path[-1]] = value
    _ctx['firebase'].get_blob('config.json').upload_from_string(dumps(config, indent=2))

    return f'Changed config{path_str} from {type(old_value).__name__}({old_value}) ' \
           f'to {type(value).__name__}({value}).'


def get_config(*path, _ctx):
    path_str = 'config' + ''.join(f"[['{k}']]" for k in path)

    try:
        value = _get_nested_member(path, _ctx['config'])

    except KeyError:
        return f'Path {path_str} does not exist.'

    else:
        def tree(initializer=value, depth=0):
            indent = '->' * depth
            if isinstance(initializer, dict):
                return '\n' + '\n'.join(f'{indent}{k}: {tree(v, depth+1)}' for k, v in initializer.items())

            else:
                return f"{initializer}"

        return f'```\n{tree().strip()}```'


def config_dispatcher(args, firebase, config, message, chat, logger):
    """[set, get] [path] [value]
    Edits config file."""
    traceback = config_graph(args, ctx={'firebase': firebase,
                                        'config':   config,
                                        'logger':   logger})

    if len(traceback) > 1:
        traceback = (f'{i}: {t}' for i, t in enumerate(traceback))
    traceback = '\n'.join(traceback)

    chat.send_action(ChatAction.TYPING)
    message.reply_text(text=traceback, parse_mode=ParseMode.MARKDOWN)


handlers.append(DynamicCommandHandler('config', config_dispatcher, filters=mod_filter))
