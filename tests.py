import unittest
from misc.tests import *
from plugins.tests import *
from specialized.telegram_support.tests import *
from misc.logging import ensure_logging_setup
import logging


if __name__ == '__main__':
    ensure_logging_setup(logging.DEBUG, True)
    unittest.main()
