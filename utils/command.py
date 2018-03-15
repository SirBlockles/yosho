import inspect
from typing import Dict, Callable, Any

from .helpers import plural


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
        return f'Signal(contents={self.contents}, flag={self.flag}, piped={self.piped}, data={self.data})'


class Command:
    """Dispatch table based class for defining directed graphs of commands with associated functions.
    Uses mutual tail recursion between commands to evaluate lists of arguments.

    Possible optimizations include flattening the recursion (manual tail call optimization),
    and pre-computing the function signature properties on self.func assignment."""
    __slots__ = {'table', 'func'}

    def __init__(self, dispatcher: Dict[Any, 'Command'] = None, func: Callable = None):
        self.table = dispatcher if dispatcher else {}
        self.func = func

    def __repr__(self):
        return f"Command(func={self.func.__name__ if self.func else 'None'}, table={self.table})"

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

    def __call__(self, args: list, ctx=None, _cmd=None, _trace=None) -> list:
        _trace = _trace if _trace else []
        output = None
        if self.func:
            sig = inspect.signature(self.func).parameters

            position = inspect.Parameter.VAR_POSITIONAL
            keyword = inspect.Parameter.KEYWORD_ONLY
            gather = any(v.kind is position for v in sig.values())

            passes = {'_ctx': ctx, '_cmd': _cmd, '_pipe': _trace[-1] if _trace else None}
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
                return [*_trace, f'Command "{_cmd}" expects {"at least" * (maximum > minimum)}'
                                 f' {minimum} argument{plural(minimum)} but {len(args)}'
                                 f' {plural(args, ("were", "was"))} given.']

            # Ellipsis, pipe, chain indicate no optional arguments are to be consumed.
            # Ellipsis is essentially NOP and removed, pipe and chain are left.
            if len(args) >= minimum + 1 and args[:minimum + 1][-1] in {..., '|', '&'}:
                consume, args = args[:minimum], (args[minimum + 1:] if
                                                 args[:minimum + 1][-1] is ... else args[minimum:])
            # Gather indicates all arguments are to be consumed.
            # (gather operator present in func sig, e.g *args)
            elif gather:
                consume, args = args, []
            # Otherwise, consume exactly as many arguments as are present in func sig.
            else:
                consume, args = args[:maximum], args[maximum:]

            try:
                output = self.func(*consume, **passes)

            except Exception as e:
                output = e

            if not args:
                if output:
                    _trace.append(output)

                return _trace

        if output:
            _trace.append(output)

        if not args:
            # If no arguments are given, check for a default command.
            if _cmd is None:
                args = [None]

            else:
                return [*_trace, f'Missing sub-command for command "{_cmd}".']

        next_cmd, *args = args
        next_cmd = next_cmd.lower() if isinstance(next_cmd, str) else next_cmd
        try:
            subsequent = self.val_of(next_cmd)

        except KeyError:
            if _cmd is not None:
                return [*_trace, f'Unknown sub-command of "{_cmd}": "{next_cmd}".']

            else:
                return [*_trace, f'Unknown command: "{next_cmd}".']

        else:
            # Call subsequent command and populate traceback recursively.
            return subsequent(args, ctx, next_cmd, _trace)

    def key_of(self, item):
        try:
            return next(k for k in self.table if item in self._cast(k))

        except StopIteration:
            raise KeyError(f'Command name "{item}" not found in command keys.')

    def val_of(self, item):
        try:
            return next(v for k, v in self.table.items() if item in self._cast(k))

        except StopIteration:
            raise KeyError(f'Command name "{item}" not found in command keys.')

    @staticmethod
    def _cast(k):
        if isinstance(k, tuple):
            return k

        else:
            return k,
