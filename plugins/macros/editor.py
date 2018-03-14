"""yosho plugin:macro editor"""
import json
import shlex
from enum import Enum
from functools import wraps
from inspect import signature, Parameter, getdoc
from os.path import dirname

from requests import head
from telegram import Update, ChatAction

from utils.command import Command, Signal
from utils.dynamic import DynamicCommandHandler
from utils.helpers import arg_replace, plural, clip
from .macro import MacroContainer, Macro

ABSOLUTE = dirname(__file__)
with open(ABSOLUTE + '/macros.json', 'r') as read:
    MACROS = MacroContainer.from_dict(json.load(read))

handlers = []


class Errors(Enum):
    """Enum for common error messages.
    Used so changes to error messages are reflected across all commands."""
    PERMISSION = "You don't have permission to do that."
    EMPTY_PIPE = "Input pipe is empty."
    NONEXISTENT = 'Macro "{}" does not exist.'
    INPUT_REQUIRED = "Input or pipe required."
    ALREADY_EXISTS = 'A macro named "{}" already exists'
    BAD_KEYWORDS = 'Command "{}" expects a keyword:value pair or multiple pairs in a quoted string.'
    BAD_PHOTO = "Photo macro content must be a valid photo url."

    def __str__(self):
        return self.value

    def format(self, *args, **kwargs):
        return str(self).format(*args, **kwargs)


class Flags(Enum):
    """Enum for signal flags, simplifies piping."""
    INTERNAL = 0
    PHOTO = 1


# Currently unused but may find use in the future.
def replaces_args(f):
    """Decorator that replaces certain argument values automatically."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        replace = {'true': True, 'false': False, 'none': None}
        args = arg_replace(args, replace)
        kwargs = {k: arg_replace(a, replace) for k, a in kwargs.items()}
        return f(*args, **kwargs)

    return wrapper


def new(name, contents, _cmd, _ctx):
    """Creates a new macro."""
    global MACROS
    variety = Macro.Variety[_cmd.upper()]

    if variety in {Macro.Variety.PHOTO, Macro.Variety.IMAGE}:
        if head(contents).headers.get('content-type') not in {'image/png', 'image/jpeg'}:
            return Errors.BAD_PHOTO

    if name not in MACROS:
        MACROS.append(Macro(name=name,
                            contents=contents,
                            creator=_ctx['user'].id,
                            variety=variety,
                            hidden=False,
                            protected=_ctx['is_mod'],
                            nsfw=False))
        return f'Created new {_cmd} macro "{name}".'

    else:
        return Errors.ALREADY_EXISTS.format(name)


def modify(name, contents, _ctx):
    """Modifies the contents of a given macro."""
    global MACROS
    if name in MACROS:
        m = MACROS[name]
        if m.variety in {Macro.Variety.PHOTO, Macro.Variety.IMAGE}:
            if head(contents).headers.get('content-type') not in {'image/png', 'image/jpeg'}:
                return Errors.BAD_PHOTO

        if _ctx['is_mod'] or m.creator == _ctx['user'].id:
            m.contents = contents
            MACROS[name] = m
            return f'Modified contents of {m.variety.name.lower()} macro "{name}".'

    else:
        return Errors.NONEXISTENT


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
            return Errors.PERMISSION

    else:
        return Errors.INPUT_REQUIRED


def value(name, _ctx):
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


def find(search_parameters='', _ctx=None, _cmd=None):
    """Searches macro list, check /macro help for details.
    Can be piped to "remove" or "attribs" commands.
    Piping example: /macro search creator:me | remove"""
    kwargs = shlex.split(search_parameters)
    try:
        def ar(a, k):
            replace = {'true': True, 'false': False, 'none': None}
            return arg_replace(a, {'me': _ctx['user'].id} if k == 'creator' else replace)

        kwargs = {k.lower(): ar(a, k) for k, a in (k.split(':') for k in kwargs)}

    except ValueError:
        return Signal(Errors.BAD_KEYWORDS.format(_cmd))

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


def attributes(attribs, name=None, _ctx=None, _pipe=None, _cmd=None):
    """Modifies the attributes of a given macro."""
    global MACROS
    kwargs = shlex.split(attribs)
    try:
        def ar(a, k):
            if isinstance(a, str):
                if a.isnumeric():
                    return int(a)

            if k == 'variety':
                a = Macro.Variety[a.upper()]

            replace = {'true': True, 'false': False, 'none': None}
            return arg_replace(a, {'me': _ctx['user'].id} if k == 'creator' else replace)

        kwargs = {k.lower(): ar(a, k) for k, a in (k.split(':') for k in kwargs)}

    except (KeyError, AttributeError, ValueError):
        return Errors.BAD_KEYWORDS.format(_cmd)

    macro_sig = signature(Macro.__init__).parameters

    unexpected = {'contents'}
    if not _ctx['is_mod']:
        unexpected |= {'protected', 'creator'}

    unexpected = [f'"{k}"' for k in kwargs if k not in macro_sig or k in unexpected]
    if unexpected:
        return Signal(f"Unexpected keyword{plural(unexpected)}: {', '.join(unexpected)}.")

    wrong_type = [f'"{k}": {type(a).__name__} != {macro_sig[k].annotation.__name__}'
                  for k, a in kwargs.items() if macro_sig[k].annotation is not type(a)]

    if wrong_type:
        return Signal(f'''Incorrect type for keyword{plural(wrong_type)}: {', '.join(wrong_type)}.''')

    if isinstance(_pipe, Signal) and _pipe.piped:
        if _pipe.data:
            macros = _pipe.data.macros
            if all(k != 'name' for k in kwargs) or len(macros) == 1:
                for m in macros:
                    for k, a in kwargs.items():
                        setattr(m, k, a)

                    MACROS[m.name] = m

                macros_string = ', '.join(f'"{m.name}"' for m in macros)
                return f"Set attributes of macro{plural(macros)} {macros_string}."

            else:
                return 'Cannot batch edit macro names.'

        else:
            return Errors.EMPTY_PIPE

    elif name:
        try:
            m = MACROS[name]

        except KeyError:
            return Errors.NONEXISTENT.format(name)

        if _ctx['is_mod'] or _ctx['user'].id == m.id:
            if name in kwargs and kwargs[name] in MACROS:
                return Errors.ALREADY_EXISTS.format(name)

            for k, a in kwargs.items():
                setattr(m, k, a)

            MACROS[m.name] = m
            return f'Set attributes of macro "{m.name}".'

        else:
            return Errors.PERMISSION

    else:
        return Errors.INPUT_REQUIRED


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
                  'Do /macro docs [command] for info on a specific command.'],
                  flag=Flags.PHOTO)


def sig(name_or_path, _ctx, _cmd):
    """Displays a given command or sub-command's documentation, aliases and arguments."""
    if not isinstance(name_or_path, str):
        return f'Command "{_cmd}" expects type str not {type(name_or_path).__name__}.'

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

            target_sig = signature(cmd.func).parameters.items()
            args = ', '.join(display(p) for k, p in target_sig if not k.startswith('_'))
            aliases = ', '.join(k for k in key) if isinstance(key, tuple) else key
            return f'[{aliases}] {args}\n{getdoc(cmd.func)}'.strip()

        else:
            return f'Command {path[-1]} has no associated function.'


def pipes(_pipe: Signal):
    """Facilitates piping of data between commands."""
    return Signal(_pipe.contents, data=_pipe.data, flag=Flags.INTERNAL, piped=True)


# This exists purely to provide a docstring for /macro sig inspection of '&' (chain) nodes.
def chains():
    """Facilitates chaining of commands."""


# <-- CONTROL GRAPH SETUP --> #
# Groups of nodes which are cyclical through an '&' (chain) node.
groups = []
linked = {tuple(s.name.lower() for s in Macro.Variety):                Command(func=new),
          ('modify', 'change', 'edit', 'alter'):               Command(func=modify),
          ('attribs', 'attributes', 'properties', 'settings'): Command(func=attributes)}
groups.append(Command(linked))

linked = {('remove', 'delete'):                         Command(func=remove)}
groups.append(Command(linked))
linked = {('list', 'show', 'subset', 'search', 'find'): Command(func=find)}
groups.append(Command(linked))
linked = {('contents', 'content', 'value'):             Command(func=value)}
groups.append(Command(linked))
linked = {('sig', 'doc', 'docs', 'args'):               Command(func=sig)}
groups.append(Command(linked))

# Cyclically link the groups via self reference.
for g in groups:
    for v in g.table.values():
        v['&'] = Command(func=chains) + g

# Leaf nodes.
unlinked = {(None, 'help', 'info'):    Command(func=info),
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

# Create edges from remove, edit, new and attrib '&' (chain) nodes to search and save nodes.
graph[remove_key]['&'][search_key] = graph[search_key]
graph[attrib_key]['&'][search_key] = graph[search_key]

save_key = graph.key_of('save')
graph[remove_key]['&'][save_key] = graph[save_key]
graph[attrib_key]['&'][save_key] = graph[save_key]

edit_key = graph.key_of('edit')
new_key = graph.key_of('text')
graph[edit_key]['&'][save_key] = graph[save_key]
graph[new_key]['&'][save_key] = graph[save_key]


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

    if not is_mod and sum(1 for a in args if a == '&') > max_chained_commands - 1:
        msg.reply_text(text=f'Too many subsequent commands. (max {max_chained_commands})')
        return

    args = arg_replace(args, {'...': ...})
    traceback = graph(args, _ctx)

    def flag(t):
        return t.flag if isinstance(t, Signal) else None

    if any(flag(t) is Flags.PHOTO for t in traceback):
        file, caption = next(t for t in traceback if flag(t) is Flags.PHOTO).contents

        msg.chat.send_action(ChatAction.UPLOAD_PHOTO)
        msg.reply_photo(photo=file, caption=caption, timeout=config.get('photo timeout', 10))
        file.close()

    else:
        trace_len = len(traceback)
        traceback = (str(t) for t in traceback if flag(t) is not Flags.INTERNAL)

        if trace_len > 1:
            traceback = (f'{i}: {t}' for i, t in enumerate(traceback))

        traceback = '\n'.join(traceback)

        if not is_mod:
            traceback = clip(traceback, config)

        msg.chat.send_action(ChatAction.TYPING)
        msg.reply_text(text=traceback)


handlers.append(DynamicCommandHandler(['macro', 'macros'], dispatcher))
