import inspect
import shlex

from telegram.ext import CommandHandler, MessageHandler


class _DynamicHandler:
    def collect_args(self, dispatcher, update):
        chat = update.effective_chat
        user = update.effective_user

        args = {'update': lambda: update,
                'bot': lambda: dispatcher.bot,
                'update_queue': lambda: dispatcher.update_queue,
                'job_queue': lambda: dispatcher.job_queue,
                'user_data': lambda: dispatcher.user_data[user.id] if user else None,
                'chat_data': lambda: dispatcher.chat_data[chat.id] if chat else None}

        sig = inspect.signature(self.callback).parameters
        return {k: v() for k, v in args.items() if k in sig}


class DynamicCommandHandler(_DynamicHandler, CommandHandler):
    def handle_update(self, update, dispatcher):
        args = self.collect_args(dispatcher, update)
        sig = inspect.signature(self.callback).parameters

        send_args = 'args' in sig
        send_command = 'command' in sig
        if send_args or send_command:
            command, *params = shlex.split((update.message or update.edited_message).text)

            if send_args:
                args['args'] = params

            if send_command:
                args['command'] = command[1:]

        return self.callback(**args)


class DynamicMessageHandler(_DynamicHandler, MessageHandler):
    def handle_update(self, update, dispatcher):
        args = self.collect_args(dispatcher, update)
        return self.callback(**args)
