from inspect import Parameter, signature
import shlex
from typing import Callable

from telegram.ext import CommandHandler, MessageHandler
from telegram.ext.filters import BaseFilter
from telegram.message import Message


def _valid(k, sig):
    return k in sig and sig[k].kind is Parameter.POSITIONAL_OR_KEYWORD


class _DynamicHandler:
    def collect_args(self, dispatcher, update):
        chat = update.effective_chat
        user = update.effective_user

        passes = {'update':       (lambda: update),
                  'message':      (lambda: update.message),
                  'text':         (lambda: update.message.text),
                  'bot':          (lambda: dispatcher.bot),
                  'update_queue': (lambda: dispatcher.update_queue),
                  'job_queue':    (lambda: dispatcher.job_queue),
                  'user_data':    (lambda: dispatcher.user_data[user.id] if user else None),
                  'chat_data':    (lambda: dispatcher.chat_data[chat.id] if chat else None)}

        sig = signature(self.callback).parameters

        # Optimization for large messages.
        send_args = _valid('args', sig)
        send_command = _valid('command', sig)
        if send_args or send_command:
            command, *params = shlex.split((update.message or update.edited_message).text)

            if send_args:
                passes['args'] = lambda: params

            if send_command:
                passes['command'] = lambda: command.lstrip('/')

        return {k: v() for k, v in passes.items() if _valid(k, sig)}


class DynamicCommandHandler(_DynamicHandler, CommandHandler):
    """Autowiring CommandHandler."""
    def handle_update(self, update, dispatcher):
        args = self.collect_args(dispatcher, update)
        return self.callback(**args)


class DynamicMessageHandler(_DynamicHandler, MessageHandler):
    """Autowiring MessageHandler."""
    def handle_update(self, update, dispatcher):
        args = self.collect_args(dispatcher, update)
        return self.callback(**args)


class DynamicFilter(BaseFilter):
    """Filter that allows for arbitrary conditions."""
    def __init__(self, func: Callable[[Message], bool], ctx=None):
        self.func = func
        self.ctx = ctx

    def filter(self, message):
        sig = signature(self.func).parameters
        passes = {'ctx':     (lambda: self.ctx),
                  'message': (lambda: message)}
        return self.func(**{k: v() for k, v in passes.items() if _valid(k, sig)})
