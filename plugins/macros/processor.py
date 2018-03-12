"""yosho plugin: macro processor"""
import json
from os.path import dirname

from utils.command import Command
from utils.dynamic import DynamicCommandHandler
from .macro import MacroContainer, Macro

ABSOLUTE = dirname(__file__)
with open(ABSOLUTE + '/macros.json', 'r') as read:
    MACROS = MacroContainer.from_dict(json.load(read))

handlers = []


def new(name, value, cmd, ctx):
    pass


def modify(name, value, ctx):
    pass


def remove(name, ctx):
    pass


def contents(name, ctx):
    pass


def show(*args, ctx):
    pass


def attributes(name, *args, ctx):
    pass


def clean(ctx):
    pass


def info(): return '/macro help: https://pastebin.com/raw/qzBR6GgB'


table = {('photo', 'eval', 'inline', 'text', 'e621', 'markov', 'alias'): Command(func=new),
         ('modify', 'change', 'edit', 'alter'):                          Command(func=modify),
         ('remove', 'delete'):                                           Command(func=remove),
         ('contents', 'content', 'value'):                               Command(func=contents),
         ('list', 'show', 'subset', 'search', 'find'):                   Command(func=show),
         ('attribs', 'attributes', 'properties', 'settings'):            Command(func=attributes),
         ('clean', 'purge'):                                             Command(func=clean),
         (None, 'help', 'info'):                                         Command(func=info)}
dispatcher = Command(table)

# Create a link back to starting state from each child state.
exclude = {None, 'clean', 'attribs'}
for k, v in dispatcher.table.items():
    # Exclude specified states from back-linking.
    if not any(e in k for e in exclude):
        v['&'] = dispatcher


def dispatch(args, update, logger, config):
    name = update.message.from_user.name
    is_mod = name.lower() in config.get('bot_mods', None) if name else False
    ctx = {'update': update,
           'logger': logger,
           'is_mod': is_mod}

    try:
        max_chained_commands = config['macro editor']['max chained commands']

    except KeyError:
        max_chained_commands = 5

    if not is_mod and sum(1 for a in args if a == '&') > max_chained_commands:
        update.message.reply_text(text='Too many subsequent commands. (max 5)')
        return

    traceback = dispatcher(args, ctx)
    if len(traceback) > 1:
        traceback = ('{}: {}'.format(i, v) for i, v in enumerate(traceback))

    update.message.reply_text(text='\n'.join(traceback))


handlers.append(DynamicCommandHandler(['macro', 'macros'], dispatch))
