"""yosho plugin:e621 plugin"""
from http.client import responses
from random import choice
from time import sleep
from typing import Tuple

import requests
from telegram import ChatAction, Update

from utils.dynamic import DynamicCommandHandler

handlers = []


def random_image(tags: str, count: int, sfw: bool, credentials: dict) -> Tuple[str, int]:
    blacklist = '-cub -young'
    index = 'https://e926.net/post/index.json' if sfw else 'https://e621.net/post/index.json'
    headers = {'User-Agent': 'YoshoBot e621 plugin || @WyreYote and @TeamFortress on Telegram'}
    params = {'tags': f'{blacklist} {tags}'.strip(), 'limit': count, **credentials}

    request = requests.get(index, params=params, headers=headers)
    sleep(.5)  # rate limit

    if request.status_code == requests.codes.ok:
        data = request.json()
        posts = [(p['sample_url'], p['id']) for p in data if p['file_ext'] in {'jpg', 'png'}]
        return choice(posts) if posts else None

    else:
        raise requests.ConnectionError(f'Request failed, e621 returned status "{responses[request.status_code]}".')


def e621(update: Update, args, command, tokens, config):
    """[tags]"""
    try:
        limit = config['e621 plugin']['post limit']

    except KeyError:
        limit = 25

    msg = update.message
    try:
        url, pid = random_image(' '.join(args), limit, command == 'e926', tokens['e621'])

    except requests.ConnectionError:
        msg.chat.send_action(ChatAction.TYPING)
        msg.reply_text(text='e621 connection/API error.')

    except TypeError:
        msg.chat.send_action(ChatAction.TYPING)
        msg.reply_text(text='No images found.')

    else:
        timeout = config.get('photo timeout', 10)

        msg.chat.send_action(ChatAction.UPLOAD_PHOTO)
        msg.reply_photo(photo=url, caption=f'https://e621.net/post/show/{pid}', timeout=timeout)


handlers.append(DynamicCommandHandler(['e621', 'e926'], e621))
