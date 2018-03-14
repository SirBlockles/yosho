"""yosho plugin:macro processor"""
import json
import shlex
from enum import Enum
from inspect import signature, Parameter
from os.path import dirname

from telegram import Update, ChatAction

from utils.command import Command, Signal
from utils.dynamic import DynamicCommandHandler
from utils.helpers import arg_replace, plural
from .macro import MacroContainer

ABSOLUTE = dirname(__file__)
with open(ABSOLUTE + '/macros.json', 'r') as read:
    MACROS = MacroContainer.from_dict(json.load(read))

handlers = []


class Errors(Enum):
    PERMISSION = "You don't have permission to do that."
    EMPTY_PIPE = "Input pipe is empty."
    NONEXISTENT = 'Macro "{}" does not exist.'
    INPUT_REQUIRED = "Input or pipe required."

    def __str__(self):
        return self.value

    def format(self, *args, **kwargs):
        return str(self).format(*args, **kwargs)


class Flags(Enum):
    INTERNAL = 0
    PHOTO = 1


def new(name, value, _cmd, _ctx):
    """Creates a new macro."""
    return f'Created new {_cmd} macro "{name}".'


def modify(name, value, _ctx):
    """Modifies the contents of a given macro."""
    return 'modify'


def remove(name=None, _ctx=None, _pipe=None):
    """Deletes a given macro."""
    global MACROS
    if isinstance(_pipe, Signal) and _pipe.piped:
        if _pipe.data:
            macros = _pipe.data.macros
            if _ctx['is_mod'] or not any(m.creator != _ctx['user'].id for m in macros):
                MACROS.macros = [m for m in MACROS.macros if m not in macros]
                macros_string = ', '.join(f'"{m.name}"' for m in macros)
                return f"Removed macro{plural(macros)} {macros_string}."

            else:
                return Errors.PERMISSION

        else:
            return Errors.EMPTY_PIPE

    elif name:
        try:
            m = MACROS[name]

        except KeyError:
            return Errors.NONEXISTENT.format(name)

        if _ctx['is_mod'] or _ctx['user'].id == m.id:
            del MACROS[name]
            return f'Removed macro "{name}".'

    else:
        return Errors.INPUT_REQUIRED


def contents(name, _ctx):
    """Displays the contents and attributes of a given macro."""
    try:
        m = MACROS[name]

    except KeyError:
        return Errors.NONEXISTENT.format(name)

    else:
        if _ctx['is_mod'] or m.creator == _ctx['user'].id:
            if _ctx['is_mod']:
                exclude = {'contents'}

            elif not m.hidden:
                exclude = {'contents', 'creator'}

            else:
                return Errors.PERMISSION

        else:
            return Errors.PERMISSION

    return ', '.join(f'{a[0]}: "{a[1]}"' for a in m.zipped() if a[0] not in exclude) + f'\n\nContents:\n{m.contents}'


def show(search_parameters='', _ctx=None):
    """Searches macro list, check /macro help for details.
    Can be piped to "remove" or "attributes" commands.
    Piping example: /macro search "search:/tag" | remove"""
    kwargs = shlex.split(search_parameters)
    try:
        def ar(a, k):
            return arg_replace(a, {'me': _ctx['user'].id} if k == 'creator' else {})

        kwargs = {k.lower(): ar(a, k) for k, a in (k.split(':') for k in kwargs)}

    except ValueError:
        return Signal('Bad input. Accepts key:value pairs.')

    if not _ctx['is_mod']:
        kwargs['hidden'] = False

    subset_sig = signature(MacroContainer.iter_subset).parameters
    unexpected = [f'"{k}"' for k in kwargs if k not in subset_sig or k == 'criteria']
    if unexpected:
        return Signal(f"Unexpected keyword{plural(unexpected)}: {', '.join(unexpected)}.")

    subset = MACROS.subset(**kwargs)
    joined = ', '.join(f'"{m.name}"' for m in subset.macros)
    return Signal(f'Matching macros: {joined}' if subset.macros else
                  'No matching macros found.', data=subset if subset.macros else None)


def attributes(name, args_string, _ctx):
    """Modifies the attributes of a given macro."""
    return 'attributes'


def clean(_ctx):
    """Purges all macros that haven't been protected by a bot moderator."""
    global MACROS
    if _ctx['is_mod']:
        MACROS = MACROS.subset(protected=True)
        return 'Cleaned up macros.'

    else:
        return Errors.PERMISSION


def save(_ctx):
    if _ctx['is_mod']:
        with open(ABSOLUTE + '/macros.json', 'w+') as write:
            json.dump(MACROS.to_dict(), write, indent=2)
        return 'Saved macros.'

    else:
        return Errors.PERMISSION


def info():
    """Displays macro editor help link."""
    return Signal([open(ABSOLUTE + '/control flow graph.png', 'rb'),
                   '/macro help: https://pastebin.com/raw/qzBR6GgB'],
                  flag=Flags.PHOTO)


def sig(name_or_path, _ctx):
    """Displays a given command or sub-command's documentation, aliases and arguments."""
    path = name_or_path.split()
    cmd = _ctx['graph']
    key = None
    last = None
    try:
        for a in path:
            last = a
            key = cmd.key_of(a)
            cmd = cmd.val_of(a)

    except KeyError:
        return f'Command "{last}" not found.'

    else:
        if cmd.func:
            def display(p):
                if p.default is not Parameter.empty:
                    return f'[optional: {p.name}]'

                elif p.kind is Parameter.VAR_POSITIONAL:
                    return '[all remaining args]'

                else:
                    return f'[required: {p.name}]'

            args = (display(p) for k, p in signature(cmd.func).parameters.items() if not k.startswith('_'))
            args = ', '.join(args)
            aliases = ', '.join(k for k in key) if isinstance(key, tuple) else key
            doc = '\n'.join(l.strip() for l in (cmd.func.__doc__ or '').split('\n'))
            return f'[{aliases}] {args}\n{doc}'.strip()

        else:
            return f'Command {path[-1]} has no associated function.'


def pipes(_pipe: Signal):
    """Facilitates piping data between commands."""
    return Signal(_pipe.contents, data=_pipe.data, flag=Flags.INTERNAL, piped=True)


# chains() exists purely to provide a docstring for /macro sig inspection of '&' (chain) nodes.
def chains():
    """Facilitates chaining of commands."""


# <-- CONTROL GRAPH SETUP --> #
# Groups of nodes which are cyclical through an '&' (chain) node.
groups = []
linked = {('photo', 'eval', 'inline', 'text',
           'e621', 'e926', 'markov', 'alias'):                 Command(func=new),
          ('modify', 'change', 'edit', 'alter'):               Command(func=modify),
          ('attribs', 'attributes', 'properties', 'settings'): Command(func=attributes)}
groups.append(Command(linked))

linked = {('remove', 'delete'):                         Command(func=remove)}
groups.append(Command(linked))
linked = {('list', 'show', 'subset', 'search', 'find'): Command(func=show)}
groups.append(Command(linked))
linked = {('contents', 'content', 'value'):             Command(func=contents)}
groups.append(Command(linked))
linked = {('sig', 'doc', 'docs', 'args'):               Command(func=sig)}
groups.append(Command(linked))

# Cyclically link the groups via self reference.
for g in groups:
    for v in g.table.values():
        g.func = chains
        v['&'] = g

# Leaf nodes.
unlinked = {('clean', 'purge'):        Command(func=clean),
            (None, 'help', 'info'):    Command(func=info),
            ('save', 'flush', 'push'): Command(func=save)}
groups.append(Command(unlinked))

# Merge base graphs.
graph = sum(groups, Command())

# Create edges from search node to '|' (pipe) node, and then to editing nodes.
search_key = graph.key_of('search')
remove_key = graph.key_of('remove')
attrib_key = graph.key_of('attribs')
graph[search_key]['|'] = Command({remove_key: graph[remove_key],
                                  attrib_key: graph[attrib_key]},
                                 func=pipes)

# Create edges from remove and attrib '&' (chain) nodes to search and save nodes.
graph[remove_key]['&'][search_key] = graph[search_key]
graph[attrib_key]['&'][search_key] = graph[search_key]

save_key = graph.key_of('save')
graph[remove_key]['&'][save_key] = graph[save_key]
graph[attrib_key]['&'][save_key] = graph[save_key]


def dispatcher(args, update: Update, logger, config):
    """Macro editor dispatcher."""
    msg = update.message
    name = msg.from_user.name

    is_mod = name.lower() in config.get('bot_mods', None) if name else False
    _ctx = {'update': update,
            'user': msg.from_user,
            'logger': logger,
            'is_mod': is_mod,
            'graph': graph}

    try:
        max_chained_commands = config['macro editor']['max chained commands']

    except KeyError:
        max_chained_commands = 5

    if not is_mod and sum(1 for a in args if a == '&') > max_chained_commands:
        msg.reply_text(text='Too many subsequent commands. (max 5)')
        return

    args = [arg_replace(a) for a in args]

    traceback = graph(args, _ctx)
    try:
        img = next(t for t in traceback if isinstance(t, Signal) and t.flag is Flags.PHOTO).contents

    except StopIteration:
        trace_len = len(traceback)
        traceback = (str(t) for t in traceback if
                     (t.flag is not Flags.INTERNAL if isinstance(t, Signal) else True))

        if trace_len > 1:
            traceback = (f'{i}: {t}' for i, t in enumerate(traceback))

        traceback = '\n'.join(traceback)
        traceback = traceback if is_mod else traceback[:config.get('character limit', 256)]
        msg.chat.send_action(ChatAction.TYPING)
        msg.reply_text(text=traceback)

    else:
        timeout = config.get('photo timeout', 10)

        msg.chat.send_action(ChatAction.UPLOAD_PHOTO)
        msg.reply_photo(photo=img[0], caption=img[1], timeout=timeout)
        img[0].close()


handlers.append(DynamicCommandHandler(['macro', 'macros'], dispatcher))
