"""yosho plugin:markov generator"""
import pickle
import string

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

RIGHT = set("!.?~:;,%")

handlers = []

# word exceptions
WORDS = KNOWN_WORDS | {"floofy", "hentai", "binch", "wtf", "afaik", "iirc", "lol", "scat", "brek", "yosho", "yoshi",
                       "str8", "b&", "cyoot", "lmao", "vore", "we'd", "we're", "we've"}


def process_token(t):
    # punctuation and capitalization check
    if t in set(string.punctuation) | {'I', "I'm", "I've", "I'd", "I'd've", "I'll",
                                       "i", "i'm", "i've", "i'd", "i'd've", "i'll"}:
        return t.capitalize()

    # known word check
    if t.lower() in WORDS:
        return t.lower()

    # acronym and contraction check
    if all((c in set(string.ascii_uppercase) for c in t)):
        return t
    elif any((c in set(string.punctuation) for c in t)):
        return t.lower()

    return spell(t).lower()


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
    # joins together punctuation at ends of words: ['test', '.'] -> 'test.'
    def joiner(states):
        output = []
        for i, s in enumerate(states):
            if s not in RIGHT:
                if i < len(states) - 1 and all((c in RIGHT for c in states[i + 1])):
                    s += states[i+1]

                output.append(s)

        return ' '.join(output)

    def capitals(s):
        if len(s) > 1:
            return s[0].upper() + s[1:]
        else:
            return s.upper()

    if len(STATES) <= 1:
        update.message.reply_text(text='No markov states! Type something to contribute to /markov!')
        return

    output = []

    text = clean(update.message.text)
    if text:
        state = process_token(text)
        if state not in set(STATES):
            update.message.reply_text(text='"{}" is not in markov states.'.format(state))
            return
        else:
            state_index = STATES.index(state)
            output.append(STATES[state_index])
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
/links <state>: displays links between states
/ends: displays end states
/starts: displays start states
/mean: displays mean number of branches per state
"""
    text = update.message.text

    if text.startswith('/ends'):
        ends = find(TRANSITIONS.getcol(0))[0]
        output = ', '.join('"{}"'.format(STATES[s]) for i, s in enumerate(ends) if i < MAX_OUTPUT_STATES)
        percent = round((len(ends) / TRANSITIONS.shape[0]) * 100)

    elif text.startswith('/starts'):
        starts = find(TRANSITIONS.getrow(0))[1]
        output = ', '.join('"{}"'.format(STATES[s]) for i, s in enumerate(starts) if i < MAX_OUTPUT_STATES)
        percent = round((len(starts) / TRANSITIONS.shape[0]) * 100)

    elif text.startswith('/links'):
        state = process_token(clean(text))
        if state not in set(STATES):
            update.message.reply_text(text='"{}" is not in markov states.'.format(state))
            return
        else:
            state_index = STATES.index(state)

        links = find(TRANSITIONS.getrow(state_index))[1]
        output = ', '.join('"{}"'.format(STATES[s]) for i, s in enumerate(links) if i < MAX_OUTPUT_STATES)
        percent = round((len(links) / TRANSITIONS.shape[0]) * 100)

    else:
        mean = 0
        for r in range(TRANSITIONS.shape[0]):
            mean += len(find(TRANSITIONS.getrow(r))[0])
        mean /= TRANSITIONS.shape[0]

        update.message.reply_text(text='Mean number of branches per state: {}'.format(mean))
        return

    update.message.reply_text(text='{}% of states: {{{}}}\n(Displays up to first {} applicable states.)'
                              .format(percent, output, MAX_OUTPUT_STATES), disable_web_page_preview=True)


handlers.append([CommandHandler(['links', 'ends', 'starts', 'mean'], relations), {'action': Ca.TYPING}])


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

    if len(expr) > 1 and expr[1].isnumeric() and int(expr[1]) < MAX_OUTPUT_STATES:
        steps = int(expr[1])
    else:
        steps = MAX_OUTPUT_STATES

    # create and populate boolean translation matrix
    shape = TRANSITIONS.shape
    transitions = lil_matrix(shape, dtype=bool)

    for r in range(shape[0]):
        indices, values = find(TRANSITIONS.getrow(r))[1:]
        for i, v in enumerate(values):
            if v == max(values) and r > 0:
                transitions[r, indices[i]] = True

    if update.message.text.startswith('/converge'):
        transitions **= steps
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


def markov_states(bot, update):
    """current number of distinct markov states"""
    update.message.reply_text(text='Number of markov generator states: {}'.format(len(STATES)))


handlers.append([CommandHandler('states', markov_states), {'action': Ca.TYPING}])


def accumulator(bot, update):
    """markov state accumulator"""
    global STATES, TRANSITIONS

    # splits off punctuation at ends of tokens: 'test.' -> ['test', '.']
    def splitter(text):
        tokens = []
        for t in text.split():
            if t[-1] in RIGHT:
                tokens.append(process_token(t.rstrip(t[-1])))
                tokens.append(t[-1])

            else:
                tokens.append(process_token(t))

        return tokens

    if len(update.message.text) > MAX_INPUT_SIZE:
        return

    tokenizer = PunktSentenceTokenizer()
    for s in tokenizer.tokenize(re_name(re_url(update.message.text))):
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
            TRANSITIONS[state, next_state] += 1


handlers.append([MessageHandler(callback=accumulator, filters=(Filters.text & (~Filters.command))), None])


def flush(bot, job):
    pickle.dump([STATES, TRANSITIONS], open(MARKOV_PATH, 'wb+'))
    db_push(MARKOV_PATH)


def init(bot_globals):
    bot_globals['jobs'].run_repeating(flush, interval=bot_globals['FLUSH_INTERVAL'])
