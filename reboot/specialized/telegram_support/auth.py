from enum import Enum
from collections import namedtuple
from datetime import datetime, timedelta
from bcrypt import hashpw, gensalt, checkpw
from ...misc.pwgen import generate_password
from ...misc.extended_json_codec import make_custom_serializable


class AuthStatus(Enum):
    AUTHORIZED = 'authorized'
    NEGOTIATING = 'negotiating'
    DENIED = 'denied'
    UNKNOWN = 'unknown'


_CHAT_AUTH_FIELDS = ['user', 'datetime', 'status']


class ChatAuthStatus(namedtuple('_ChatAuth', _CHAT_AUTH_FIELDS)):
    @classmethod
    def from_json(cls, payload):
        return cls(*map(payload.get, _CHAT_AUTH_FIELDS))

    def to_json(self):
        return {field: getattr(self, field) for field in _CHAT_AUTH_FIELDS}


class AuthAttemptResult(Enum):
    AUTHENTICATED = 'authenticated'
    ALREADY_AUTHENTICATED = 'already authenticated'
    TOO_MANY_RETRIES = 'too many retries'
    WRONG_TOKEN = 'wrong token'
    EXPIRED = 'expired token'


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
                return AuthAttemptResult.WRONG_PASSWORD

    def to_json(self):
        return self.__dict__

    @classmethod
    def from_json(cls, payload):
        obj = cls()
        obj.__dict__.update(payload)


class ChatAuthStorage:
    def __init__(self):
        self._storage = {}

    @property
    def authorized_chat_ids(self):
        yield from filter(lambda chat_id: self.status(chat_id) == AuthStatus.OK, self._storage.keys())

    def status(self, chat_id):
        status = self._storage.get(chat_id, None)
        if status is None:
            return AuthStatus.UNKNOWN
        elif isinstance(status, AuthorizedChat):
            return AuthStatus.OK
        elif isinstance(status, DeniedChat):
            return AuthStatus.DENIED
        elif isinstance(status, ChatAuthProcess):
            return AuthStatus.ONGOING
        return None

    def start_auth(self, chat_id, user):
        assert(self.status(chat_id) == AuthStatus.UNKNOWN)
        self._storage[chat_id] = ChatAuthProcess()
        return self._storage[chat_id].generate(chat_id, user)

    def do_auth(self, chat_id, pwd):
        assert(self.status(chat_id) == AuthStatus.ONGOING)
        process = self._storage[chat_id]
        result = process.authenticate(pwd)
        if result == AuthAttemptResult.AUTHENTICATED:
            self._storage[chat_id] = AuthorizedChat(process.requested_by, process.request_time)
        elif result in [AuthAttemptResult.TOO_MANY_RETRIES, AuthAttemptResult.EXPIRED]:
            self._storage[chat_id] = DeniedChat(process.requested_by, process.request_time)
        return result

    def revoke_auth(self, chat_id):
        if chat_id in self._storage:
            del self._storage[chat_id]

    def as_json_obj(self):
        # Convert keys to string
        return {str(k): self._storage[k] for k in self._storage}

    @classmethod
    def from_json_obj(cls, d):
        retval = ChatAuthStorage()
        # Convert the keys back from string
        retval._storage = {int(k): d[k] for k in d}
        return retval