import unittest
from specialized.telegram_support.handlers import make_handler, HandlerBase, _HANDLERS_CLS_PROP_NAME
from specialized.telegram_support.auth import ChatAuthTransaction, AuthAttemptResult, ChatAuthStatus, AuthStatus, \
    ChatAuthStorage
from datetime import timedelta
from misc.extended_json_codec import ExtendedJSONCodec
import json
from specialized.telegram_support.auth_io import load_chat_auth_storage, save_chat_auth_storage
import tempfile


def through_json(obj):
    return json.loads(json.dumps(obj, cls=ExtendedJSONCodec), object_hook=ExtendedJSONCodec.hook)


class HandlersTestCase(unittest.TestCase):
    class Handler:
        def __call__(self):
            return self.name, self.method()

        def __init__(self, _, method, name):
            self.method = method
            self.name = name

    def test_making_custom_handler(self):
        class TestHandlerCls(HandlerBase):
            @make_handler(HandlersTestCase.Handler, 'something')
            def bar(self):
                return 3387

        test_obj = TestHandlerCls()
        self.assertTrue(hasattr(test_obj.__class__, _HANDLERS_CLS_PROP_NAME))
        self.assertEqual(len(getattr(test_obj.__class__, _HANDLERS_CLS_PROP_NAME, [])), 1)
        handlers = list(test_obj.handlers)
        self.assertEqual(len(handlers), 1)
        self.assertEqual(handlers[0](), ('something', 3387))

    def test_nonbinding_handler(self):
        @make_handler(HandlersTestCase.Handler, 'something')
        def bar():  # pragma: no cover
            return 3387

        self.assertIs(bar.handler, bar().method)

    def test_manual_override_of_handlers_prop(self):
        with self.assertRaises(RuntimeError):
            class TestHandlerClsFailing(HandlerBase):
                _HANDLERS = 'SOME STRING'
            # Dummy
            TestHandlerClsFailing()  # pragma: no cover


class TestAuthTransaction(unittest.TestCase):
    def test_authenticate_but_no_generate(self):
        transaction = ChatAuthTransaction()
        with self.assertRaises(RuntimeError):
            transaction.authenticate('')

    def test_simple(self):
        transaction = ChatAuthTransaction()
        pwd = transaction.generate(None, None)
        self.assertIs(transaction.authenticate(pwd), AuthAttemptResult.AUTHENTICATED)
        self.assertIs(transaction.authenticate(pwd), AuthAttemptResult.ALREADY_AUTHENTICATED)
        self.assertIs(transaction.authenticate(''), AuthAttemptResult.ALREADY_AUTHENTICATED)

    def test_retry_once(self):
        transaction = ChatAuthTransaction()
        pwd = transaction.generate(None, None)
        self.assertIs(transaction.authenticate(''), AuthAttemptResult.WRONG_TOKEN)
        self.assertIs(transaction.authenticate(pwd), AuthAttemptResult.AUTHENTICATED)
        self.assertIs(transaction.authenticate(None), AuthAttemptResult.ALREADY_AUTHENTICATED)

    def test_too_many_retries(self):
        transaction = ChatAuthTransaction()
        pwd = transaction.generate(None, None)
        for _ in range(ChatAuthTransaction.MAX_RETRIES - 1):
            self.assertIs(transaction.authenticate(''), AuthAttemptResult.WRONG_TOKEN)
        self.assertIs(transaction.authenticate(''), AuthAttemptResult.TOO_MANY_RETRIES)
        self.assertIs(transaction.authenticate(None), AuthAttemptResult.TOO_MANY_RETRIES)
        self.assertIs(transaction.authenticate(pwd), AuthAttemptResult.TOO_MANY_RETRIES)

    def test_expired(self):
        transaction = ChatAuthTransaction()
        pwd = transaction.generate(None, None)
        transaction.request_time -= ChatAuthTransaction.MAX_PWD_LIFE + timedelta(seconds=1)
        self.assertIs(transaction.authenticate(pwd), AuthAttemptResult.EXPIRED)
        self.assertIs(transaction.authenticate(''), AuthAttemptResult.EXPIRED)


class TestChatAuthStatus(unittest.TestCase):
    def test_invalid_operations(self):
        status = ChatAuthStatus()
        self.assertIs(status.status, AuthStatus.UNKNOWN)
        with self.assertRaises(RuntimeError):
            status.try_auth('')
        status.start_auth(None)
        with self.assertRaises(RuntimeError):
            status.start_auth(None)
        self.assertIs(status.status, AuthStatus.ONGOING)

    def test_simple(self):
        status = ChatAuthStatus()
        self.assertIs(status.status, AuthStatus.UNKNOWN)
        pwd = status.start_auth(None)
        self.assertIs(status.status, AuthStatus.ONGOING)
        self.assertIs(status.try_auth(pwd), AuthAttemptResult.AUTHENTICATED)
        self.assertIs(status.status, AuthStatus.AUTHORIZED)
        with self.assertRaises(RuntimeError):
            status.try_auth(pwd)
        # Do this again
        status.revoke_auth()
        pwd = status.start_auth(None)
        self.assertIs(status.try_auth(pwd), AuthAttemptResult.AUTHENTICATED)
        self.assertIs(status.status, AuthStatus.AUTHORIZED)

    def test_retry_once(self):
        status = ChatAuthStatus()
        self.assertIs(status.status, AuthStatus.UNKNOWN)
        pwd = status.start_auth(None)
        self.assertIs(status.status, AuthStatus.ONGOING)
        self.assertIs(status.try_auth(''), AuthAttemptResult.WRONG_TOKEN)
        self.assertIs(status.status, AuthStatus.ONGOING)
        self.assertIs(status.try_auth(pwd), AuthAttemptResult.AUTHENTICATED)
        self.assertIs(status.status, AuthStatus.AUTHORIZED)
        with self.assertRaises(RuntimeError):
            status.try_auth(pwd)

    def test_too_many_retries(self):
        status = ChatAuthStatus()
        self.assertIs(status.status, AuthStatus.UNKNOWN)
        pwd = status.start_auth(None)
        self.assertIs(status.status, AuthStatus.ONGOING)
        for _ in range(ChatAuthTransaction.MAX_RETRIES - 1):
            self.assertIs(status.try_auth(''), AuthAttemptResult.WRONG_TOKEN)
            self.assertIs(status.status, AuthStatus.ONGOING)
        self.assertIs(status.try_auth(''), AuthAttemptResult.TOO_MANY_RETRIES)
        self.assertIs(status.status, AuthStatus.DENIED)
        with self.assertRaises(RuntimeError):
            status.try_auth(pwd)

    def test_expired(self):
        status = ChatAuthStatus()
        self.assertIs(status.status, AuthStatus.UNKNOWN)
        pwd = status.start_auth(None)
        self.assertIs(status.status, AuthStatus.ONGOING)
        status.transaction.request_time -= ChatAuthTransaction.MAX_PWD_LIFE + timedelta(seconds=1)
        self.assertIs(status.try_auth(pwd), AuthAttemptResult.EXPIRED)
        self.assertIs(status.status, AuthStatus.DENIED)
        with self.assertRaises(RuntimeError):
            status.try_auth(pwd)


class TestChatAuthStorage(unittest.TestCase):
    def test_successful(self):
        storage = ChatAuthStorage()
        chat_id = 1549730692
        self.assertTrue(storage.has_auth_status(chat_id, AuthStatus.UNKNOWN))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.DENIED))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.ONGOING))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.AUTHORIZED))
        self.assertEqual(len(list(storage.authorized_chats)), 0)
        status = storage[chat_id]
        self.assertTrue(storage.has_auth_status(chat_id, AuthStatus.UNKNOWN))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.DENIED))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.ONGOING))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.AUTHORIZED))
        self.assertEqual(len(list(storage.authorized_chats)), 0)
        pwd = status.start_auth(None)
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.UNKNOWN))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.DENIED))
        self.assertTrue(storage.has_auth_status(chat_id, AuthStatus.ONGOING))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.AUTHORIZED))
        self.assertEqual(len(list(storage.authorized_chats)), 0)
        status.try_auth(pwd)
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.UNKNOWN))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.DENIED))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.ONGOING))
        self.assertTrue(storage.has_auth_status(chat_id, AuthStatus.AUTHORIZED))
        self.assertEqual(list(storage.authorized_chats), [status])

    def test_failure(self):
        storage = ChatAuthStorage()
        chat_id = 1549730692
        status = storage[chat_id]
        status.start_auth(None)
        for _ in range(ChatAuthTransaction.MAX_RETRIES - 1):
            status.try_auth('')
            self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.UNKNOWN))
            self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.DENIED))
            self.assertTrue(storage.has_auth_status(chat_id, AuthStatus.ONGOING))
            self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.AUTHORIZED))
            self.assertEqual(len(list(storage.authorized_chats)), 0)
        status.try_auth('')
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.UNKNOWN))
        self.assertTrue(storage.has_auth_status(chat_id, AuthStatus.DENIED))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.ONGOING))
        self.assertFalse(storage.has_auth_status(chat_id, AuthStatus.AUTHORIZED))
        self.assertEqual(len(list(storage.authorized_chats)), 0)

    def assert_same_status(self, l, r):
        if l is None:
            self.assertIs(r, None)
        elif l is not None and r is not None:
            self.assertEqual(l.chat_id, r.chat_id)
            self.assertEqual(l.user, r.user)
            self.assertEqual(l.date, r.date)
            self.assertEqual(l.status, r.status)
            self.assert_same_transaction(l.transaction, r.transaction)

    def assert_same_transaction(self, l, r):
        if l is None:
            self.assertIs(r, None)
        elif l is not None and r is not None:
            self.assertEqual(l.chat_id, r.chat_id)
            self.assertEqual(l.requested_by, r.requested_by)
            self.assertEqual(l.request_time, r.request_time)
            self.assertEqual(l.retries, r.retries)
            self.assertEqual(l.password, r.password)

    def assert_passes_through_json(self, storage, unique_chat_id):
        should_be_same_storage = through_json(storage)
        should_be_same_status = should_be_same_storage[unique_chat_id]
        self.assert_same_status(should_be_same_status, storage[unique_chat_id])

    def test_successful_json(self):
        storage = ChatAuthStorage()
        chat_id = 1549730692
        status = storage[chat_id]
        self.assert_passes_through_json(storage, chat_id)
        pwd = status.start_auth(None)
        self.assert_passes_through_json(storage, chat_id)
        status.try_auth(pwd)
        self.assert_passes_through_json(storage, chat_id)

    def test_failure_json(self):
        storage = ChatAuthStorage()
        chat_id = 1549730692
        status = storage[chat_id]
        status.start_auth(None)
        for _ in range(ChatAuthTransaction.MAX_RETRIES - 1):
            status.try_auth('')
            self.assert_passes_through_json(storage, chat_id)
        status.try_auth('')
        self.assert_passes_through_json(storage, chat_id)


class TestSaveAuthStorage(unittest.TestCase):
    def test_simple(self):
        storage = load_chat_auth_storage('')
        # Just test that the settings are saved without any exc
        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            save_chat_auth_storage(temp_file.name, storage)
