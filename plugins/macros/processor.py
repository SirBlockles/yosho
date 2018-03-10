"""yosho plugin:macro processor"""
from math import inf
from os.path import dirname

from .macro import *

_ABSOLUTE = dirname(__file__) + '/'
ORDER = inf

with open(_ABSOLUTE + 'macros.json', 'r') as macros:
    MACROS = MacroSet.load(macros)


def macro(*args: List[str]) -> str:
    global MACROS

    def new():
        pass

    def remove():
        pass

    def hide():
        pass

    def protect():
        pass

    def clean():
        pass

    def modify():
        pass

    def rename():
        pass

    def nsfw():
        pass

    def contents():
        pass

    def show():
        pass

    modes = {'eval': new,
             'text': new,
             'inline': new,
             'photo': new,
             'e621': new,
             'alias': new,
             'markov': new,
             'remove': remove,
             'hide': hide,
             'protect': protect,
             'clean': clean,
             'modify': modify,
             'rename': rename,
             'nsfw': nsfw,
             'contents': contents,
             'show': show}

    return modes[args[0]]()
