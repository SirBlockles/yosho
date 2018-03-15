from functools import wraps
from typing import Any, Tuple


def build_menu(buttons: list, n_cols: int, header_buttons: bool = None, footer_buttons: bool = None) -> list:
    """Helper function for building telegram menus."""
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]

    if header_buttons:
        menu.insert(0, header_buttons)

    if footer_buttons:
        menu.append(footer_buttons)

    return menu


def arg_replace(args: [Any, list, dict], replace: dict = None) -> [Any, list]:
    """Replaces given arguments based on a translation dictionary."""
    if isinstance(args, list):
        return [arg_replace(a, replace) for a in args]

    elif isinstance(args, dict):
        return {k: arg_replace(v, replace) for k, v in args.items()}

    return ({} if replace is None else replace).get(args.lower() if isinstance(args, str) else args, args)


# Currently unused but may find use in the future.
def replaces_args(f):
    """Decorator that replaces certain argument values automatically."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        replace = {'true': True, 'false': False, 'none': None}
        return f(*arg_replace(args, replace), **arg_replace(kwargs, replace))

    return wrapper


def plural(args: [int, list], append: Tuple[str, str] = ('s', '')) -> str:
    """Takes int/list and returns one of two values depending on plurality."""
    return append[args == 1 if isinstance(args, int) else len(args) == 1]


def clip(text: str, config: dict) -> str:
    """Clips text to meet character limit and annotates output if text was clipped."""
    limit = config.get('output character limit', 256)
    return f'{text[:limit]}... (exceeds {limit} character limit)' if len(text) > limit else text
