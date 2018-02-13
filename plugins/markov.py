"""yosho plugin:markov generator"""
import pickle
import string

import emoji
from autocorrect import spell
from autocorrect.word import KNOWN_WORDS
from nltk.tokenize import PunktSentenceTokenizer
from numpy.random import choice
from scipy.sparse import lil_matrix, hstack, vstack, find
from telegram import ChatAction as Ca
from telegram.ext import CommandHandler, MessageHandler
from telegram.ext.filters import Filters

from helpers import db_push, db_pull, clean, add_s, re_url, re_name

ORDER = 0

MARKOV_PATH = 'MARKOV.pkl'

MAX_INPUT_SIZE = 256
MAX_OUTPUT_STATES = 50
ACCUMULATOR_TIMEOUT = 5

db_pull(MARKOV_PATH)
STATES, TRANSITIONS = pickle.load(open(MARKOV_PATH, 'rb'))

handlers = []

# word exceptions
WORDS = KNOWN_WORDS | {"floofy", "hentai", "binch", "wtf", "afaik", "iirc", "lol", "scat", "brek", "yosho", "yoshi",
                       "str8", "b&", "cyoot", "lmao", "vore", "we'd", "we're", "we've"}


def process_token(token):
    # kludgy "I'm" spelling error exceptions
    if token in {"im", "iM", "Im", "IM"}:
        return "I'm"

    # punctuation and capitalization check
    if token in set(string.punctuation) | {'I', "I'm", "I've", "I'd", "I'd've", "I'll",
                                       "i", "i'm", "i've", "i'd", "i'd've", "i'll"}:
        return token.capitalize()

    # known word check
    if token.lower() in WORDS:
        return token.lower()

    # acronym and contraction check
    if all(c in set(string.ascii_uppercase) for c in token):
        return token
    elif any(c in set(string.punctuation) for c in token):
        return token.lower()

    return spell(token).lower()


def reset(bot, update):
    """reset markov states"""
    global STATES, TRANSITIONS
    # initiate STATES and TRANSITIONS with one member (absorbing state)
    STATES = [' ']
    TRANSITIONS = lil_matrix((1, 1), dtype=int)
    pickle.dump([STATES, TRANSITIONS], open(MARKOV_PATH, 'wb+'))
    db_push(MARKOV_PATH)
    update.message.reply_text(text='Reset markov states.')


handlers.append([CommandHandler('reset', reset), {'action': Ca.TYPING, 'mods': True}])


def markov(bot, update):
    """generates sentences using a markov chain"""

    # joins together punctuation at ends of words and auto-completes parenthesis: ['"', 'test', '.'] -> '"test."'
    # tries its best
    snap = (tuple(r'''[{(*'"'''), tuple(r''']})*'"'''))
    right = set('!.?~:;,%')
    left = set()

    def joiner(tokens):
        snaps = [[], []]
        output = tokens.copy()
        for i, t in enumerate(tokens):
            if t in set(snap[0]) or t in left:
                if i < len(tokens) - 1:
                    if t not in left:
                        snaps[0] += [t]
                    ind = i + 1
                    while not output[ind]:
                        ind += 1
                    output[ind] = t + tokens[i + 1]
                    output[i] = ''

            if t in set(snap[1]) or t in right:
                if i > 0:
                    if t not in right:
                        snaps[1] += [t]
                    ind = i - 1
                    while not output[ind]:
                        ind -= 1
                    output[ind] += t
                    output[i] = ''

        output = (t for t in output if t)

        for c in snaps[0]:
            completion = snap[1][snap[0].index(c)]
            if completion in snaps[1]:
                snaps[0].remove(c)
                snaps[1].remove(completion)

        snaps[0] = [snap[1][snap[0].index(s)] for s in snaps[0]]
        snaps[1] = [snap[0][snap[1].index(s)] for s in snaps[1]]

        return ''.join(snaps[1]) + ' '.join(output) + ''.join(snaps[0])

    def capitals(s):
        if len(s) > 1:
            return s[0].upper() + s[1:]
        else:
            return s.upper()

    if len(STATES) == 1:
        update.message.reply_text(text='No markov states! Type something to contribute to /markov!')
        return

    output = []

    text = clean(update.message.text)
    if text:
        state = process_token(text.split()[-1])
        if state not in set(STATES):
            update.message.reply_text(text='"{}" is not in markov states.'.format(state))
            return
        else:
            state_index = STATES.index(state)
            output.append(' '.join(text.split()[:-1] + [STATES[state]]))
    else:
        state_index = 0

    # generate text until hitting the next absorbing state or exceeding MAX_OUTPUT_STATES
    while (state_index != 0 or len(output) == 0) and len(output) < MAX_OUTPUT_STATES:
        branches, probabilities = find(TRANSITIONS.getrow(state_index))[1:]

        # normalization of probabilities
        transition_sum = sum(probabilities)
        probabilities = tuple(i/transition_sum for i in probabilities)

        # choose branch with weighted random choice
        state_index = choice(branches, p=probabilities)

        output.append(STATES[state_index])

    if len(output) == MAX_OUTPUT_STATES:
        output += ['...']

    # capitalize sentences
    tokenizer = PunktSentenceTokenizer()
    reply = ' '.join((capitals(s) for s in tokenizer.tokenize(joiner(output).strip())))

    if not reply[-1] in string.punctuation:
        reply += '.'

    update.message.reply_text(text=reply, disable_web_page_preview=True)


handlers.append([CommandHandler('markov', markov), {'action': Ca.TYPING, 'name': True}])


def relations(bot, update):
    """
/after <state>: displays states proceeding a state
/before <state>: displays states preceding a state
/ends: displays end states
/starts: displays start states
/mean: displays mean number of branches per state
/states: displays total number of states
"""
    def get_state():
        state = process_token(clean(text))
        if state not in set(STATES):
            update.message.reply_text(text='"{}" is not in markov states.'.format(state))
            return
        else:
            return STATES.index(state)

    text = update.message.text

    if text.startswith('/ends'):
        data = TRANSITIONS.getcol(0).T

    elif text.startswith('/starts'):
        data = TRANSITIONS.getrow(0)

    elif text.startswith('/before'):
        data = TRANSITIONS.getcol(get_state()).T

    elif text.startswith('/after'):
        data = TRANSITIONS.getrow(get_state())

    elif text.startswith('/mean'):
        mean = len(find(TRANSITIONS)[0])/TRANSITIONS.shape[0]
        update.message.reply_text(text='Mean number of branches per state: {}'.format(mean))
        return

    else:
        update.message.reply_text(text='Number of markov generator states: {}'.format(len(STATES)))
        return

    links = (s for s in find(data)[1])
    sort = sorted(enumerate(links), key=lambda s: data[0, s[0]], reverse=True)
    percent = round((len(sort) / TRANSITIONS.shape[0]) * 100)
    output = ' ,'.join('"{}"'.format(STATES[s[1]]) for s in sort[:MAX_OUTPUT_STATES])

    update.message.reply_text(text='{}% of states: {{{}}}\n(Displays {} most probable states.)'
                              .format(percent, output, MAX_OUTPUT_STATES), disable_web_page_preview=True)


handlers.append([CommandHandler(['links', 'ends', 'after', 'before', 'mean', 'states'], relations),
                 {'action': Ca.TYPING}])


def convergence(bot, update):
    """
/converge <state> <steps>: number of states a starting state converges to
/diverge <state> <steps>: displays if a starting state diverges at least once
"""
    expr = clean(update.message.text).split()

    if not expr:
        update.message.reply_text(text='Syntax is /converge <state> <optional steps int>')
        return

    state = process_token(expr[0])
    if state not in set(STATES):
        update.message.reply_text(text='"{}" is not in markov states.'.format(state))
        return
    else:
        state_index = STATES.index(state)

    if len(expr) > 1 and expr[1].isnumeric() and int(expr[1]) < 10:
        steps = int(expr[1])
    else:
        steps = 10

    # create and populate boolean translation matrix
    shape = TRANSITIONS.shape
    transitions = lil_matrix(shape, dtype=bool)

    x, y = find(TRANSITIONS)[:2]
    for i, v in enumerate(x):
        transitions[v, y[i]] = True
    transitions = transitions.asformat('csr')

    print('test')

    if update.message.text.startswith('/converge'):
        transitions **= 2
        converge = len(find(transitions.getrow(state_index))[1])

        update.message.reply_text(text='State "{}" converges to {} possible final state{} after {} step{}.'
                                  .format(state, converge, add_s(converge), steps, add_s(steps)))
    else:
        copy = transitions.copy()
        for s in range(steps + 1):
            branches = find(transitions.getrow(state_index))[1]
            if len(branches) > 1:
                update.message.reply_text(text='State "{}" diverges at {} step{} where it has {} possible branches.'
                                          .format(state, s, add_s(s), len(branches)))
                return

            if s != steps:
                transitions *= copy

        update.message.reply_text(text="""State "{}" doesn't diverge within {} step{}."""
                                  .format(state, steps, add_s(steps)))


handlers.append([CommandHandler(['converge', 'diverge'], convergence), {'action': Ca.TYPING}])


def accumulator(bot, update):
    """markov state accumulator"""
    global STATES, TRANSITIONS

    # splits off punctuation at ends of tokens: 'test.' -> ['test', '.']
    def splitter(text):
        tokens = []
        for t in text.split():
            no_split = all(c in string.punctuation for c in t) or any(c in emoji.EMOJI_UNICODE for c in t)
            if t[-1] in string.punctuation and len(t) > 1 and not no_split:
                tokens.append(process_token(t.rstrip(t[-1])))
                tokens.append(t[-1])

            if t[0] in string.punctuation and len(t) > 1 and not no_split:
                tokens.append(t[0])
                tokens.append(process_token(t.lstrip(t[0])))

            else:
                tokens.append(process_token(t))

        return tokens

    if len(update.message.text) > MAX_INPUT_SIZE:
        return

    sentence_tokenizer = PunktSentenceTokenizer()
    for s in sentence_tokenizer.tokenize(re_name(re_url(update.message.text))):
        tokens = splitter(s)

        # add new states
        STATES += list(set(tokens) - set(STATES))

        # scale transition matrix accordingly
        if len(STATES) > TRANSITIONS.shape[0]:
            difference = len(STATES) - TRANSITIONS.shape[0]

            v_pad = lil_matrix((difference, TRANSITIONS.shape[0]), dtype=int)
            h_pad = lil_matrix((len(STATES), difference), dtype=int)

            TRANSITIONS = vstack([TRANSITIONS, v_pad])
            TRANSITIONS = hstack([TRANSITIONS, h_pad])

            TRANSITIONS = lil_matrix(TRANSITIONS)

        # increment transition matrix values
        for i, t in enumerate(tokens):
            state = STATES.index(t)

            next_state = STATES.index(tokens[i+1]) if i < len(tokens) - 1 else 0  # absorbing state at end of sentence
            if i == 0:
                TRANSITIONS[0, state] += 1  # absorbing state at start of sentence

            TRANSITIONS[state, next_state] += 1  # transition state


handlers.append([MessageHandler(callback=accumulator, filters=(Filters.text & (~Filters.command))), None])


def flush(bot, job):
    pickle.dump([STATES, TRANSITIONS], open(MARKOV_PATH, 'wb+'))
    db_push(MARKOV_PATH)


def init(bot_globals):
    bot_globals['jobs'].run_repeating(flush, interval=bot_globals['FLUSH_INTERVAL'])
