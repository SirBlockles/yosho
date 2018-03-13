"""yosho plugin:macro processor"""
import json
import shlex
from enum import Enum
from inspect import signature, Parameter
from os.path import dirname

from utils.command import Command, Signal
from utils.dynamic import DynamicCommandHandler
from utils.helpers import arg_replace
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


class SignalFlags(Enum):
    INTERNAL = 0


def new(name, value, _cmd, _ctx):
    """Creates a new macro."""
    return 'Created new {} macro "{}".'.format(_cmd, name)


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
                return 'Removed macro{} {}.'.format('s' * (len(macros) != 1),
                                                    ', '.join('"{}"'.format(m.name) for m in macros))

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
            return 'Removed macro "{}".'.format(name)

    else:
        return Errors.INPUT_REQUIRED


def contents(name, _ctx):
    """Displays the contents and attributes of a given macro."""
    return name


def show(search_parameters='', _ctx=None):
    """Searches macro list, check /macro help for details.
    Can be piped to "remove" or "attributes" commands.
    Piping example: /macro search "search:/tag" | remove"""
    kwargs = shlex.split(search_parameters)
    try:
        kwargs = {k.lower(): arg_replace(v) for k, v in (k.split(':') for k in kwargs)}

    except ValueError:
        return Signal('Malformed input.')

    if not _ctx['is_mod']:
        kwargs['hidden'] = False

    subset_sig = signature(MacroContainer.iter_subset).parameters
    unexpected = ['"{}"'.format(k) for k in kwargs if k not in subset_sig or k == 'criteria']
    if unexpected:
        return Signal('Unexpected keyword{}: {}.'
                      .format('s' * (len(unexpected) != 1), ', '.join(unexpected)))

    subset = MACROS.subset(**kwargs)
    return Signal(', '.join('"{}"'.format(m.name) for m in subset.macros) if subset.macros else
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
        with open(ABSOLUTE + '/macros.json', 'r') as write:
            json.dump(MACROS.to_dict(), write)
        return 'Saved macros.'

    else:
        return Errors.PERMISSION


def info():
    """Displays macro editor help link."""
    return '/macro help: https://pastebin.com/raw/qzBR6GgB'


def sig(name, _ctx):
    """Displays a given command's documentation, aliases and arguments."""
    try:
        key = _ctx['graph'].key_of(name)
        func = _ctx['graph'][key].func
        if func:
            def display(p):
                if p.default is not Parameter.empty:
                    return '[optional: {}]'.format(p.name)

                elif p.kind is Parameter.VAR_POSITIONAL:
                    return '[all remaining args]'

                else:
                    return '[required: {}]'.format(p.name)

            args = (display(p) for k, p in signature(func).parameters.items() if not k.startswith('_'))
            args = ', '.join(args)
            aliases = ', '.join(k for k in key) if isinstance(key, tuple) else key
            doc = '\n'.join(l.strip() for l in (func.__doc__ or '').split('\n'))
            return '[{}] {}\n\n{}'.format(aliases, args, doc).strip()

        else:
            return 'Command {} has no associated function.'.format(name)

    except KeyError:
        return 'Command "{}" not found.'.format(name)


def pipes(_pipe: Signal):
    return Signal(_pipe.contents, data=_pipe.data, flag=SignalFlags.INTERNAL, piped=True)


# <-- CONTROL GRAPH SETUP --> #
# Groups of nodes which are cyclical through an '&' (chain) node.
groups = []
linked = {('photo', 'eval', 'inline', 'text',
           'e621', 'e926', 'markov', 'alias'): Command(func=new),
          ('modify', 'change', 'edit', 'alter'): Command(func=modify),
          ('attribs', 'attributes', 'properties', 'settings'): Command(func=attributes)}
groups.append(Command(linked))

linked = {('remove', 'delete'): Command(func=remove)}
groups.append(Command(linked))

linked = {('list', 'show', 'subset', 'search', 'find'): Command(func=show)}
groups.append(Command(linked))

linked = {('contents', 'content', 'value'): Command(func=contents)}
groups.append(Command(linked))

# Cyclically link the groups via self reference.
for g in groups:
    for v in g.table.values():
        v['&'] = g

# Leaf nodes.
unlinked = {('clean', 'purge'): Command(func=clean),
            (None, 'help', 'info'): Command(func=info),
            ('sig', 'doc', 'args'): Command(func=sig),
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

# Create edges from '&' (chain) nodes to search node.
graph[remove_key]['&'][search_key] = graph[search_key]
graph[attrib_key]['&'][search_key] = graph[search_key]


def dispatcher(args, update, logger, config):
    """Macro editor dispatcher."""
    name = update.message.from_user.name
    is_mod = name.lower() in config.get('bot_mods', None) if name else False
    _ctx = {'update': update,
            'user': update.message.from_user,
            'logger': logger,
            'is_mod': is_mod,
            'graph': graph}

    try:
        max_chained_commands = config['macro editor']['max chained commands']

    except KeyError:
        max_chained_commands = 5

    if not is_mod and sum(1 for a in args if a == '&') > max_chained_commands:
        update.message.reply_text(text='Too many subsequent commands. (max 5)')
        return

    args = [arg_replace(a) for a in args]

    traceback = graph(args, _ctx)
    trace_len = len(traceback)
    traceback = (str(t) for t in traceback if
                 (t.flag is not SignalFlags.INTERNAL if isinstance(t, Signal) else True))
    if trace_len > 1:
        traceback = ('{}: {}'.format(i, v) for i, v in enumerate(traceback))
    update.message.reply_text(text='\n'.join(traceback))


handlers.append(DynamicCommandHandler(['macro', 'macros'], dispatcher))
