from enum import Enum
from datetime import datetime, timedelta
from bcrypt import hashpw, gensalt, checkpw
from misc.pwgen import generate_password
from misc.extended_json_codec import make_custom_serializable


@make_custom_serializable
class AuthStatus(Enum):
    AUTHORIZED = 'authorized'
    ONGOING = 'ongoing'
    DENIED = 'denied'
    UNKNOWN = 'unknown'


class AuthAttemptResult(Enum):
    AUTHENTICATED = 'authenticated'
    ALREADY_AUTHENTICATED = 'already authenticated'
    TOO_MANY_RETRIES = 'too many retries'
    WRONG_TOKEN = 'wrong token'
    EXPIRED = 'expired token'


@make_custom_serializable
class ChatAuthStatus:
    def __init__(self, chat_id=None, status=AuthStatus.UNKNOWN, user=None, date=None, transaction=None):
        self._chat_id = chat_id
        self.user = user
        self.date = date
        self.status = status
        self.transaction = transaction

    @property
    def chat_id(self):
        return self._chat_id

    @chat_id.setter
    def chat_id(self, new_chat_id):
        self._chat_id = new_chat_id
        if self.transaction is not None:
            self.transaction.chat_id = new_chat_id

    def start_auth(self, user):
        assert self.status == AuthStatus.UNKNOWN and self.transaction is None
        self.transaction = ChatAuthTransaction()
        self.status = AuthStatus.ONGOING
        return self.transaction.generate(self.chat_id, user)

    def try_auth(self, pwd):
        assert self.status == AuthStatus.ONGOING and self.transaction is not None
        result = self.transaction.authenticate(pwd)
        if result == AuthAttemptResult.AUTHENTICATED:
            self.date = self.transaction.request_time
            self.user = self.transaction.requested_by
            self.status = AuthStatus.AUTHORIZED
            self.transaction = None
        elif result in [AuthAttemptResult.TOO_MANY_RETRIES, AuthAttemptResult.EXPIRED]:
            self.status = AuthStatus.DENIED
            self.transaction = None
        return result

    def revoke_auth(self):
        self.status = AuthStatus.UNKNOWN
        self.user = None
        self.date = None


@make_custom_serializable
class ChatAuthTransaction:
    MAX_RETRIES = 3
    MAX_PWD_LIFE = timedelta(seconds=180)

    def __init__(self):
        self.chat_id = None
        self.requested_by = None
        self.request_time = datetime.min
        self.retries = -1
        self.password = None

    def generate(self, chat_id, requested_by):
        pwd = generate_password()
        self.chat_id = chat_id
        self.requested_by = requested_by
        self.request_time = datetime.now()
        self.password = hashpw(pwd.encode(), gensalt())
        self.retries = 0
        return pwd

    def authenticate(self, pwd):
        assert(self.retries >= 0)
        if self.password is None:
            return AuthAttemptResult.ALREADY_AUTHENTICATED
        elif self.retries >= self.__class__.MAX_RETRIES:
            self.password = None
            return AuthAttemptResult.TOO_MANY_RETRIES
        elif datetime.now() - self.request_time > self.__class__.MAX_PWD_LIFE:
            self.password = None
            return AuthAttemptResult.EXPIRED
        elif checkpw(pwd.encode(), self.password):
            self.password = None
            return AuthAttemptResult.AUTHENTICATED
        else:
            self.retries += 1
            if self.retries >= self.__class__.MAX_RETRIES:
                self.password = None
                return AuthAttemptResult.TOO_MANY_RETRIES
            else:
                return AuthAttemptResult.WRONG_TOKEN


@make_custom_serializable
class ChatAuthStorage:
    def __init__(self):
        self._storage = {}

    def has_auth_status(self, chat_id, status):
        if chat_id in self._storage:
            return self._storage[chat_id].status == status
        return status == AuthStatus.UNKNOWN

    def __getitem__(self, chat_id):
        if chat_id not in self._storage:
            self._storage[chat_id] = ChatAuthStatus(chat_id)
        return self._storage[chat_id]

    def replace_chat_id(self, chat_id, new_chat_id):
        if chat_id not in self._storage:
            return
        chat_auth_status = self._storage[chat_id]
        del self._storage[chat_id]
        chat_auth_status.chat_id = new_chat_id
        self._storage[chat_auth_status.chat_id] = chat_auth_status

    @property
    def authorized_chats(self):
        yield from filter(lambda chat: chat.status == AuthStatus.AUTHORIZED, self._storage.values())

    def to_json(self):
        return list(self._storage.values())

    @classmethod
    def from_json(cls, payload):
        obj = cls()
        obj._storage = dict({entry.chat_id: entry for entry in payload})
        return obj
