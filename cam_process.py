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

from time import sleep
import threading
import logging
from cam_manager import CameraManager

_log = logging.getLogger('ratcam')


class CameraProcess:
    def __init__(self, bot_interface, cam_interface):
        self._cam_interface = cam_interface
        self._cam = CameraManager(bot_interface)
        self._poll_commands_thread = threading.Thread(target=self._poll_commands, name='cam_poll_commands')
        self._shutdown = threading.Event()

    def _poll_commands(self):
        while not self._shutdown.is_set():
            cmd = self._cam_interface.pop_cmd_if_changed(0.5)
            if cmd is not None:
                _log.debug('Got command set %s', str(cmd))
                if cmd.video_request:
                    self._cam.take_video()
                if cmd.photo_request:
                    self._cam.take_photo()
                if cmd.toggle_detection is not None:
                    self._cam.detection_enabled = cmd.toggle_detection
                if cmd.toggle_light is not None:
                    self._cam.light_enabled = cmd.toggle_light
            # Process time dependent events
            self._cam.spin()
            # Do not allow too may commands to poke with the camera manager
            sleep(0.2)

    def __enter__(self):
        self._cam.__enter__()
        self._poll_commands_thread.start()
        _log.info('Cam: polling threads in place.')

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._shutdown.set()
        self._poll_commands_thread.join()
        _log.info('Cam: polling threads joined.')
        self._cam.__exit__(exc_type, exc_val, exc_tb)
