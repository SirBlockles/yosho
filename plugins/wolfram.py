"""yosho plugin:Wolfram Alpha command"""
import io
import re
import xml.etree.ElementTree as Xml

import requests
from PIL import Image, ImageOps
from telegram import ChatAction as Ca
from telegram import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from telegram.ext import CommandHandler, CallbackQueryHandler

from helpers import clean, build_menu

WOLFRAM_RESULTS = {}
WOLFRAM_TIMEOUT = 20

handlers = []

ORDER = 0


# noinspection PyUnusedLocal
def wolfram(bot, update, bot_globals=None):
    message = update.message
    name = message.from_user.name

    err = 'Wolfram|Alpha error:\n\n'
    failed = err + 'Wolfram|Alpha query failed.'

    query = clean(update.message.text)

    if name not in WOLFRAM_RESULTS.keys():
        WOLFRAM_RESULTS[name] = None

    if query != '':
        base = 'http://api.wolframalpha.com/v2/query'
        params = {'appid': bot_globals['WOLFRAM_TOKEN'], 'input': query, 'width': 800}

        r = requests.get(base, params=params)
        tree = Xml.XML(r.text)
        if r.status_code == requests.codes.ok:
            if (tree.attrib['success'], tree.attrib['error']) == ('true', 'false'):
                pods = tree.iterfind('pod')
                buttons = [InlineKeyboardButton(p.attrib['title'], callback_data='w' + str(i))
                           for i, p in enumerate(pods) if not p.attrib['id'] == 'Input']
                markup = InlineKeyboardMarkup(build_menu(buttons, n_cols=2))

                interp = re.sub(' +', ' ', tree.find('pod').find('subpod').find('plaintext').text)

                pods = tree.iterfind('pod')
                WOLFRAM_RESULTS[name] = {i: (p.attrib['title'],
                                             [s for s in p.iterfind('subpod')], interp) for i, p in enumerate(pods)}

                if len(WOLFRAM_RESULTS[name]) > 1:
                    m = message.reply_text('Input interpretation: {}\nChoose result to view:'.format(interp),
                                           reply_markup=markup)
                    bot_globals['jobs'].run_once(wolfram_timeout, WOLFRAM_TIMEOUT, context=(m.message_id, m.chat.id,
                                                                             message.message_id, message.chat_id))
                else:
                    message.reply_text(text=failed)
            else:
                message.reply_text(text=err + "Wolfram|Alpha can't understand your query.")
        else:
            message.reply_text(text=failed)
    else:
        message.reply_text(text=err + 'Empty query.')


handlers.append([CommandHandler("wolfram", wolfram), {'action': Ca.TYPING}])


def wolfram_callback(bot, update, bot_globals=None):
    def album(data):
        output = []
        for idx, subpod in enumerate(data[1]):
            url = subpod.find('img').attrib['src']
            title = subpod.attrib['title']
            caption = 'Selection: {}{}\nInput: {}'.format(data[0], '\nSubpod: ' * bool(title) + title, data[2])

            img_b = io.BytesIO(requests.get(url).content)
            img = Image.open(img_b)
            minimum = 100
            if img.size[0] < minimum or img.size[1] < minimum:  # Hacky way to make sure any image sends.
                pad = sorted([minimum - img.size[0], minimum - img.size[1]])
                img = ImageOps.expand(img, border=pad[1] // 2, fill=255)
            fn = 'temp{}.png'.format(idx)
            img.save(fn, format='PNG')
            output.append(InputMediaPhoto(caption=caption, media=fn))
        return output

    query = update.callback_query
    idx = int(query.data.replace('w', ''))
    name = query.from_user.name
    message = query.message

    if name not in WOLFRAM_RESULTS.keys():
        WOLFRAM_RESULTS[name] = None
        return

    bot.sendChatAction(chat_id=message.chat.id, action=Ca.TYPING)

    if message.chat.type == 'private':
        images = album(WOLFRAM_RESULTS[name][idx])
        for i in images:
            bot.send_photo(caption=i.caption, photo=open(i.media, 'rb'), chat_id=message.chat.id,
                           timeout=bot_globals['IMAGE_SEND_TIMEOUT'])

    elif query.from_user.id == message.reply_to_message.from_user.id:
        images = album(WOLFRAM_RESULTS[name][idx])
        for i in images:
            bot.send_photo(caption=i.caption, photo=open(i.media, 'rb'), chat_id=message.chat.id,
                           reply_to_message_id=message.reply_to_message.message_id,
                           timeout=bot_globals['IMAGE_SEND_TIMEOUT'])

    message.delete()
    WOLFRAM_RESULTS[name] = None


handlers.append([CallbackQueryHandler(wolfram_callback, pattern='^w[0-9]+'), None])


def wolfram_timeout(bot, job):
    try:
        bot.deleteMessage(message_id=job.context[0], chat_id=job.context[1])
    except TelegramError:
        return
    bot.send_message(reply_to_message_id=job.context[2], chat_id=job.context[3],
                     text='Failed to choose an option within {} seconds.\nResults timed out.'
                     .format(WOLFRAM_TIMEOUT))

