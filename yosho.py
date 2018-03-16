import logging
import os
from functools import wraps
from importlib import import_module
from inspect import signature
from json import load, loads
from re import match

import firebase_admin
from firebase_admin import credentials, storage
from telegram.ext import Updater

from utils.helpers import can_pass_to


def init():
    plugins, config, tokens = ({},) * 3

    with open('tokens.json', 'r') as tokens:
        tokens = load(tokens)

    _ = credentials.Certificate(tokens['firebase']['token'])
    firebase_admin.initialize_app(_, {'storageBucket': tokens['firebase']['bucket']})
    firebase = storage.bucket()

    updater = Updater(token=tokens['beta'])

    blob = firebase.get_blob('config.json')
    if not blob:
        raise FileNotFoundError('File config.json not found in Firebase bucket.')

    config = loads(blob.download_as_string())

    logging.basicConfig(format='[%(levelname)s] %(message)s', level=config.get('logging level', logging.INFO))
    logger = logging.getLogger(__name__)

    passable = {'plugins':  (lambda: plugins),
                'logger':   (lambda: logger),
                'config':   (lambda: config),
                'tokens':   (lambda: tokens),
                'firebase': (lambda: firebase),
                'jobs':     (lambda: updater.dispatcher.job_queue),
                'updater':  (lambda: updater)}

    def err(bot, update, error):
        logger.error(f'Bot error: "{error}"')

    updater.dispatcher.add_error_handler(err)

    def pass_globals(callback):
        @wraps(callback)
        def wrapper(*args, **kwargs):
            local_sig = signature(callback).parameters
            passes = {a: v() for a, v in passable.items() if can_pass_to(a, local_sig)}
            return callback(*args, **passes, **kwargs)

        return wrapper

    # Find plugins in their directories and add them to the plugins dictionary.
    for directory in (s for s in os.listdir('plugins') if os.path.isdir('plugins/' + s)):
        for fn in (s[:-3] for s in os.listdir('plugins/' + directory) if s.endswith('.py')):
            plugin = import_module(f'plugins.{directory}.{fn}')

            name = match(r'yosho plugin:([\w\s]+)', plugin.__doc__ or '')
            if name:
                plugins[name.group(1)] = plugin

    # Load plugins in specified order.
    for k in sorted(plugins, key=lambda p: plugins[p].order if hasattr(plugins[p], 'order') else 0):
        if hasattr(plugins[k], 'handlers'):
            for h in plugins[k].handlers:
                if not isinstance(h, list):
                    h = [h]

                # Wrap callback function with globals if required.
                sig = signature(h[0].callback).parameters
                if any(True for a in passable if can_pass_to(a, sig)):
                    h[0].callback = pass_globals(h[0].callback)

                updater.dispatcher.add_handler(*h)
                logger.debug(f'Hooked handler function "{h[0].callback.__name__}" from plugin {k}.')

        # Initialize plugin if it contains an init function.
        if hasattr(plugins[k], 'init') and callable(plugins[k].init):
            sig = signature(plugins[k].init).parameters
            plugins[k].init(**{a: v() for a, v in passable.items() if can_pass_to(a, sig)})
            logger.debug(f'Initialized plugin "{k}".')

        logger.info(f'Loaded plugin "{k}".')

    updater.start_polling(clean=True)
    logger.info('Bot loaded.')


if __name__ == "__main__":
    init()
