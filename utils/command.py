import inspect
from typing import Dict, List, Callable, Any, Tuple


class Command:
    """Dispatch table based class for defining and evaluating directed graphs of commands
     with associated functions that consume input arguments. Returns a traceback on evaluation."""
    _key_type = Tuple
    _dispatcher_type = Dict[_key_type, 'Command']
    __slots__ = {'table', 'func'}

    def __init__(self, dispatcher: _dispatcher_type = None, func: Callable[[Any], str] = None):
        self.table = dispatcher if dispatcher else {}
        self.func = func

    def __repr__(self):
        return str(self.table)

    def __setitem__(self, key: _key_type, value: 'Command'):
        self.table[key] = value

    def __getitem__(self, key: _key_type) -> 'Command':
        return self.table[key]

    def __delitem__(self, key: _key_type):
        del self.table[key]

    @staticmethod
    def _cast(k):
        if isinstance(k, tuple):
            return k

        else:
            return k,

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

    def __call__(self, args: List[str], ctx=None, _cmd=None) -> List[str]:
        output = []
        if self.func:
            sig = inspect.signature(self.func).parameters

            passes = {'ctx': ctx, 'cmd': _cmd}

            position = inspect.Parameter.VAR_POSITIONAL
            gather = any(v.kind is position for v in sig.values())

            if gather:
                keyword = inspect.Parameter.KEYWORD_ONLY
                passes = {k: v for k, v in passes.items() if k in sig and sig[k].kind is keyword}

            else:
                passes = {k: v for k, v in passes.items() if k in sig}

            n = len(sig) - len(passes)
            if len(args) < n:
                return ['Not enough arguments for command "{}": {}{} expected, {} given.'
                        .format(_cmd, 'at least ' * gather, n, len(args))]

            if gather:
                consume, args = args, []

            else:
                consume, args = args[:n], args[n:]

            output = [self.func(*consume, **passes)]
            if not args:
                return output

        if not args:
            # If no arguments are given, check for a default command.
            if _cmd is None:
                args = [None]

            else:
                return ['Missing sub-command for command "{}".'.format(_cmd)]

        try:
            _cmd, *args = args
            _cmd = _cmd.lower() if _cmd else _cmd

            subsequent = self.val_of(_cmd)
            return [*output, *subsequent(args, ctx, _cmd)]

        except KeyError:
            return ['Unknown command or sub-command "{}".'.format(_cmd)]
