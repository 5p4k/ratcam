#
# Copyright (C) 2017  Pietro Saccardi

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from datetime import datetime, timedelta
import os
import bcrypt
import json
from enum import Enum
from telegram.ext import BaseFilter


PWD_CHARS = 'abcdefghjkmnpqrstuvwxyz23456789_?!-'  # No zeros or ones or o or l
MAX_RETRIES = 3
MAX_PWD_LIFE = timedelta(seconds=180)


def _pick_random_char():
    c = len(PWD_CHARS)
    while c >= len(PWD_CHARS):
        c = int(os.urandom(1)[0])
    return PWD_CHARS[c]


def generate_password(length=10):
    return ''.join(_pick_random_char() for _ in range(length))


class AuthAttemptResult(Enum):
    AUTHENTICATED = 'AUTHENTICATED'
    ALREADY_AUTHENTICATED = 'ALREADY_AUTHENTICATED'
    TOO_MANY_RETRIES = 'TOO_MANY_RETRIES'
    WRONG_PASSWORD = 'WRONG_PASSWORD'
    EXPIRED = 'EXPIRED'


class AuthStatus(Enum):
    OK = 1
    ONGOING = 2
    DENIED = 3
    UNKNOWN = 4


class ChatAuth:
    def __init__(self):
        self._d = dict()

    @property
    def authorized_chat_ids(self):
        yield from filter(lambda chat_id: isinstance(self._d[chat_id], bool) and self._d[chat_id], self._d.keys())

    def status(self, chat_id):
        status = self._d.get(chat_id, None)
        if status is None:
            return AuthStatus.UNKNOWN
        elif isinstance(status, bool):
            return AuthStatus.OK if status else AuthStatus.DENIED
        else:
            assert(isinstance(status, ChatAuthProcess))
            return AuthStatus.ONGOING

    def start_auth(self, chat_id, user):
        assert(self.status(chat_id) == AuthStatus.UNKNOWN)
        self._d[chat_id] = ChatAuthProcess()
        return self._d[chat_id].generate(chat_id, user)

    def do_auth(self, chat_id, pwd):
        assert(self.status(chat_id) == AuthStatus.ONGOING)
        process = self._d[chat_id]
        result = process.authenticate(pwd)
        if result == AuthAttemptResult.AUTHENTICATED:
            self._d[chat_id] = True
        elif result in [AuthAttemptResult.TOO_MANY_RETRIES, AuthAttemptResult.EXPIRED]:
            self._d[chat_id] = False
        return result

    def as_json_obj(self):
        return self._d

    @classmethod
    def from_json_obj(cls, d):
        retval = ChatAuth()
        retval._d = d
        return retval


class AuthStatusFilter(BaseFilter):
    def __init__(self, chat_auth, status):
        self.chat_auth = chat_auth
        self.requested_status = status

    def filter(self, message):
        return self.chat_auth.status(message.chat_id) == self.requested_status


class ChatAuthProcess:
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
        self.password = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt())
        self.retries = 0

    def authenticate(self, pwd):
        assert(self.retries >= 0)
        if self.password is None:
            return AuthAttemptResult.ALREADY_AUTHENTICATED
        elif self.retries >= MAX_RETRIES:
            self.password = None
            return AuthAttemptResult.TOO_MANY_RETRIES
        elif datetime.now() - self.request_time > MAX_PWD_LIFE:
            self.password = None
            return AuthAttemptResult.EXPIRED
        elif bcrypt.checkpw(pwd.encode(), self.password):
            self.password = None
            return AuthAttemptResult.AUTHENTICATED
        else:
            self.retries += 1
            if self.retries >= MAX_RETRIES:
                self.password = None
                return AuthAttemptResult.TOO_MANY_RETRIES
            else:
                return AuthAttemptResult.WRONG_PASSWORD

    def as_json_obj(self):
        return {k: getattr(self, k) for k in ['chat_id', 'requested_by', 'request_time', 'retries', 'password']}

    @classmethod
    def from_json_obj(cls, d):
        retval = ChatAuthProcess()
        for k in ['chat_id', 'requested_by', 'request_time', 'retries', 'password']:
            setattr(retval, k, d[k])
        return retval


class ChatAuthJSONCodec(json.JSONEncoder):
    VALID_CLASSES = [ChatAuthProcess.__name__, ChatAuth.__name__]

    def default(self, obj):
        if callable(getattr(obj, 'as_json_obj', None)):
            return {'__type': obj.__class__.__name__, '__payload': obj.as_json_obj()}
        elif isinstance(obj, datetime):
            return {'__type': obj.__class__.__name__, '__payload': obj.timestamp()}
        elif isinstance(obj, bytes):
            return {'__type': obj.__class__.__name__, '__payload': obj.hex()}
        else:
            return json.JSONEncoder.default(self, obj)

    @classmethod
    def hook(cls, d):
        if not ('__type' in d and '__payload' in d):
            return d
        typ = d['__type']
        payload = d['__payload']
        if typ == bytes.__name__:
            return bytes.fromhex(payload)
        elif typ == datetime.__name__:
            return datetime.fromtimestamp(payload)
        elif typ not in ChatAuthJSONCodec.VALID_CLASSES:
            # Sanitize the typ
            return d
        else:
            retcls = globals().get(typ, None)
            if retcls and callable(getattr(retcls, 'from_json_obj')):
                return retcls.from_json_obj(payload)
        return d
