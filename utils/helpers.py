def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]

    if header_buttons:
        menu.insert(0, header_buttons)

    if footer_buttons:
        menu.append(footer_buttons)

    return menu


def arg_replace(a, replace: dict = None):
    return {'true': True,
            'false': False,
            'none': None,
            '...': ...,
            **(replace if replace else {})}.get(a.lower(), a)


def plural(args: [int, list], append=('s', '')):
    condition = args == 1 if isinstance(args, int) else len(args) == 1
    return append[condition]
