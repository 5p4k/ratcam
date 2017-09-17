#!/usr/bin/env python3
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

import argparse
import os
import sys
from time import sleep

TOKEN_FILE = 'token.txt'

from ratcam_bot import RatcamBot
from cam_manager import CameraManager, EventType
from state import SharedState

# TODO splitting between two processes

class CameraProcess(CameraManager): # TODO move to cam_manager?
    def __init__(self, state):
        super(CameraProcess, self).__init__()
        self.state = state

    def _report_event(self, event_type, file_name = None):
        if event_type == EventType.VIDEO_READY:
            self.state.push_media(file_name, 'video')
        elif event_type == EventType.PHOTO_READY:
            self.state.push_media(file_name, 'photo')
        elif event_type == EventType.MOTION_DETECTED:
            self.state.motion_began = True
        elif event_type == EventType.MOTION_STILL:
            self.state.motion_stopped = True

    def spin(self):
        super(CameraProcess, self).spin()
        if self.state.photo_request:
            self.take_photo()
        if self.state.video_request:
            self.take_video()

class BotProcess()


def main(token):
    bot = RatcamBot(token)
    with bot:
        try:
            while True:
                bot.spin()
                sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Control your Pi camera using Telegram.')
    parser.add_argument('--token', '-t', required=False, help='Telegram API token.')
    args = parser.parse_args()
    token = args.token
    if token is None:
        # Try looking for a token.txt file
        try:
            if os.path.isfile(TOKEN_FILE):
                with open(TOKEN_FILE, 'r') as stream:
                    token = stream.readline().strip()
        except Exception as ex:
            print(ex, file=sys.stderr)
            token = None
    if token is None:
        print('Specify the token as argument or provide it in a file named %s.' % TOKEN_FILE, file=sys.stderr)
        sys.exit(1)
    else:
        main(token)
