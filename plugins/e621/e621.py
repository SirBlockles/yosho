"""yosho plugin:e621 plugin"""
from http.client import responses
from random import choice
from time import sleep
from timeit import default_timer as dt
from typing import Tuple

import requests
from telegram import ChatAction
from telegram.ext import run_async

from utils.dynamic import DynamicCommandHandler
from utils.helpers import nested_get

handlers = []
last = dt()


def random_image(tags: str, count: int, sfw: bool, credentials: dict, blacklist: Tuple[str]) -> Tuple[str, int]:
    global last

    while dt() - last < .5:
        sleep(.5)

    last = dt()

    index = 'https://e926.net/post/index.json' if sfw else 'https://e621.net/post/index.json'
    headers = {'User-Agent': 'YoshoBot e621 plugin || @WyreYote and @TeamFortress on Telegram'}
    params = {'tags': tags, 'limit': count, **credentials}

    request = requests.get(index, params=params, headers=headers)

    if request.status_code == requests.codes.ok:
        data = request.json()
        posts = [(p['sample_url'], p['id']) for p in data if p['file_ext'] in {'jpg', 'png'}
                 and not any(t in blacklist for t in p['tags'].split())]
        return choice(posts) if posts else None

    else:
        raise requests.ConnectionError(f'"{responses[request.status_code]}"')


@run_async
def e621(message, chat, args, command, tokens, config, plugins):
    """[tags]"""
    sfw = chat.id in nested_get(plugins, ['chat administration', 'CHAT_CONFIG', 'sfw'], set())

    if len(args) > 6:
        chat.send_action(ChatAction.TYPING)
        message.reply_text('Too many tags. (max 6)')
        return

    try:
        url, pid = random_image(' '.join(args),
                                nested_get(config, ['e621 plugin', 'post limit'], 25),
                                sfw or command == 'e926',
                                tokens['e621'],
                                nested_get(config, ['e621 plugin', 'blacklist'], ['cub', 'young']))

    except requests.ConnectionError as e:
        chat.send_action(ChatAction.TYPING)
        message.reply_text(f'e621 API Error: {e}')

    except TypeError:
        chat.send_action(ChatAction.TYPING)
        message.reply_text('No images found.')

    else:
        timeout = config.get('photo timeout', 10)

        chat.send_action(ChatAction.UPLOAD_PHOTO)
        message.reply_photo(photo=url, caption=f'https://e621.net/post/show/{pid}', timeout=timeout)


handlers.append(DynamicCommandHandler(['e621', 'e926'], e621))
