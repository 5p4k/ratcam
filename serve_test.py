from reboot.specialized.plugin_telegram import TelegramProcess
import logging
import time
import reboot.specialized.plugin_telegram as _plugin
from reboot.plugins.base import ProcessPack
import sys


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)


if __name__ == '__main__':
    _plugin._TELEGRAM_TEMP_TOKEN = sys.argv[1]
    proc = TelegramProcess()
    proc._plugins = {_plugin._TELEGRAM_PLUGIN_NAME: ProcessPack(None, proc, None)}
    try:
        with proc:
            while True:
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
