import logging
import os
from functools import wraps
from importlib import import_module
from inspect import signature
from json import load
from re import match

import firebase_admin
from firebase_admin import credentials, storage
from telegram.ext import Updater

PLUGINS = {}

with open('config.json', 'r') as config, open('tokens.json', 'r') as tokens:
    CONFIG = load(config)
    TOKENS = load(tokens)

_ = credentials.Certificate(TOKENS['firebase'])
firebase_admin.initialize_app(_, {'storageBucket': CONFIG['firebase bucket']})
firebase = storage.bucket()

updater = Updater(token=TOKENS['beta'])

logging.basicConfig(format='[%(levelname)s] %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

passable = {'plugins':   (lambda: PLUGINS),
            'logger':    (lambda: logger),
            'config':    (lambda: CONFIG),
            'tokens':    (lambda: TOKENS),
            'firebase':  (lambda: firebase),
            'job_queue': (lambda: updater.dispatcher.job_queue)}


def err(bot, update, error):
    logger.error(f'update "{update}" caused error "{error}"')


updater.dispatcher.add_error_handler(err)


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
        plugin = import_module(f'plugins.{directory}.{fn}')

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

    # Initialize plugin if it contains an init function.
    if hasattr(PLUGINS[k], 'init') and callable(PLUGINS[k].init):
        sig = signature(PLUGINS[k].init).parameters
        PLUGINS[k].init(**{k: v() for k, v in passable.items() if k in sig})

    logger.debug(f'loaded plugin "{k[0]}"')

updater.start_polling(clean=True)
logger.info('bot loaded')
