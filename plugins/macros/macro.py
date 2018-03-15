from enum import Enum
from typing import List, Callable, Generator, Iterable


class Macro:
    class Variety(Enum):
        TEXT = 0
        EVAL = 1
        PHOTO = 2
        IMAGE = 2
        INLINE = 3
        E621 = 4
        E926 = 5
        MARKOV = 6
        ALIAS = 7

    __slots__ = {'name', 'variety', 'contents', 'creator', 'hidden', 'protected', 'nsfw'}

    def __init__(self,
                 name: str, contents: str, creator: int, variety: Variety,
                 hidden: bool = False, protected: bool = False, nsfw: bool = False):
        self.name = name
        self.variety = variety if isinstance(variety, Macro.Variety) else Macro.Variety(variety)
        self.contents = contents
        self.creator = creator
        self.hidden = hidden
        self.protected = protected
        self.nsfw = nsfw

    def __str__(self):
        return f'Macro(name="{self.name}", variety={self.variety}, contents="{self.contents}")'

    def zipped(self):
        def cast(k):
            v = self.__getattribute__(k)
            return v.value if isinstance(v, Macro.Variety) else v

        return zip(self.__slots__, (cast(k) for k in self.__slots__))


class MacroContainer:
    __slots__ = {'macros'}

    def __init__(self, macros: List[Macro]):
        self.macros = macros

    def __str__(self):
        return f'MacroContainer({", ".join(str(m) for m in self.macros)})'

    def __contains__(self, key: str):
        return any(m.name == key for m in self.macros)

    def __getitem__(self, key: str) -> Macro:
        try:
            return next(m for m in self.macros if m.name == key)

        except StopIteration:
            raise KeyError(f'Macro {key} does not exist.')

    def __setitem__(self, key: str, value: Macro):
        try:
            self.macros[next(i for i, m in enumerate(self.macros) if m.name == key)] = value

        except StopIteration:
            self.macros.append(value)

    def __delitem__(self, key: str):
        try:
            del self.macros[next(i for i, m in enumerate(self.macros) if m.name == key)]

        except StopIteration:
            raise KeyError(f'Macro {key} does not exist.')

    def append(self, macro: Macro):
        self.macros.append(macro)

    def subset(self, **kwargs) -> 'MacroContainer':
        return MacroContainer(list(self.iter_subset(**kwargs)))

    def iter_subset(self,
                    match: str = None,
                    search: str = None,
                    creator: int = None,
                    variety: Macro.Variety = None,
                    hidden: bool = None,
                    protected: bool = None,
                    nsfw: bool = None,
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
