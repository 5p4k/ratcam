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
from time import sleep
from ratcam_bot import BotProcess
from cam_manager import CameraProcess
from state import SharedState
from multiprocessing import Process, Manager
import os
import sys

TOKEN_FILE = 'token.txt'



def bot_process(state, token):
    bot = BotProcess(state, token)
    with bot:
        while True:
            bot.spin()
            sleep(1)

def cam_process(state):
    cam = CameraProcess(state)
    with cam:
        while True:
            cam.spin()
            sleep(1)

def main(token):
    with Manager() as manager:
        state = SharedState(manager)
        cam = Process(target=cam_process, args=(state,))
        bot = Process(target=bot_process, args=(state, token))
        cam.start()
        bot.start()
        bot.join()
        cam.join()


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
