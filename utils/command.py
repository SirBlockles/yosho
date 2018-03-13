import inspect
from typing import Dict, Callable, Tuple


class Signal:
    """Optional signal class which simplifies piping between Command instances."""
    __slots__ = {'contents', 'flag', 'piped', 'data'}

    def __init__(self, contents, data=None, flag=None, piped=False):
        self.contents = contents
        self.flag = flag
        self.piped = piped
        self.data = data

    def __str__(self):
        return str(self.contents)

    def __repr__(self):
        return 'Signal(contents={}, flag={}, piped={})'.format(self.contents, self.flag, self.piped)


class Command:
    """Dispatch table based class for defining and evaluating directed graphs of commands
     with associated functions that consume input arguments. Returns a traceback on evaluation."""
    __slots__ = {'table', 'func'}

    def __init__(self, dispatcher: Dict[Tuple, 'Command'] = None, func: Callable = None):
        self.table = dispatcher if dispatcher else {}
        self.func = func

    def __repr__(self):
        return 'Command({}, {})' \
            .format(self.func.__name__ if self.func else 'None', self.table)

    def __str__(self):
        return str(self.table)

    def __setitem__(self, key, value: 'Command'):
        self.table[key] = value

    def __getitem__(self, key) -> 'Command':
        return self.table[key]

    def __delitem__(self, key):
        del self.table[key]

    def __add__(self, other: 'Command') -> 'Command':
        return Command({**other.table, **self.table}, self.func or other.func)

    def __contains__(self, item):
        return any(item in self._cast(k) for k in self.table)

    def __call__(self, args: list, ctx=None, _cmd=None, _pipe=None) -> list:
        output = []
        if self.func:
            sig = inspect.signature(self.func).parameters

            position = inspect.Parameter.VAR_POSITIONAL
            keyword = inspect.Parameter.KEYWORD_ONLY
            gather = any(v.kind is position for v in sig.values())

            passes = {'_ctx': ctx, '_cmd': _cmd, '_pipe': _pipe}
            if gather:
                passes = {k: v for k, v in passes.items() if k in sig and sig[k].kind is keyword}

            else:
                passes = {k: v for k, v in passes.items() if k in sig}

            def count(a):
                return a.name not in passes and a.kind is not position

            empty = inspect.Parameter.empty
            minimum = sum(1 for a in sig.values() if a.default is empty and count(a))
            maximum = sum(1 for a in sig.values() if count(a))

            if len(args) < minimum:
                return [SyntaxError('Not enough arguments for command "{}": {} expected, {} given.'
                                    .format(_cmd, minimum, len(args)))]

            # Ellipsis indicates no arguments are to be consumed, used with optional/gather arguments.
            if minimum == 0 and (not args or args[0] is ...):
                consume, args = [], args[1:]
            # Gather indicates all arguments are to be consumed.
            # (gather operator present in func sig, e.g *args)
            elif gather:
                consume, args = args, []
            # Otherwise, consume exactly as many arguments as are present in func sig.
            else:
                consume, args = args[:maximum], args[maximum:]

            try:
                output = [self.func(*consume, **passes)]

            except Exception as e:
                output = [e]

            if not args:
                return output

        if not args:
            # If no arguments are given, check for a default command.
            if _cmd is None:
                args = [None]

            else:
                return [*output, SyntaxError('Missing sub-command for command "{}".'.format(_cmd))]

        try:
            _cmd, *args = args
            _cmd = _cmd.lower() if isinstance(_cmd, str) else _cmd

            # Call subsequent command and populate trace list recursively.
            subsequent = self.val_of(_cmd)
            return [*output, *subsequent(args, ctx, _cmd, *output)]

        except KeyError:
            return [*output, SyntaxError('Unknown command or sub-command "{}".'.format(_cmd))]

    def key_of(self, item):
        try:
            return next(k for k in self.table if item in self._cast(k))

        except StopIteration:
            raise KeyError('Command name {} not found in command keys.'.format(item))

    def val_of(self, item):
        try:
            return next(v for k, v in self.table.items() if item in self._cast(k))

        except StopIteration:
            raise KeyError('Command name {} not found in command keys.'.format(item))

    @staticmethod
    def _cast(k):
        if isinstance(k, tuple):
            return k

        else:
            return k,
