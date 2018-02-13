import csv
import re

import dropbox
from dropbox.files import WriteMode

TOKEN_DICT = [l for l in csv.DictReader(open('tokens.csv', 'r'))][0]
DROPBOX_TOKEN = TOKEN_DICT['dropbox']

db = dropbox.Dropbox(DROPBOX_TOKEN)

MODS = {'wyreyote', 'teamfortress', 'plusreed', 'pixxo', 'radookal', 'pawjob'}

# not PEP8 compliant but idc
is_mod = lambda name: name.lower() in MODS
clean = lambda s: str.strip(re.sub('/[@\w]+\s+', '', s + ' ', 1))  # strips command name and bot name from input
db_pull = lambda name: db.files_download_to_file(name, '/' + name)
db_push = lambda name: db.files_upload(open(name, 'rb').read(), '/' + name, mode=WriteMode('overwrite'))
db_make = lambda name: db.files_upload(open(name, 'rb').read(), '/' + name, mode=WriteMode('add'))
add_s = lambda n: 's' if n != 1 else ''
re_url = lambda s: re.sub(r'(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|'
                          r'(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:\'".,<>?«»“”‘'
                          r'’]))', '', s)
re_name = lambda s: re.sub('@\w+', '', s)





def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu