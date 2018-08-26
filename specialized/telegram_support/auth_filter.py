from telegram.ext import BaseFilter


class AuthStatusFilter(BaseFilter):
    def __init__(self, chat_auth_storage, status):
        self.chat_auth_storage = chat_auth_storage
        self.requested_status = status

    def filter(self, message):
        return self.chat_auth_storage.has_auth_status(message.chat_id, self.requested_status)
