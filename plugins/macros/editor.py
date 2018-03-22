"""yosho plugin:macro editor"""
# TODO Gratuitous commenting.
import json
from enum import Enum
from inspect import signature, Parameter, getdoc
from os.path import dirname

from telegram import ChatAction

from utils.command import Command
from utils.dynamic import DynamicCommandHandler
from utils.helpers import translate_args, plural, clip, valid_photo, is_mod, nested_get
from .macro import MacroContainer, Macro

GRAPH = Command()
MACROS = None


def init(firebase, jobs, config, logger):
    """Pulls macros from firebase and initializes command graph."""
    global MACROS, GRAPH

    path = nested_get(config, ['macro editor', 'firebase macro path'], 'macros.json')
    blob = firebase.get_blob(path)
    if not blob:
        raise FileNotFoundError(f'File {path} not found in Firebase bucket.')

    MACROS = MacroContainer.from_dict(json.loads(blob.download_as_string()))

    interval = nested_get(config, ['macro editor', 'macro push interval (minutes)'], 15)
    jobs.run_repeating(callback=lambda bot, job: push_macros(job.context, logger),
                       interval=60 * interval,
                       context=firebase)

    # <-- CONTROL FLOW GRAPH SETUP --> #
    # Groups of nodes which are cyclical through an '&' (chain) node.
    groups = []
    linked = {tuple(s.name.lower() for s in Macro.Variety):        Command(callback=new),
              ('modify', 'change', 'edit', 'alter'):               Command(callback=modify),
              ('attribs', 'attributes', 'properties', 'settings'): Command(callback=attribs,
                                                                           kwargs=':')}
    groups.append(Command(linked))

    linked = {('remove', 'delete'):                         Command(callback=remove)}
    groups.append(Command(linked))
    linked = {('contents', 'content', 'value'):             Command(callback=value)}
    groups.append(Command(linked))
    linked = {('sig', 'doc', 'docs', 'args'):               Command(callback=sig)}
    groups.append(Command(linked))
    linked = {('list', 'show', 'subset', 'search', 'find'): Command(callback=find,
                                                                    kwargs=':')}
    groups.append(Command(linked))

    # Cyclically link the groups via self reference.
    for g in groups:
        for v in g.table.values():
            v['&'] = Command(callback=chains) + g

    # Leaf nodes.
    unlinked = {(None, 'help', 'info'):    Command(callback=info),
                ('save', 'flush', 'push'): Command(callback=save)}
    groups.append(Command(unlinked))

    # Merge base graphs.
    GRAPH = sum(groups, Command())

    # Create edges from search node to '|' (pipe) node, and then to editing nodes.
    search_key = GRAPH.key_of('search')
    remove_key = GRAPH.key_of('remove')
    attrib_key = GRAPH.key_of('attribs')
    GRAPH[search_key]['|'] = Command({remove_key: GRAPH[remove_key],
                                      attrib_key: GRAPH[attrib_key]},
                                     callback=pipes)

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
        raise FileNotFoundError('File macros.json not found in Firebase bucket.')

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
    UNEXPECTED_KEYWORDS = "Unexpected keyword{}: {}."
    ALIAS_NESTING = 'Cannot alias an alias macro.'
    BAD_PHOTO = "Photo macro content must be a valid photo url."
    BAD_ALIAS = 'Macro "{}" does not exist, so it may not be aliased.'
    BAD_NAME = 'Non-inline macros much have names beginning with !, not "{}".'

    def __str__(self):
        return self.value

    def __call__(self, *args, **kwargs):
        return str(self).format(*args, **kwargs)


class Signal:
    """Class which simplifies piping between Command instances."""
    __slots__ = {'contents', 'flag', 'piped', 'data'}

    def __init__(self, contents, data=None, flag=None, piped=False):
        self.contents = contents
        self.flag = flag
        self.piped = piped
        self.data = data

    def __str__(self):
        return str(self.contents)

    def __repr__(self):
        return f'Signal(contents={self.contents}, flag={self.flag}, piped={self.piped}, data={self.data})'


class Flags(Enum):
    """Enum for signal flags."""
    INTERNAL, PHOTO = range(2)


def new(name, contents, _cmd, _ctx):
    """Creates a new macro."""
    global MACROS
    variety = Macro.Variety[_cmd.upper()]

    if variety in {Macro.Variety.PHOTO, Macro.Variety.IMAGE} and not valid_photo(contents):
        return Errors.BAD_PHOTO

    if variety is Macro.Variety.ALIAS:
        if contents not in MACROS:
            return Errors.BAD_ALIAS(contents)

        elif MACROS[contents].variety is Macro.Variety.ALIAS:
            return Errors.ALIAS_NESTING

    elif variety is not Macro.Variety.INLINE and not name.startswith('!'):
        return Errors.BAD_NAME(name[0])

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
        return Errors.ALREADY_EXISTS(name)


def modify(name, contents, _ctx):
    """Modifies the contents of a given macro."""
    global MACROS
    if name in MACROS:
        m = MACROS[name]
        if m.variety in {Macro.Variety.PHOTO, Macro.Variety.IMAGE} and not valid_photo(contents):
            return Errors.BAD_PHOTO

        if m.variety is Macro.Variety.ALIAS:
            if contents not in MACROS:
                return Errors.BAD_ALIAS(contents)

            elif MACROS[contents].variety is Macro.Variety.ALIAS:
                return Errors.ALIAS_NESTING

        if _ctx['is_mod'] or (m.creator == _ctx['user'].id and not m.protected):
            m.contents = contents
            MACROS[name] = m
            return f'Modified contents of {m.variety.name.lower()} macro "{name}".'

        else:
            return Errors.PERMISSION

    else:
        return Errors.NONEXISTENT(name)


def value(name, _ctx):
    """Displays the contents and attributes of a given macro."""
    try:
        m = MACROS[name]

    except KeyError:
        return Errors.NONEXISTENT(name)

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

    attributes = (a for a in m.zipped() if a[0] not in exclude)
    return ', '.join(f'{a[0]}: "{a[1]}"' for a in attributes) + f'\n\nContents:\n{m.contents}'


# Helper function for the next two command functions.
def _ar(a, k, _ctx):

    if k == 'variety':
        a = Macro.Variety[a.upper()]

    replace = {'true': True, 'false': False, 'none': None, str.isnumeric: int}
    return translate_args(a, {'me': _ctx['user'].id} if k == 'creator' else replace)


def find(_ctx=None, _cmd=None, **parameters):
    """Searches macro list, check /macro help for details.
    Can be piped to "remove" or "attribs" commands.
    Piping example: /macro search creator:me | remove"""
    if not _ctx['is_mod']:
        parameters['hidden'] = False

    subset_sig = signature(MacroContainer.subset).parameters
    unexpected = [f'"{k}"' for k in parameters if k not in subset_sig or k == 'criteria']
    if unexpected:
        return Signal(Errors.UNEXPECTED_KEYWORDS(plural(unexpected), ', '.join(unexpected)))

    wrong_type = [f'"{k}": {type(a).__name__} != {subset_sig[k].annotation.__name__}'
                  for k, a in parameters.items() if subset_sig[k].annotation is not type(a)]
    if wrong_type:
        return Signal(f'''Incorrect type for keyword{plural(wrong_type)}: {', '.join(wrong_type)}.''')

    subset = MacroContainer(list(MACROS.subset(**parameters)))
    joined = ', '.join(f'"{m.name}"' for m in subset.macros)
    return Signal(f'Matching macros: {joined}' if subset.macros else
                  'No matching macros found.', data=subset if subset.macros else None)


def attribs(name=None, _ctx=None, _pipe=None, _cmd=None, **attributes):
    """Modifies the attributes of a given macro."""
    global MACROS

    macro_sig = signature(Macro.__init__).parameters

    unexpected = {'contents'}
    if not _ctx['is_mod']:
        unexpected |= {'protected', 'creator'}

    unexpected = [f'"{k}"' for k in attributes if k not in macro_sig or k in unexpected]
    if unexpected:
        return Errors.UNEXPECTED_KEYWORDS(plural(unexpected), ', '.join(unexpected))

    wrong_type = [f'"{k}": {type(a).__name__} != {macro_sig[k].annotation.__name__}'
                  for k, a in attributes.items() if macro_sig[k].annotation is not type(a)]
    if wrong_type:
        return f'''Incorrect type for keyword{plural(wrong_type)}: {', '.join(wrong_type)}.'''

    if isinstance(_pipe, Signal) and _pipe.piped:
        if not _pipe.data:
            return Errors.EMPTY_PIPE

        macros = _pipe.data.macros

        if any(k == 'name' for k in attributes) or len(macros) != 1:
            return 'Cannot batch edit macro names.'

        if not (_ctx['is_mod'] or all(m.creator == _ctx['user'].id and not m.protected for m in macros)):
            return Errors.PERMISSION

        for m in macros:
            for k, a in attributes.items():
                setattr(m, k, a)

            MACROS[m.name] = m

        macros_string = ', '.join(f'"{m.name}"' for m in macros)
        return f"Set attributes of macro{plural(macros)} {macros_string}."

    elif name:
        try:
            m = MACROS[name]

        except KeyError:
            return Errors.NONEXISTENT(name)

        if not (_ctx['is_mod'] or (_ctx['user'].id == m.id and not m.protected)):
            return Errors.PERMISSION

        if 'name' in attributes:
            if attributes['name'] in MACROS:
                return Errors.ALREADY_EXISTS(attributes['name'])

            if (attributes.get('variety') or m.variety) != Macro.Variety.INLINE:
                if not attributes['name'].startswith('!'):
                    return Errors.BAD_NAME(attributes['name'][0])

        for k, a in attributes.items():
            setattr(m, k, a)

        MACROS[m.name] = m
        return f'Set attributes of macro "{m.name}".'

    else:
        return Errors.INPUT_REQUIRED


def remove(name=None, _ctx=None, _pipe=None):
    """Deletes a given macro."""
    global MACROS
    if isinstance(_pipe, Signal) and _pipe.piped:
        if not _pipe.data:
            return Errors.EMPTY_PIPE

        macros = _pipe.data.macros
        if _ctx['is_mod'] or all(m.creator == _ctx['user'].id and not m.protected for m in macros):
            MACROS.macros = [m for m in MACROS.macros if m not in macros]
            macros_string = ', '.join(f'"{m.name}"' for m in macros)
            return f"Removed macro{plural(macros)} {macros_string}."

        else:
            return Errors.PERMISSION

    elif name:
        try:
            m = MACROS[name]

        except KeyError:
            return Errors.NONEXISTENT(name)

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
        if not cmd.callback:
            return f'Command {path[-1]} has no associated function.'

        def display(p):
            if p.default is not Parameter.empty:
                return f'[optional: {p.name}]'

            elif p.kind is Parameter.VAR_POSITIONAL:
                return f'[any args: {p.name}]'

            elif p.kind is Parameter.VAR_KEYWORD:
                return f'[any kwargs: {p.name}]'

            else:
                return f'[required: {p.name}]'

        target_sig = signature(cmd.callback).parameters.items()
        args = ', '.join(display(p) for k, p in target_sig if not k.startswith('_'))
        aliases = ', '.join(k for k in key if isinstance(k, str)) if isinstance(key, tuple) else key
        return f'[/macro] [{aliases}] {args}\n{getdoc(cmd.callback)}'.strip()


def pipes(_pipe: Signal):
    """Facilitates piping of data between commands."""
    return Signal(_pipe.contents, data=_pipe.data, flag=Flags.INTERNAL, piped=True)


# This exists purely to provide a docstring for /macro sig inspection of '&' (chain) nodes.
def chains():
    """Facilitates chaining of commands."""


def dispatcher(message, args, user, logger, config, firebase):
    """Macro editor dispatcher."""
    name = user.name

    _ctx = {'user':     user,
            'logger':   logger,
            'is_mod':   is_mod(name, config),
            'graph':    GRAPH,
            'firebase': firebase}

    max_chained_commands = nested_get(config, ['macro editor', 'max chained commands'], 5)
    if not is_mod(name, config) and sum(1 for a in args if a == '&') > max_chained_commands - 1:
        message.reply_text(text=f'Too many subsequent commands. (max {max_chained_commands})')
        return

    args = translate_args(args, {'...': ...})
    traceback = GRAPH(args, _ctx)

    def flag(t):
        return t.flag if isinstance(t, Signal) else None

    if any(flag(t) is Flags.PHOTO for t in traceback):
        file, caption = next(t for t in traceback if flag(t) is Flags.PHOTO).contents

        message.chat.send_action(ChatAction.UPLOAD_PHOTO)
        message.reply_photo(photo=file, caption=caption, timeout=config.get('photo timeout', 10))
        file.close()

    else:
        trace_len = len(traceback)
        traceback = (str(t) for t in traceback if flag(t) is not Flags.INTERNAL)

        if trace_len > 1:
            traceback = (f'{i}: {t}' for i, t in enumerate(traceback))

        traceback = '\n'.join(traceback)

        if not is_mod(name, config):
            traceback = clip(traceback, config)

        message.chat.send_action(ChatAction.TYPING)
        message.reply_text(text=traceback)


handlers = [DynamicCommandHandler(['macro', 'macros'], dispatcher)]
