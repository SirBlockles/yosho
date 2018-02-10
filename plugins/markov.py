"""yosho plugin:markov generator"""
import string
from random import randint, choice
from numpy import logical_xor
import stopit
from autocorrect import spell
from autocorrect.word import KNOWN_WORDS
from nltk.tokenize import PunktSentenceTokenizer
from scipy.sparse import lil_matrix, hstack, vstack, find
from telegram import ChatAction as Ca
from telegram.ext import CommandHandler, MessageHandler
from telegram.ext.filters import Filters

from helpers import clean, add_s

ORDER = 0

MAX_INPUT_SIZE = 256
MAX_OUTPUT_STATES = 50
ACCUMULATOR_TIMEOUT = 5

# initiate STATES and TRANSITIONS with one member (stop state)
STATES = [' ']
TRANSITIONS = lil_matrix((1, 1), dtype=int)

RIGHT = set("!.?~:;,%")

handlers = []


def markov(bot, update):
    """generates sentences using a markov chain"""
    expr = clean(update.message.text)

    # joins together punctuation at ends of words: ['test', '.'] -> 'test.'
    def joiner(states):
        output = []
        for i, s in enumerate(states):
            if s not in RIGHT:
                if i < len(states) - 1 and states[i + 1] in RIGHT:
                    s += states[i+1]

                output.append(s)

        return ' '.join(output)

    def start():
        i = randint(1, len(STATES) - 1)
        while STATES[i] in set(string.punctuation):  # don't start on punctuation
            i = randint(1, len(STATES) - 1)
        return i

    if len(STATES) == 0:
        update.message.reply_text(text='No markov states! Type something to contribute to /markov!')
        return

    # choose a random state to start on or use state from command input
    state_index = STATES.index(expr) if expr in set(STATES) else start()

    # generate text until hitting the stop state or exceeding MAX_OUTPUT_STATES
    output = []
    while state_index != 0 and len(output) < MAX_OUTPUT_STATES:
        output.append(STATES[state_index])

        # find most probable next state(s)
        indices, values = find(TRANSITIONS.getrow(state_index))[1:]
        maxima = tuple(indices[i] for i, v in enumerate(values) if v == max(values))

        # chain branching
        state_index = choice(maxima)

    # add trailing punctuation
    if len(output) == MAX_OUTPUT_STATES:
        output += '...'
    elif not output[-1] in RIGHT:
        output += '.'

    # capitalize sentences
    tokenizer = PunktSentenceTokenizer()
    reply = ' '.join((s.capitalize() for s in tokenizer.tokenize(joiner(output))))

    update.message.reply_text(text=reply)


handlers.append([CommandHandler('markov', markov), {'action': Ca.TYPING, 'name': True}])


def convergence(bot, update):
    """number of states a starting state converges to"""
    expr = clean(update.message.text).split()

    if not expr:
        update.message.reply_text(text='Syntax is /converge <state> <optional steps int>')
        return

    state = expr[0]
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

    transitions **= steps
    converge = len(find(transitions.getrow(state_index))[1])

    update.message.reply_text(text='State "{}" converges to {} possible final state{} after {} step{}.'
                              .format(state, converge, add_s(converge), steps, add_s(steps)))


handlers.append([CommandHandler('converge', convergence), {'action': Ca.TYPING}])


def markov_states(bot, update):
    """current number of distinct markov states"""
    update.message.reply_text(text='Number of markov generator states: {}'.format(len(STATES)))


handlers.append([CommandHandler('markov_states', markov_states), {'action': Ca.TYPING}])


def accumulator(bot, update):
    """markov state accumulator"""
    global STATES, TRANSITIONS

    # splits off punctuation at ends of words: 'test.' -> ['test', '.']
    def splitter(text):
        tokens = []
        for t in text.split():
            if t[-1] in RIGHT:
                tokens.append(process_token(t.rstrip(t[-1])))
                tokens.append(t[-1])

            else:
                tokens.append(process_token(t))

        return tokens

    def process_token(t):
        # punctuation check
        if t in string.punctuation:
            return t

        # acronym and contraction check
        if all((c in string.ascii_uppercase for c in t)) or any((c in string.punctuation for c in t)):
            return t

        # known word check
        if t in KNOWN_WORDS:
            return t.lower()

        return spell(t).lower()

    if len(update.message.text) > MAX_INPUT_SIZE:
        return

    tokenizer = PunktSentenceTokenizer()
    for s in tokenizer.tokenize(update.message.text):
        with stopit.ThreadingTimeout(ACCUMULATOR_TIMEOUT):
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
                next_state = STATES.index(tokens[i+1]) if i < len(tokens) - 1 else 0  # stop state at end of sentence
                TRANSITIONS[0, state] += 1
                TRANSITIONS[state, next_state] += 1


handlers.append([MessageHandler(callback=accumulator, filters=(Filters.text & (~Filters.command))), None])
