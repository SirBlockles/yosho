import json

from typing import Iterable, List


class Macro:
    __slots__ = {'name', 'variety', 'content', 'creator', 'hidden', 'protected', 'nsfw'}

    def __init__(self, name: str, variety: str, content: str, creator: str, hidden=False, protected=False, nsfw=False):
        self.name = name
        self.variety = variety
        self.content = content
        self.creator = creator
        self.hidden = hidden
        self.protected = protected
        self.nsfw = nsfw

    def __repr__(self):
        return 'Macro "{}": {} "{}"'.format(self.name, self.variety, self.content)


class MacroSet:
    __slots__ = {'_macros'}

    def __init__(self, macros: Iterable[Macro]):
        self._macros = set(macros)

    def __len__(self):
        return len(self._macros)

    def __iter__(self):
        return iter(self._macros)

    def __contains__(self, name):
        return name in (m.name for m in self._macros)

    def __getitem__(self, item):
        m = next((m for m in self._macros if m.name == item), None)
        if m is None:
            raise KeyError

        return m

    def __setitem__(self, key, value):
        if key in self._macros:
            self.remove(key)
            self.add(value)

        else:
            raise KeyError

    def __add__(self, macros):
        return MacroSet(self._macros.union(macros))

    def __sub__(self, macros):
        return MacroSet(self._macros.difference(macros))

    def __repr__(self):
        return 'MacroSet {{{}}}'.format(', '.join(repr(m) for m in self._macros))

    def subset(self, match=None,
               search=None,
               creator=None,
               variety=None,
               hidden=False,
               protected=None,
               nsfw=None) -> 'MacroSet':
        return MacroSet({m for m in self._macros if all((hidden is None or m.hidden == hidden,
                                                         protected is None or m.protected == protected,
                                                         creator is None or m.creator == creator,
                                                         nsfw is None or m.nsfw == nsfw,
                                                         variety is None or variety in {m.variety.lower(), m.variety},
                                                         match is None or m.name == match,
                                                         search is None or search in m.name))})

    def add(self, value: Macro):
        self._macros.add(value)

    def remove(self, key):
        if isinstance(key, str):
            self._macros.remove(next(m for m in self._macros if m.name == key))

        elif isinstance(key, Macro):
            self._macros.remove(key)

        else:
            raise KeyError('Key must be of type str or Macro, not {}.'.format(type(key)))

    def sort(self) -> List[Macro]:
        return sorted(self._macros, key=lambda m: m.name)

    def dump(self, file):
        serializable = {m.name: {k: v for k, v in zip(m.__slots__, map(m.__getattribute__, m.__slots__))
                                 if not k == 'name'} for m in self._macros}
        json.dump(serializable, file, indent=4)

    @staticmethod
    def load(file) -> 'MacroSet':
        data = json.load(file)
        return MacroSet({Macro(k, **{k: v for k, v in v.items()}) for k, v in data.items()})
