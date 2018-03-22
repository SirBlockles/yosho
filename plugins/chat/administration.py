"""yosho plugin:chat administration"""
import json

from utils.dynamic import DynamicCommandHandler, DynamicFilter
from utils.helpers import nested_get

CHAT_CONFIG = {}
handlers = []


def init(firebase, config):
    global CHAT_CONFIG
    path = nested_get(config, ['chat administration', 'firebase chat config path'], 'chat_config.json')
    blob = firebase.get_blob(path)

    if not blob:
        raise FileNotFoundError(f'File {path} not found in Firebase bucket.')

    CHAT_CONFIG = json.loads(blob.download_as_string())
    CHAT_CONFIG = {k: set(v) if isinstance(v, list) else v for k, v in CHAT_CONFIG}


def _push_chat_config(config, firebase):
    path = nested_get(config, ['chat administration', 'firebase chat config path'], 'chat_config.json')
    blob = firebase.get_blob(path)

    _ = {k: list(v) if isinstance(v, set) else v for k, v in CHAT_CONFIG}
    blob.upload_as_string(json.dumps(_))


def _is_admin(message):
    chat = message.chat

    if message.user.id in (u.user.id for u in chat.get_administrators):
        return True

    return False


chat_mod_filter = DynamicFilter(func=_is_admin)


def sfw_status(command, chat, config, firebase):
    sfw = CHAT_CONFIG['sfw']
    if command == 'sfw':
        sfw.add(chat.id)

    else:
        sfw.discard(chat.id)

    CHAT_CONFIG['sfw'] = sfw

    _push_chat_config(config, firebase)


handlers.append(DynamicCommandHandler(['nsfw', 'sfw'], sfw_status, filters=chat_mod_filter))
