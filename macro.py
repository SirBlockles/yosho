from requests import head
import json


class Macro:
    __varieties = ('TEXT', 'EVAL', 'PHOTO', 'INLINE', 'E926')
    TEXT, EVAL, PHOTO, INLINE, E926 = __varieties

    def __init__(self, name, variety, content, description='', hidden=False, protected=False, nsfw=False):
        if variety not in Macro.__varieties:
            raise AttributeError(variety + ' is not a macro variety.')
        self.name = str(name)
        self.variety = variety
        self._content = None
        self.content = content
        self.description = str(description)
        self.hidden = hidden
        self.protected = protected
        self.nsfw = nsfw

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, value):
        if self.variety == Macro.PHOTO:
            if head(value).headers.get('content-type') not in {'image/png', 'image/jpeg'}:
                raise ValueError('PHOTO macro content is not a photo url.')
        self._content = value

    def __repr__(self):
        return '{} macro "{}": "{}"'.format(self.variety, self.name, self._content)


class MacroSet:
    def subset(self, match=None, search=None, variety=None, hidden=None, protected=None, nsfw=None):
        return MacroSet({m for m in self.macros if all((m.hidden == hidden or hidden is None,
                                               m.protected == protected or protected is None,
                                               m.nsfw == nsfw or nsfw is None,
                                               m.variety == variety or variety is None,
                                               m.name == match or match is None,
                                               search is None or search in m.name))})

    def add(self, value):
        self.macros.add(value)

    def remove(self, key):
        if key in self.macros:
            self.macros.remove(self[key])
        else:
            raise KeyError

    @staticmethod
    def dump(mset, file):
        serializable = {m.name: {k: v for k, v in m.__dict__.items() if not k == 'name'} for m in mset.macros}
        json.dump(serializable, file, indent=4, sort_keys=True)

    @staticmethod
    def load(file):
        data = json.load(file)
        return MacroSet({Macro(k,
                               data[k]['variety'],
                               data[k]['_content'],
                               description=data[k]['description'],
                               hidden=data[k]['hidden'],
                               protected=data[k]['protected'],
                               nsfw=data[k]['nsfw']) for k, v in data.items()})

    def __init__(self, macros):
        self.macros = set(macros)

    def __len__(self):
        return len(self.macros)

    def __iter__(self):
        return iter(self.macros)

    def __contains__(self, name):
        return name in (m.name for m in self.macros)

    def __getitem__(self, item):
        m = next((m for m in self.macros if m.name == item), None)
        if m is None:
            raise KeyError
        return m

    def __setitem__(self, key, value):
        if key in self.macros:
            self.remove(key)
            self.add(value)
        else:
            raise KeyError

    def __add__(self, macros):
        return self.macros.union(macros)

    def __sub__(self, macros):
        return self.macros.difference(macros)

    def __repr__(self):
        return 'MacroSet {{{}}}'.format(', '.join((repr(m) for m in self.macros)))
