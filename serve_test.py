from specialized.plugin_telegram import TelegramProcess
import logging
import time
import specialized.plugin_telegram as _plugin
from plugins import ProcessPack
from misc.settings import SETTINGS
import sys


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)


if __name__ == '__main__':
    SETTINGS.telegram.token = sys.argv[1]
    proc = TelegramProcess()
    proc._plugins = {_plugin.TELEGRAM_PLUGIN_NAME: ProcessPack(None, proc, None)}
    try:
        with proc:
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
