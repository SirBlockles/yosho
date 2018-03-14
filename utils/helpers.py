from typing import Any, Tuple


def build_menu(buttons: list, n_cols: int, header_buttons: bool = None, footer_buttons: bool = None) -> list:
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]

    if header_buttons:
        menu.insert(0, header_buttons)

    if footer_buttons:
        menu.append(footer_buttons)

    return menu


def arg_replace(args: [Any, list], replace: dict = None) -> [Any, list]:
    if isinstance(args, list):
        return [arg_replace(a, replace) for a in args]

    return ({} if replace is None else replace).get(args.lower() if isinstance(args, str) else args, args)


def plural(args: [int, list], append: Tuple[str, str] = ('s', '')) -> str:
    return append[args == 1 if isinstance(args, int) else len(args) == 1]


def clip(text: str, config: dict) -> str:
    limit = config.get('output character limit', 256)
    return f'{text[:limit]}... (exceeds {limit} character limit)' if len(text) > limit else text
