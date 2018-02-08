"""yosho plugin:e621 command"""
import time
from random import choice

import requests
from telegram import ChatAction as Ca
from telegram.error import TelegramError
from telegram.ext import CommandHandler

from helpers import clean


# noinspection PyUnusedLocal
def e621(bot, update, bot_globals, tags=None):
    failed = 'Error:\n\ne621 query failed.'

    index = 'https://e621.net/post/index.json'
    chat = update.message.chat
    name = chat.title if chat.username is None else '@' + chat.username
    if name in bot_globals['SFW'].keys() and bot_globals['SFW'][name]:
        index = 'https://e926.net/post/index.json'

    if tags is None:
        tags = clean(update.message.text)

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
            bot_globals['logger'].debug(url)
            try:
                update.message.reply_photo(photo=url, timeout=bot_globals['IMAGE_SEND_TIMEOUT'])
            except TelegramError:
                bot_globals['logger'].debug('TelegramError in e621.')
                update.message.reply_text(text=failed)
        else:
            bot_globals['logger'].debug('Bad tags entered in e621.')
            update.message.reply_text(text=failed)
    else:
        update.message.reply_text(text=failed)


handlers = [[CommandHandler("e621", e621), {'action': Ca.UPLOAD_PHOTO}]]
