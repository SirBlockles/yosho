"""yosho plugin:e621 command"""
import time
from random import choice

import requests
from telegram import ChatAction as Ca
from telegram.error import TelegramError
from telegram.ext import CommandHandler

from helpers import clean

ORDER = 0

handlers = []


# noinspection PyUnusedLocal
def e621(bot, update, bot_globals, tags=None):
    """queries e621/e926 and posts a random image from the first 50 results"""
    def no_flood(u):
        bot_globals['last_commands'][u] = time.time() - bot_globals['MESSAGE_TIMEOUT'] * 2

    failed = 'e621 error:\n\n'

    logger = bot_globals['logger']
    sfw = bot_globals['SFW']

    message = update.message
    message_user = message.from_user.username if message.from_user.username is not None else message.from_user.name

    index = 'https://e621.net/post/index.json'
    chat = update.message.chat
    name = chat.title if chat.username is None else '@' + chat.username

    if name in sfw.keys() and sfw[name]:
        index = 'https://e926.net/post/index.json'

    if tags is None:
        tags = clean(update.message.text)
    else:
        no_flood(message_user)

    # construct the request
    params = {'limit': '50', 'tags': tags}
    headers = {'User-Agent': 'YoshoBot e621 plugin || @WyreYote and @TeamFortress on Telegram'}

    r = requests.get(index, params=params, headers=headers)
    time.sleep(.5)

    if r.status_code == requests.codes.ok:
        data = r.json()
        posts = [p['file_url'] for p in data if p['file_ext'] in ('jpg', 'png')]  # find image urls in json response

        if posts:
            url = choice(posts)
            logger.debug(url)
            try:
                update.message.reply_text(text=url)
            except TelegramError:
                logger.debug('TelegramError in e621.')
                update.message.reply_text(text=failed + 'Telegram error.')
        else:
            logger.debug('Bad tags entered in e621.')
            update.message.reply_text(text=failed + 'No images found.')
    else:
        update.message.reply_text(text=failed + 'e621 API error.')


handlers.append([CommandHandler("e621", e621), {'action': Ca.UPLOAD_PHOTO}])
