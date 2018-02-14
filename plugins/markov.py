"""yosho plugin:markov generator"""
import pickle
import string
from math import sqrt

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
MIN_OUTPUT_STATES = 4
MAX_OUTPUT_STATES = 50
ACCUMULATOR_TIMEOUT = 5

db_pull(MARKOV_PATH)
STATES, TRANSITIONS = pickle.load(open(MARKOV_PATH, 'rb'))

handlers = []

# word exceptions
WORDS = KNOWN_WORDS | {"floofy", "hentai", "binch", "wtf", "afaik", "iirc", "lol", "scat", "brek", "yosho", "yoshi",
                       "str8", "b&", "cyoot", "lmao", "vore", "we'd", "we're", "we've", "tbh", "tbf", "uwu", "af",
                       "nsfw", "ecks", "wyre", "awoo"}

REPLACE = {"im": "I'm", "ive": "I've", "id": "I'd", "idve": "I'd've", "hes": "he's", "arent": "aren't", "shes": "she's",
           "youre": "you're", "youll": "you'll", "thats": "that's", "xd": "xD", "dont": "don't", "youd": "you'd",
           "whats": "what's", "owo": "OwO", "uwu": "UwU"}


def process_token(token):
    if any(c in emoji.EMOJI_UNICODE for c in token):
        return token.lower()

    # Contraction spelling error exceptions
    if token.lower() in REPLACE:
        return REPLACE[token.lower()]

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


def markov(bot, update):
    """generates sentences using a markov chain"""

    # joins together punctuation at ends of words and auto-completes parenthesis: ['"', 'test', '.'] -> '"test."'
    # tries its best
    snap = (('[', '{', '(', '*', "'", '"'), (']', '}', ')', '*', "'", '"'))
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

        output = (t for t in output if t != '')

        for c in snaps[0]:
            completion = snap[1][snap[0].index(c)]
            if completion in snaps[1]:
                snaps[0].remove(c)
                snaps[1].remove(completion)

        snaps[0] = [snap[1][snap[0].index(s)] for s in snaps[0]]
        snaps[1] = [snap[0][snap[1].index(s)] for s in snaps[1]]

        return ''.join(snaps[1]) + ' '.join(output).strip() + ''.join(snaps[0])

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
            output.append(' '.join(text.split()[:-1] + [STATES[state_index]]))
    else:
        state_index = 0

    # generate text until hitting the next absorbing state or exceeding MAX_OUTPUT_STATES
    while (state_index != 0 or len(output) == 0) and len(output) < MAX_OUTPUT_STATES:
        branches, probabilities = find(TRANSITIONS.getrow(state_index))[1:]

        # don't post short responses if longer responses are possible
        if len(branches) > 1 and branches[0] == 0 and len(output) < MIN_OUTPUT_STATES:
            branches = branches[1:]
            probabilities = probabilities[1:]

        # normalization of probabilities
        transition_sum = sum(probabilities)
        probabilities = tuple(i/transition_sum for i in probabilities)

        # choose branch with weighted random choice
        state_index = choice(branches, p=probabilities)

        if state_index != 0:
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
/deviation: displays standard deviation of branches per state
/states: displays total number of states
/singleton: displays probability of a singleton being an end state
"""
    text = update.message.text

    if text.startswith('/ends'):
        data = TRANSITIONS.getcol(0).T

    elif text.startswith('/starts'):
        data = TRANSITIONS.getrow(0)

    elif text.startswith('/before'):
        state = process_token(clean(text))
        if state not in set(STATES):
            update.message.reply_text(text='"{}" is not in markov states.'.format(state))
            return
        else:
            state_index = STATES.index(state)

        data = TRANSITIONS.getcol(state_index).T

    elif text.startswith('/after'):
        state = process_token(clean(text))
        if state not in set(STATES):
            update.message.reply_text(text='"{}" is not in markov states.'.format(state))
            return
        else:
            state_index = STATES.index(state)

        data = TRANSITIONS.getrow(state_index)

    elif text.startswith('/mean'):
        mean = len(find(TRANSITIONS)[0])/TRANSITIONS.shape[0]
        update.message.reply_text(text='Mean number of branches per state: {}'.format(mean))
        return

    elif text.startswith('/deviation'):
        mean = len(find(TRANSITIONS)[0]) / TRANSITIONS.shape[0]
        deviation = 0

        for r in range(TRANSITIONS.shape[0]):
            deviation += (len(find(TRANSITIONS.getrow(r))[0]) - mean)**2

        deviation /= TRANSITIONS.shape[0]
        deviation = sqrt(deviation)

        update.message.reply_text(text='Standard deviation of branches per state: {}'.format(deviation))
        return

    elif text.startswith('/singleton'):
        singletons = 0
        stop_singletons = 0

        for r in range(TRANSITIONS.shape[0]):
            row = find(TRANSITIONS.getrow(r))[1]
            print(row)
            if len(row) == 1:
                singletons += 1
                if row[0] == 0:
                    stop_singletons += 1

        update.message.reply_text(text='Probability of a state being a singleton: {}\n'
                                       'Probability of a singleton being an end state singleton: {}\n'
                                       'Probability of a state being an end state singleton.'
                                  .format(singletons/TRANSITIONS.shape[0],
                                          stop_singletons/singletons,
                                          stop_singletons/TRANSITIONS.shape[0]))
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


handlers.append([CommandHandler(['ends', 'starts', 'after', 'before', 'mean', 'deviation', 'states', 'singleton'],
                                relations), {'action': Ca.TYPING, 'mods': True}])


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


handlers.append([CommandHandler(['converge', 'diverge'], convergence), {'action': Ca.TYPING, 'mods': True}])


def merge(bot, update):
    """<state> <state>: merge first state into second"""
    global TRANSITIONS, STATES

    expr = clean(update.message.text)
    states = expr.split()

    if len(states) != 2:
        update.message.reply_text(text='Proper syntax is /merge <state> <state>')
        return

    if any(s not in STATES for s in states):
        update.message.reply_text(text='One or both input states not found in markov states.')
        return

    ind = STATES.index(states[0])
    del STATES[ind]

    keep = [c for c in range(TRANSITIONS.shape[0]) if c != ind]

    row = TRANSITIONS.getrow(ind)[:, keep]
    col = TRANSITIONS.getcol(ind)[keep, :]
    loop = TRANSITIONS[ind, ind]

    TRANSITIONS = TRANSITIONS[keep, :][:, keep]

    ind = STATES.index(states[1])
    TRANSITIONS[ind, :] += row
    TRANSITIONS[:, ind] += col
    TRANSITIONS[ind, ind] += loop

    update.message.reply_text(text='Merged state "{}" into state "{}".'.format(*states))


handlers.append([CommandHandler('merge', merge), {'action': Ca.TYPING, 'mods': True}])


def delete(bot, update):
    """delete a state"""
    global TRANSITIONS, STATES

    expr = clean(update.message.text)
    state = expr.split()[0]

    if state not in STATES:
        update.message.reply_text(text='Input state not found in markov states.')
        return

    ind = STATES.index(state)
    del STATES[ind]
    keep = [c for c in range(TRANSITIONS.shape[0]) if c != ind]
    TRANSITIONS = TRANSITIONS[keep, :][:, keep]

    update.message.reply_text(text='Deleted {}.'.format(state))


handlers.append([CommandHandler('delete', delete), {'action': Ca.TYPING, 'mods': True}])


def insert(bot, update):
    """insert new state in markov states"""
    expr = clean(update.message.text)
    state = expr.split()[0]

    accumulator(bot, update, insert=state)

    update.message.reply_text(text='Inserted "{}" into markov states.'.format(state))


handlers.append([CommandHandler('insert', insert), {'action': Ca.TYPING, 'mods': True}])


def rename(bot, update):
    """rename markov state"""
    expr = clean(update.message.text)
    states = expr.split()

    if len(states) != 2:
        update.message.reply_text(text='Proper syntax is /rename <state> <state>')
        return

    states = [process_token(states[0]), states[1]]

    if states[0] not in STATES:
        update.message.reply_text(text='State not found in markov states.')
        return

    ind = STATES.index(states[0])
    STATES[ind] = states[1]

    update.message.reply_text(text='Renamed "{}" to "{}".'.format(*states))


handlers.append([CommandHandler('rename', rename), {'action': Ca.TYPING, 'mods': True}])


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


def accumulator(bot, update, insert=None):
    """markov state accumulator"""
    global STATES, TRANSITIONS

    # splits off punctuation at ends of tokens: 'test.' -> ['test', '.']
    def splitter(text):
        tokens = []
        for t in text.split():
            has_emojis = any(c in emoji.EMOJI_UNICODE for c in t)
            non_ascii = any(c not in set(string.ascii_letters + string.punctuation) for c in t)
            no_split = has_emojis or non_ascii

            start = t[0] in set(string.punctuation) - {';', ':'} and len(t) > 1 and not no_split
            end = t[-1] in set(string.punctuation) and len(t) > 1 and not no_split

            if start and end:
                tokens.append(t[0])
                tokens.append(process_token(t.lstrip(t[0]).rstrip(t[-1])))
                tokens.append(t[-1])

            elif start:
                tokens.append(t[0])
                tokens.append(process_token(t.lstrip(t[0])))

            elif end:
                tokens.append(process_token(t.rstrip(t[-1])))
                tokens.append(t[-1])

            elif has_emojis:
                tokens.append(t)

            elif non_ascii:
                tokens.append(t.lower())

            else:
                tokens.append(process_token(t))

        return tokens

    text = insert if insert else update.message.text

    if len(text) > MAX_INPUT_SIZE:
        return

    sentence_tokenizer = PunktSentenceTokenizer()
    for s in sentence_tokenizer.tokenize(re_name(re_url(text))):
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
        if not insert:
            for i, t in enumerate(tokens):
                state = STATES.index(t)

                # absorbing state at end of sentence
                next_state = STATES.index(tokens[i+1]) if i < len(tokens) - 1 else 0

                # absorbing state at start of sentence
                if i == 0:
                    TRANSITIONS[0, state] += 1

                # transition state
                TRANSITIONS[state, next_state] += 1


handlers.append([MessageHandler(callback=accumulator, filters=(Filters.text & (~Filters.command))), None])


def flush(bot, job):
    pickle.dump([STATES, TRANSITIONS], open(MARKOV_PATH, 'wb+'))
    db_push(MARKOV_PATH)


def init(bot_globals):
    bot_globals['jobs'].run_repeating(flush, interval=bot_globals['FLUSH_INTERVAL'])
