import unittest
from misc.tests import *
from plugins.tests import *
from specialized.tests import *
from specialized.telegram_support.tests import *
from misc.logging import ensure_logging_setup
import logging


ensure_logging_setup(logging.DEBUG, True)


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
