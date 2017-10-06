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

import threading
import logging
from bot_manager import BotManager

_log = logging.getLogger('ratcam')


class BotProcess:
    def __init__(self, bot_interface, cam_interface, token):
        self._bot_interface = bot_interface
        self._bot = BotManager(cam_interface, token)
        self._poll_media_thread = threading.Thread(target=self._poll_media, name='bot_poll_media')
        self._poll_motion_thread = threading.Thread(target=self._poll_motion_updates, name='bot_poll_motion')
        self._shutdown = threading.Event()

    def _poll_motion_updates(self):
        while not self._shutdown.is_set():
            _, motion_detected = self._bot_interface.pop_motion_event(0.5)
            if motion_detected is not None:
                self._bot.report_motion_detected(motion_detected)
            self._bot.spin()

    def _poll_media(self):
        while not self._shutdown.is_set():
            file_name, media_type = self._bot_interface.pop_media(1)
            if file_name is not None:
                self._bot.send_media(file_name, media_type)

    def __enter__(self):
        self._bot.__enter__()
        self._poll_media_thread.start()
        self._poll_motion_thread.start()
        _log.info('Bot: polling threads in place.')

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._shutdown.set()
        self._poll_media_thread.join()
        self._poll_motion_thread.join()
        _log.info('Bot: polling threads joined.')
        self._bot.__exit__(exc_type, exc_val, exc_tb)
