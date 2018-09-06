import unittest
from misc.tests import *
from plugins.tests import *
from specialized.tests import *
from specialized.telegram_support.tests import *
from misc.logging import ensure_logging_setup
import logging
import specialized.plugin_picamera


ensure_logging_setup(logging.DEBUG, True)

# Patch the warmup time so we don't have to wait
specialized.plugin_picamera._WARMUP_THREAD_TIME = 0.


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
