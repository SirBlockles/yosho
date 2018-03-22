from functools import reduce
from inspect import Parameter
from typing import Tuple, Dict, Iterable

from requests import head


def build_menu(buttons: list, n_cols: int, header_buttons: bool = None, footer_buttons: bool = None) -> list:
    """Helper function for building telegram menus."""
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]

    if header_buttons:
        menu.insert(0, header_buttons)

    if footer_buttons:
        menu.append(footer_buttons)

    return menu


def plural(args: [int, list], append: Tuple[str, str] = ('s', '')) -> str:
    """Takes int/list and returns one of two values depending on plurality."""
    return append[args == 1 if isinstance(args, int) else len(args) == 1]


def clip(text: str, config: dict) -> str:
    """Clips text to meet character limit and annotates output if text was clipped."""
    limit = config.get('output character limit', 256)
    return f'{text[:limit]}... (exceeds {limit} character limit)' if len(text) > limit else text


def can_pass_to(a: str, sig: Dict[str, Parameter]) -> bool:
    """Used to determine which arguments to pass during autowiring."""
    return a in sig and sig[a].kind is Parameter.POSITIONAL_OR_KEYWORD


def valid_photo(url: str) -> bool:
    """Validate photo url by checking MIME type."""
    return head(url).headers.get('content-type') in {'image/png', 'image/jpeg'}


def is_mod(name: str, config: dict) -> bool:
    """Check if name is in the bot moderator list."""
    return name and name.lower().lstrip('@') in config.get('bot mods')


def nested_get(root, path: Iterable[str], default):
    """Like dict.get() but for nested dictionaries, object attributes, or a combination of both."""
    try:
        return reduce(lambda d, k: d[k] if isinstance(d, dict) else getattr(d, k), path, root)

    except (KeyError, AttributeError):
        return default


def translate_args(args, translate: dict = None, exceptions=(ValueError, TypeError, AttributeError)):
    """Recursively replaces given arguments using a translation dictionary."""
    translate = translate or {'true': True,
                              'false': False,
                              'none': None,
                              str.isnumeric: int}

    if isinstance(args, (list, tuple, set)):
        return type(args)(translate_args(a, translate) for a in args)

    elif isinstance(args, dict):
        return {k: translate_args(v, translate) for k, v in args.items()}

    else:
        replacement = translate.get(args.lower() if isinstance(args, str) else args)
        if replacement is None:
            replacement = args

            if any(callable(k) for k in translate):
                for k in translate:
                    try:
                        if callable(k) and k(args):
                            replacement = translate[k]
                            break

                    except exceptions:
                        pass

        if callable(replacement):
            try:
                replacement = replacement(args)

            except exceptions:
                pass

        return replacement
