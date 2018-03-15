"""yosho plugin:macro editor"""
# TODO Gratuitous commenting.
import json
import shlex
from enum import Enum
from inspect import signature, Parameter, getdoc
from os.path import dirname

from requests import head
from telegram import Update, ChatAction

from utils.command import Command, Signal
from utils.dynamic import DynamicCommandHandler
from utils.helpers import arg_replace, plural, clip
from .macro import MacroContainer, Macro

GRAPH = Command()
MACROS = None


def init(firebase, job_queue, config, logger):
    """Grabs macros from firebase and initializes command graph."""
    global MACROS, GRAPH

    blob = firebase.get_blob('macros.json')
    if not blob:
        raise FileNotFoundError('macros.json not found in Firebase bucket.')

    MACROS = MacroContainer.from_dict(json.loads(blob.download_as_string()))

    try:
        interval = config["macro editor"]["macro push interval (minutes)"]

    except KeyError:
        interval = 15

    job_queue.run_repeating(callback=lambda bot, job: push_macros(job.context, logger),
                            interval=60 * interval,
                            context=firebase)

    # <-- CONTROL FLOW GRAPH SETUP --> #
    # Groups of nodes which are cyclical through an '&' (chain) node.
    groups = []
    linked = {tuple(s.name.lower() for s in Macro.Variety):        Command(func=new),
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
    GRAPH = sum(groups, Command())

    # Create edges from search node to '|' (pipe) node, and then to editing nodes.
    search_key = GRAPH.key_of('search')
    remove_key = GRAPH.key_of('remove')
    attrib_key = GRAPH.key_of('attribs')
    GRAPH[search_key]['|'] = Command({remove_key: GRAPH[remove_key],
                                      attrib_key: GRAPH[attrib_key]},
                                     func=pipes)

    # Create edges from remove, edit, new and attrib '&' (chain) nodes to search and save nodes.
    GRAPH[remove_key]['&'][search_key] = GRAPH[search_key]
    GRAPH[attrib_key]['&'][search_key] = GRAPH[search_key]

    save_key = GRAPH.key_of('save')
    GRAPH[remove_key]['&'][save_key] = GRAPH[save_key]
    GRAPH[attrib_key]['&'][save_key] = GRAPH[save_key]

    edit_key = GRAPH.key_of('edit')
    new_key = GRAPH.key_of('text')
    GRAPH[edit_key]['&'][save_key] = GRAPH[save_key]
    GRAPH[new_key]['&'][save_key] = GRAPH[save_key]


def push_macros(firebase, logger):
    """Pushes macros to Firebase, used by both the save command
    function and the repeating job defined above."""
    blob = firebase.get_blob('macros.json')
    if not blob:
        raise FileNotFoundError('macros.json not found in Firebase bucket.')

    blob.upload_from_string(json.dumps(MACROS.to_dict(), indent=2))
    logger.info('Pushed macros to Firebase.')
    return 'Saved macros.'


class Errors(Enum):
    """Enum for shared error messages.
    Used so changes to error messages are reflected across all commands."""
    PERMISSION = "You don't have permission to do that."
    EMPTY_PIPE = "Input pipe is empty."
    NONEXISTENT = 'Macro "{}" does not exist.'
    INPUT_REQUIRED = "Input or pipe required."
    ALREADY_EXISTS = 'A macro named "{}" already exists'
    BAD_KEYWORDS = 'Command "{}" expects a keyword:value pair or multiple pairs in a quoted string.'
    UNEXPECTED_KEYWORDS = "Unexpected keyword{}: {}."
    BAD_PHOTO = "Photo macro content must be a valid photo url."

    def __str__(self):
        return self.value

    def format(self, *args, **kwargs):
        return str(self).format(*args, **kwargs)


class Flags(Enum):
    """Enum for signal flags, simplifies piping."""
    INTERNAL = 0
    PHOTO = 1


def new(name, contents, _cmd, _ctx):
    """Creates a new macro."""
    global MACROS
    variety = Macro.Variety[_cmd.upper()]

    if variety in {Macro.Variety.PHOTO, Macro.Variety.IMAGE}:
        if head(contents).headers.get('content-type') not in {'image/png', 'image/jpeg'}:
            return Errors.BAD_PHOTO

    elif variety is not Macro.Variety.INLINE and not name.startswith('!'):
        return f'Non-inline macros much have names beginning with !, not "{name[0]}".'

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

        if _ctx['is_mod'] or (m.creator == _ctx['user'].id and not m.protected):
            m.contents = contents
            MACROS[name] = m
            return f'Modified contents of {m.variety.name.lower()} macro "{name}".'

        else:
            return Errors.PERMISSION

    else:
        return Errors.NONEXISTENT


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

    attribs = (a for a in m.zipped() if a[0] not in exclude)
    return ', '.join(f'{a[0]}: "{a[1]}"' for a in attribs) + f'\n\nContents:\n{m.contents}'


# Helper function for the next two command functions.
def _ar(a, k, _ctx):
    if isinstance(a, str):
        if a.isnumeric():
            return int(a)

    if k == 'variety':
        a = Macro.Variety[a.upper()]

    replace = {'true': True, 'false': False, 'none': None}
    return arg_replace(a, {'me': _ctx['user'].id} if k == 'creator' else replace)


def find(search_parameters='', _ctx=None, _cmd=None):
    """Searches macro list, check /macro help for details.
    Can be piped to "remove" or "attribs" commands.
    Piping example: /macro search creator:me | remove"""
    kwargs = shlex.split(search_parameters)
    try:
        kwargs = {k.lower(): _ar(a, k, _ctx) for k, a in (k.split(':') for k in kwargs)}

    except ValueError:
        return Signal(Errors.BAD_KEYWORDS.format(_cmd))

    if not _ctx['is_mod']:
        kwargs['hidden'] = False

    subset_sig = signature(MacroContainer.iter_subset).parameters
    unexpected = [f'"{k}"' for k in kwargs if k not in subset_sig or k == 'criteria']
    if unexpected:
        return Signal(Errors.UNEXPECTED_KEYWORDS.format(plural(unexpected), ', '.join(unexpected)))

    wrong_type = [f'"{k}": {type(a).__name__} != {subset_sig[k].annotation.__name__}'
                  for k, a in kwargs.items() if subset_sig[k].annotation is not type(a)]
    if wrong_type:
        return Signal(f'''Incorrect type for keyword{plural(wrong_type)}: {', '.join(wrong_type)}.''')

    subset = MACROS.subset(**kwargs)
    joined = ', '.join(f'"{m.name}"' for m in subset.macros)
    return Signal(f'Matching macros: {joined}' if subset.macros else
                  'No matching macros found.', data=subset if subset.macros else None)


def attributes(attribs, name=None, _ctx=None, _pipe=None, _cmd=None):
    """Modifies the attributes of a given macro."""
    global MACROS
    kwargs = shlex.split(attribs)
    try:
        kwargs = {k.lower(): _ar(a, k, _ctx) for k, a in (k.split(':') for k in kwargs)}

    except (KeyError, AttributeError, ValueError):
        return Errors.BAD_KEYWORDS.format(_cmd)

    macro_sig = signature(Macro.__init__).parameters

    unexpected = {'contents'}
    if not _ctx['is_mod']:
        unexpected |= {'protected', 'creator'}

    unexpected = [f'"{k}"' for k in kwargs if k not in macro_sig or k in unexpected]
    if unexpected:
        return Errors.UNEXPECTED_KEYWORDS.format(plural(unexpected), ', '.join(unexpected))

    wrong_type = [f'"{k}": {type(a).__name__} != {macro_sig[k].annotation.__name__}'
                  for k, a in kwargs.items() if macro_sig[k].annotation is not type(a)]
    if wrong_type:
        return f'''Incorrect type for keyword{plural(wrong_type)}: {', '.join(wrong_type)}.'''

    if isinstance(_pipe, Signal) and _pipe.piped:
        if _pipe.data:
            macros = _pipe.data.macros
            if all(k != 'name' for k in kwargs) or len(macros) == 1:
                if _ctx['is_mod'] or not any(m.creator != _ctx['user'].id or m.protected for m in macros):
                    for m in macros:
                        for k, a in kwargs.items():
                            setattr(m, k, a)

                        MACROS[m.name] = m

                    macros_string = ', '.join(f'"{m.name}"' for m in macros)
                    return f"Set attributes of macro{plural(macros)} {macros_string}."

                else:
                    return Errors.PERMISSION

            else:
                return 'Cannot batch edit macro names.'

        else:
            return Errors.EMPTY_PIPE

    elif name:
        try:
            m = MACROS[name]

        except KeyError:
            return Errors.NONEXISTENT.format(name)

        if _ctx['is_mod'] or (_ctx['user'].id == m.id and not m.protected):
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


def remove(name=None, _ctx=None, _pipe=None):
    """Deletes a given macro."""
    global MACROS
    if isinstance(_pipe, Signal) and _pipe.piped:
        if _pipe.data:
            macros = _pipe.data.macros
            if _ctx['is_mod'] or not any(m.creator != _ctx['user'].id or m.protected for m in macros):
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

        if _ctx['is_mod'] or (_ctx['user'].id == m.id and not m.protected):
            del MACROS[name]
            return f'Removed macro "{name}".'

        else:
            return Errors.PERMISSION

    else:
        return Errors.INPUT_REQUIRED


def save(_ctx):
    """Pushes macro updates."""
    if _ctx['is_mod']:
        return push_macros(_ctx['firebase'], _ctx['logger'])

    else:
        return Errors.PERMISSION


def info():
    """Displays macro editor help."""
    return Signal([open(dirname(__file__) + '/control flow graph.png', 'rb'),
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
            aliases = ', '.join(k for k in key if isinstance(k, str)) if isinstance(key, tuple) else key
            return f'[{aliases}] {args}\n{getdoc(cmd.func)}'.strip()

        else:
            return f'Command {path[-1]} has no associated function.'


def pipes(_pipe: Signal):
    """Facilitates piping of data between commands."""
    return Signal(_pipe.contents, data=_pipe.data, flag=Flags.INTERNAL, piped=True)


# This exists purely to provide a docstring for /macro sig inspection of '&' (chain) nodes.
def chains():
    """Facilitates chaining of commands."""


def dispatcher(args, update: Update, logger, config, firebase):
    """Macro editor dispatcher."""
    msg = update.message
    name = msg.from_user.name

    is_mod = name.lower() in config.get('bot mods', None) if name else False
    _ctx = {'update':   update,
            'user':     msg.from_user,
            'logger':   logger,
            'is_mod':   is_mod,
            'graph':    GRAPH,
            'firebase': firebase}

    try:
        max_chained_commands = config['macro editor']['max chained commands']

    except KeyError:
        max_chained_commands = 5

    if not is_mod and sum(1 for a in args if a == '&') > max_chained_commands - 1:
        msg.reply_text(text=f'Too many subsequent commands. (max {max_chained_commands})')
        return

    args = arg_replace(args, {'...': ...})
    traceback = GRAPH(args, _ctx)

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


handlers = [DynamicCommandHandler(['macro', 'macros'], dispatcher)]
