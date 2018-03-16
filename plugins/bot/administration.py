"""yosho plugin:bot administration plugin"""
from telegram import ChatAction, ParseMode
from telegram.ext import Filters

from utils.dynamic import DynamicCommandHandler
from utils.helpers import arg_replace
from functools import reduce
from json import dumps, loads

handlers = []
mod_filter = None


def init(config):
    global mod_filter
    mod_filter = Filters.user(username=config['bot mods'])


def die(message, chat, updater):
    """Kills the bot humanely."""
    chat.send_action(ChatAction.TYPING)
    message.reply_text('KMS.')
    updater.stop()


handlers.append(DynamicCommandHandler('kys', die, filters=mod_filter))


def config_manager(args, firebase, config, message, chat):
    """[set, get, tree] [key path] [value]
    Edits config file."""
    chat.send_action(ChatAction.TYPING)

    if len(args) > 1 and args[0] in {'set', 'get'}:
        if args[0] == 'set':
            *keys, new_value = args[1:]

        else:
            keys = args[1:]
            new_value = None

        path_str = ''.join(f'["{k}"]' for k in keys)

        def is_list(s):
            if s.startswith('[') and s.endswith(']'):
                try:
                    return loads(f'''{{"dummy": {s.replace("'", '"')}}}''')['dummy']

                except ValueError:
                    return False

            else:
                return False

        new_value = arg_replace(new_value, {'true':        True,
                                            'false':       False,
                                            str.isnumeric: int,
                                            is_list:       is_list})
        try:
            old_value = reduce(lambda d, k: d[k], keys, config)

        except KeyError:
            message.reply_text(f'Path config{path_str} does not exist.')

        else:
            if args[0] == 'set' and isinstance(old_value, dict):
                if new_value in old_value:
                    message.reply_text('Missing value argument.')

                else:
                    message.reply_text(f'Incomplete path config{path_str}.')

            elif args[0] == 'set' and not isinstance(new_value, type(old_value)):
                message.reply_text(f'Type mismatch, config{path_str} '
                                   f'expects type "{type(old_value).__name__}" '
                                   f'but got type "{type(new_value).__name__}".')

            elif args[0] == 'set':
                reduce(lambda d, k: d[k], keys[:-1], config)[keys[-1]] = new_value
                firebase.get_blob('config.json').upload_from_string(dumps(config))

                message.reply_text(f'Changed config{path_str} from '
                                   f'{type(old_value).__name__}({old_value}) to '
                                   f'{type(new_value).__name__}({new_value}).\n'
                                   f'You may need to restart me for the changes to be applied.')

            elif args[0] == 'get':
                if isinstance(old_value, dict):
                    message.reply_text(f'Incomplete path config{path_str}.')

                else:
                    message.reply_text(f'config{path_str}: {old_value}')

    elif args[0] == 'tree':
        def tree(dictionary=config, depth=0):
            return '\n'.join(f'{k}\n{tree(v, depth+1)}' if isinstance(v, dict) else '->' * depth + str(k)
                             for k, v in dictionary.items())

        message.reply_text(f'```\n{tree()}```', parse_mode=ParseMode.MARKDOWN)

    else:
        message.reply_text('Usage: /config [set, get, tree] [key path] [value]')


handlers.append(DynamicCommandHandler('config', config_manager, filters=mod_filter))
