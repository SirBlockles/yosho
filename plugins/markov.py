"""yosho plugin:markov generator"""
import string
from random import randint, choice
import stopit
from autocorrect import spell
from autocorrect.word import KNOWN_WORDS
from nltk.tokenize import PunktSentenceTokenizer
from scipy import dtype
from scipy.sparse import lil_matrix, hstack, vstack, find
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

RIGHT = set("!.?~:;,%")

handlers = []


def markov(bot, update):
    """generates sentences using a markov chain"""
    def joiner(states):
        output = []
        for i, s in enumerate(states):
            if s not in RIGHT:
                if i < len(states) - 1 and states[i + 1] in RIGHT:
                    s += states[i+1]
                output.append(s)

        return ' '.join(output)

    if len(STATES) == 0:
        update.message.reply_text(text='No markov states! Type something to contribute /markov!')
        return

    def start():
        i = randint(1, len(STATES) - 1)
        while STATES[i] in set(string.punctuation):  # don't start on punctuation
            i = randint(1, len(STATES) - 1)
        return i

    state_index = start()  # choose a random state to start on
    output = []

    # generate text until hitting the stop state or exceeding MAX_OUTPUT_STATES
    while state_index != 0 and len(output) < MAX_OUTPUT_STATES:
        output.append(STATES[state_index])

        indices, values = find(TRANSITIONS.getrow(state_index))[1:]
        maxima = tuple(indices[i] for i, v in enumerate(values) if v == max(values))

        state_index = choice(maxima)  # chain branching

    if len(output) == MAX_OUTPUT_STATES:
        output += '...'
    elif not output[len(output) - 1] in {'.', '?', '!'}:
        output += '.'

    tokenizer = PunktSentenceTokenizer()
    reply = ' '.join((s.capitalize() for s in tokenizer.tokenize(joiner(output))))  # capitalize sentences

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

    tokenizer = PunktSentenceTokenizer()
    for s in tokenizer.tokenize(update.message.text):
        with stopit.ThreadingTimeout(ACCUMULATOR_TIMEOUT):
            tokens = []
            for t in s.split():
                last = t[::-1][0]

                if last in RIGHT:
                    tokens.append(process_token(t.rstrip(last)))
                    tokens.append(last)

                else:
                    tokens.append(process_token(t))

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
