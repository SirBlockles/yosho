def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]

    if header_buttons:
        menu.insert(0, header_buttons)

    if footer_buttons:
        menu.append(footer_buttons)

    return menu


def arg_replace(a, replace: dict = None):
    return ({} if replace is None else replace).get(a.lower(), a)


def plural(args: [int, list], append=('s', '')):
    return append[args == 1 if isinstance(args, int) else len(args) == 1]
