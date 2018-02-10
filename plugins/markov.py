"""yosho plugin:markov generator"""
import string
from random import randint

import stopit
from autocorrect import spell
from autocorrect.word import KNOWN_WORDS
from nltk.tokenize import PunktSentenceTokenizer
from scipy import dtype
from scipy.sparse import lil_matrix, csr_matrix, hstack, vstack
from telegram import ChatAction as Ca
from telegram.ext import CommandHandler, MessageHandler
from telegram.ext.filters import Filters

ORDER = 0

MAX_INPUT_SIZE = 256
MAX_OUTPUT_STATES = 50
ACCUMULATOR_TIMEOUT = 5

# initiate STATES and TRANSITIONS with one member (stop state)
STATES = [' ']
TRANSITIONS = lil_matrix((1, 1), dtype=dtype(int))

handlers = []


def markov(bot, update):
    """generates sentences using a markov chain"""
    if len(STATES) == 0:
        update.message.reply_text(text='No markov states! Type something to contribute /markov!')
        return

    def start():
        i = randint(1, len(STATES) - 1)
        while len(STATES[i]) == 1:
            i = randint(1, len(STATES) - 1)
        return i

    state_index = start()  # choose a random state to start on
    output = ''
    count = 0

    # generate text until hitting the stop state or exceeding MAX_OUTPUT_STATES
    while state_index != 0 and count < MAX_OUTPUT_STATES:
        output += ' ' + STATES[state_index]

        row = csr_matrix(TRANSITIONS.getrow(state_index))
        state_index = row.indices[row.data.argmax()] if row.nnz else 0

        count += 1

    if count == MAX_OUTPUT_STATES:
        output += '...'
    elif not output[len(output) - 1] in {'.', '?', '!'}:
        output += '.'

    tokenizer = PunktSentenceTokenizer()
    reply = ' '.join((s.capitalize() for s in tokenizer.tokenize(output.strip())))  # capitalize sentences

    update.message.reply_text(text=reply)


handlers.append([CommandHandler('markov', markov), {'action': Ca.TYPING, 'name': True}])


def markov_states(bot, update):
    """prints current number of distinct markov states"""
    update.message.reply_text(text='Number of markov generator states: {}'.format(len(STATES)))


handlers.append([CommandHandler('markov_states', markov_states), {'action': Ca.TYPING}])


def accumulator(bot, update):
    """markov state accumulator"""
    global STATES, TRANSITIONS

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

    with stopit.ThreadingTimeout(ACCUMULATOR_TIMEOUT):
        tokens = [process_token(t) for t in update.message.text.split()]

        temp = []
        for t in tokens:
            if len(t) > 1 and t.endswith('.'):
                temp.append(t.rstrip('.'))
                temp.append('.')
            else:
                temp.append(t)
        tokens = temp

        STATES += list(set(tokens) - set(STATES))

        if len(STATES) > TRANSITIONS.shape[0]:  # scale transition matrix accordingly
            difference = len(STATES) - TRANSITIONS.shape[0]

            v_pad = lil_matrix((difference, TRANSITIONS.shape[0]), dtype=dtype(int))
            h_pad = lil_matrix((len(STATES), difference), dtype=dtype(int))

            TRANSITIONS = vstack([TRANSITIONS, v_pad])
            TRANSITIONS = hstack([TRANSITIONS, h_pad])

            TRANSITIONS = lil_matrix(TRANSITIONS)

        for i, t in enumerate(tokens):  # increment transition matrix values
            state = STATES.index(t)
            next_state = STATES.index(tokens[i+1]) if i < len(tokens) - 1 else 0
            TRANSITIONS[0, state] += 1
            TRANSITIONS[state, next_state] += 1


handlers.append([MessageHandler(callback=accumulator, filters=(Filters.text & (~Filters.command))), None])
