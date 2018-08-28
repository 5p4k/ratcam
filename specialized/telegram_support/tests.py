import unittest
from specialized.telegram_support.handlers import make_handler, HandlerBase, _HANDLERS_CLS_PROP_NAME


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


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
