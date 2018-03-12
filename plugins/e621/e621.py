"""yosho plugin:e621 plugin"""
from random import choice
from time import sleep
from typing import Tuple

import requests
from telegram import ChatAction

from utils.dynamic import DynamicCommandHandler

handlers = []


def random_image(tags, count, sfw, credentials) -> Tuple[str, int]:
    blacklist = '-cub -young'
    index = 'https://e926.net/post/index.json' if sfw else 'https://e621.net/post/index.json'
    headers = {'User-Agent': 'YoshoBot e621 plugin || @WyreYote and @TeamFortress on Telegram'}
    params = {'tags': '{} {}'.format(blacklist, tags).strip(), 'limit': count, **credentials}

    request = requests.get(index, params=params, headers=headers)
    sleep(.5)  # rate limit

    if request.status_code == requests.codes.ok:
        data = request.json()
        posts = [(p['sample_url'], p['id']) for p in data if p['file_ext'] in {'jpg', 'png'}]
        return choice(posts) if posts else None

    else:
        raise requests.ConnectionError('Request failed, e621 returned status code {}.'.format(request.status_code))


def e621(update, args, command, tokens):
    """[tags]"""
    try:
        url, pid = random_image(' '.join(args), 25, command == 'e926', tokens['e621'])

    except requests.ConnectionError:
        update.message.chat.send_action(ChatAction.TYPING)
        update.message.reply_text(text='e621 connection/API error.')

    except TypeError:
        update.message.chat.send_action(ChatAction.TYPING)
        update.message.reply_text(text='No images found.')

    else:
        update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
        update.message.reply_photo(photo=url, caption='https://e621.net/post/show/' + str(pid))


handlers.append(DynamicCommandHandler(['e621', 'e926'], e621))
