from enum import Enum
from typing import List, Callable, Generator, Iterable


class Macro:
    class Variety(Enum):
        TEXT = 0
        EVAL = 1
        PHOTO = 2
        INLINE = 3
        E621 = 4
        E926 = 4
        MARKOV = 5
        ALIAS = 6

    __slots__ = {'name', 'variety', 'contents', 'creator', 'hidden', 'protected', 'nsfw'}

    def __init__(self,
                 name: str, contents: str, creator: str, variety: Variety,
                 hidden=False, protected=False, nsfw=False):
        self.name = name
        self.variety = variety
        self.contents = contents
        self.creator = creator
        self.hidden = hidden
        self.protected = protected
        self.nsfw = nsfw

    def __str__(self):
        return 'Macro "{}": {} "{}"'.format(self.name, self.variety, self.contents)

    def zipped(self):
        return zip(self.__slots__, map(self.__getattribute__, self.__slots__))


class MacroContainer:
    __slots__ = {'macros'}

    def __init__(self, macros: List[Macro]):
        self.macros = macros

    def __str__(self):
        return 'MacroSet {{{}}}'.format(', '.join(str(m) for m in self.macros))

    def __contains__(self, key: str):
        return any(m.name == key for m in self.macros)

    def __getitem__(self, key: str) -> Macro:
        try:
            return next(m for m in self.macros if m.name == key)

        except StopIteration:
            raise KeyError('Macro {} does not exist.'.format(key))

    def __setitem__(self, key: str, value: Macro):
        try:
            self.macros[next(i for i, m in enumerate(self.macros) if m.name == key)] = value

        except StopIteration:
            self.macros.append(value)

    def __delitem__(self, key: str):
        try:
            del self.macros[next(i for i, m in enumerate(self.macros) if m.name == key)]

        except StopIteration:
            raise KeyError('Macro {} does not exist.'.format(key))

    def subset(self, **kwargs) -> 'MacroContainer':
        return MacroContainer(list(self.iter_subset(**kwargs)))

    def iter_subset(self,
                    match=None,
                    search=None,
                    creator=None,
                    variety=None,
                    hidden=None,
                    protected=None,
                    nsfw=None,
                    criteria: Callable[[Iterable], bool] = all) -> Generator:

        comparisons = {hidden:    (lambda m: m.hidden == hidden),
                       protected: (lambda m: m.protected == protected),
                       creator:   (lambda m: m.creator == creator),
                       nsfw:      (lambda m: m.nsfw == nsfw),
                       variety:   (lambda m: m.variety == variety),
                       match:     (lambda m: m.name == match),
                       search:    (lambda m: search in m.name)}

        comparisons = [v for k, v in comparisons.items() if k is not None]
        return (m for m in self.macros if criteria(c(m) for c in comparisons))

    def to_dict(self) -> dict:
        return {m.name: {k: v for k, v in m.zipped() if not k == 'name'} for m in self.macros}

    @classmethod
    def from_dict(cls, macros: dict) -> 'MacroContainer':
        return cls([Macro(k, **{k: v for k, v in v.items()}) for k, v in macros.items()])
