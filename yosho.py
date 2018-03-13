import logging
import os
from functools import wraps
from importlib import import_module
from inspect import signature
from json import load
from re import match

from telegram.ext import Updater

PLUGINS = {}

with open('config.json', 'r') as config:
    CONFIG = load(config)

with open('tokens.json', 'r') as tokens:
    TOKENS = load(tokens)

updater = Updater(token=TOKENS['beta'])

logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


def err(bot, update, error):
    logger.error('update "{}" caused error "{}"'.format(update, error))


updater.dispatcher.add_error_handler(err)

passable = {'plugins': (lambda: PLUGINS),
            'logger':  (lambda: logger),
            'config':  (lambda: CONFIG),
            'tokens':  (lambda: TOKENS)}


def pass_globals(callback):
    @wraps(callback)
    def wrapper(*args, **kwargs):
        sig = signature(callback).parameters
        passes = {k: v() for k, v in passable.items() if k in sig}
        return callback(*args, **passes, **kwargs)

    return wrapper


# Find plugins in their directories and add them to the PLUGINS dictionary.
for directory in (s for s in os.listdir('plugins') if os.path.isdir('plugins/' + s)):
    for fn in (s[:-3] for s in os.listdir('plugins/' + directory) if s.endswith('.py')):
        plugin = import_module('plugins.{}.{}'.format(directory, fn))

        name = match(r'yosho plugin:([\w\s]+)', plugin.__doc__ or '')
        if name:
            PLUGINS[name.group(1)] = plugin

# Load plugins in specified order.
for k in sorted(PLUGINS, key=lambda k: PLUGINS[k].order if hasattr(PLUGINS[k], 'order') else 0):
    if hasattr(PLUGINS[k], 'handlers'):
        for h in PLUGINS[k].handlers:
            if not isinstance(h, list):
                h = [h]

            # Wrap callback function with globals if required.
            if any(a in passable for a in signature(h[0].callback).parameters):
                h[0].callback = pass_globals(h[0].callback)

            updater.dispatcher.add_handler(*h)

    logger.debug('loaded plugin "{}"'.format(k[0]))

updater.start_polling(clean=True)
logger.info('bot loaded')
