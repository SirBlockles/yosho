import shlex
from inspect import signature
from typing import Callable

from telegram import ChatAction
from telegram.ext import CommandHandler, MessageHandler
from telegram.ext.filters import BaseFilter
from telegram.message import Message

from utils.helpers import can_pass_to


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
                  'user':         (lambda: user if user else None),
                  'chat':         (lambda: chat if chat else None)}

        sig = signature(self.callback).parameters

        # Optimization for large messages.
        send_args = can_pass_to('args', sig)
        send_command = can_pass_to('command', sig)
        if send_args or send_command:
            try:
                command, *params = shlex.split((update.message or update.edited_message).text)

            except Exception as e:
                update.message.chat.send_action(ChatAction.TYPING)
                update.message.reply_text(f'Error parsing input: "{e}".')
                return

            if send_args:
                passes['args'] = lambda: params

            if send_command:
                passes['command'] = lambda: command.lstrip('/')

        return {k: v() for k, v in passes.items() if can_pass_to(k, sig)}


class DynamicCommandHandler(_DynamicHandler, CommandHandler):
    """Autowiring CommandHandler."""
    def handle_update(self, update, dispatcher):
        args = self.collect_args(dispatcher, update)

        return not args or self.callback(**args)


class DynamicMessageHandler(_DynamicHandler, MessageHandler):
    """Autowiring MessageHandler."""
    def handle_update(self, update, dispatcher):
        args = self.collect_args(dispatcher, update)
        return self.callback(**args)


class DynamicFilter(BaseFilter):
    """Autowiring filter that allows for arbitrary conditions."""
    def __init__(self, func: Callable[[Message], bool], ctx=None):
        self.func = func
        self.ctx = ctx

    def filter(self, message):
        sig = signature(self.func).parameters
        passes = {'ctx':     (lambda: self.ctx),
                  'message': (lambda: message),
                  'user':    (lambda: message.from_user)}
        return self.func(**{k: v() for k, v in passes.items() if can_pass_to(k, sig)})
