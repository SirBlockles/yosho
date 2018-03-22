import inspect
from typing import Dict, Callable, Any


class Command:
    """Dispatch table based class for defining directed graphs of commands with associated functions.
    Uses mutual tail recursion between commands to evaluate lists of arguments.

    Possible optimizations include flattening the recursion (manual tail call optimization),
    and pre-computing the function signature properties on self.func assignment."""
    __slots__ = {'table', 'callback', 'unions', 'stops', 'kwargs'}

    def __init__(self, dispatcher: Dict[Any, 'Command'] = None,
                 callback: Callable = None,
                 kwargs: str = None,
                 unions: set = {'&', '|'},
                 stops: set = {...}):
        self.table = dispatcher or {}
        self.callback = callback
        self.kwargs = kwargs
        self.unions = unions
        self.stops = stops

    def __repr__(self):
        return f"Command(func={self.callback.__name__ if self.callback else 'None'}, table={self.table})"

    def __str__(self):
        return str(self.table)

    def __setitem__(self, key, value: 'Command'):
        self.table[key] = value

    def __getitem__(self, key) -> 'Command':
        return self.table[key]

    def __delitem__(self, key):
        del self.table[key]

    def __add__(self, other: 'Command') -> 'Command':
        return Command({**other.table, **self.table}, self.callback or other.callback)

    def __contains__(self, item):
        return any(item in self._cast(k) for k in self.table)

    def __call__(self, args: list, ctx=None, _cmd=None, _trace=None) -> list:
        _trace = _trace or []
        output = None
        if self.callback:
            sig = inspect.signature(self.callback).parameters

            passes = {'_ctx': ctx, '_cmd': _cmd, '_pipe': _trace[-1] if _trace else None}

            keyword = inspect.Parameter.KEYWORD_ONLY
            pos_or_key = inspect.Parameter.POSITIONAL_OR_KEYWORD
            passes = {k: v for k, v in passes.items() if k in sig and sig[k].kind in {keyword, pos_or_key}}

            def consume():
                nonlocal args
                while args and args[0] not in self.unions | self.stops:
                    yield args.pop(0)

                if args and args[0] in self.stops:
                    del args[0]

                raise StopIteration

            func_args = []
            func_kwargs = {}
            if _cmd not in self.unions | self.stops:
                for a in consume():
                    if self.kwargs and isinstance(a, str) and self.kwargs in a:
                        kwarg = a.split(self.kwargs)

                        if len(kwarg) > 2:
                            kwarg[1] = self.kwargs.join(kwarg[1:])

                        if any(not k for k in kwarg):
                            _trace.append('Malformed keyword arguments.')
                            return _trace

                        if kwarg[0].startswith('_'):
                            _trace.append('Cannot pass kwargs that start with an underscore.')

                        func_kwargs[kwarg[0]] = kwarg[1]

                    else:
                        if func_kwargs:
                            _trace.append('Positional arguments must proceed keyword arguments.')
                            return _trace

                        func_args.append(a)

            try:
                output = self.callback(*func_args, **func_kwargs, **passes)

            except (IndexError, TypeError):
                _trace.append(f'Incorrect number or type of args for command "{_cmd}".')
                return _trace

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
                _trace.append(f'Missing sub-command for command "{_cmd}".')
                return _trace

        next_cmd, *args = args
        next_cmd = next_cmd.lower() if isinstance(next_cmd, str) else next_cmd
        try:
            subsequent = self.val_of(next_cmd)

        except KeyError:
            if _cmd is not None:
                _trace.append(f'Unknown sub-command of "{_cmd}": "{next_cmd}".')
                return _trace

            else:
                _trace.append(f'Unknown command: "{next_cmd}".')
                return _trace

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
