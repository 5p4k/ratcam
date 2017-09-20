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
from bot_manager import BotManager
from cam_manager import CameraManager
from state import SharedState
from multiprocessing import Process, Manager
import os
import sys
import logging

TOKEN_FILE = 'token.txt'
LOG_FILE = 'ratcam.log'

_log = None


def bot_process(state, token):
    bot = BotManager(state, token)
    with bot:
        while True:
            try:
                bot.spin()
                sleep(1)
            except KeyboardInterrupt:
                _log.info('BotProcess: shutting down...')
                break
            except Exception as e:
                _log.error('Error during polling: %s' % str(e))


def cam_process(state):
    cam = CameraManager(state)
    with cam:
        while True:
            try:
                cam.spin()
                sleep(1)
            except KeyboardInterrupt:
                _log.info('CameraProcess: shutting down...')
                break
            except Exception as e:
                _log.error('Error during camera spin: %s' % str(e))


def setup_log(debug=False):
    global _log
    fmt = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    lvl = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(format=fmt, level=lvl)
    _log = logging.getLogger('ratcam')
    if debug:
        handler = logging.FileHandler(LOG_FILE)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        _log.addHandler(handler)


def main(telegram_token):
    with Manager() as manager:
        try:
            state = SharedState(manager)
            cam = Process(target=cam_process, args=(state,))
            bot = Process(target=bot_process, args=(state, telegram_token))
            cam.start()
            bot.start()
            bot.join()
            cam.join()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            raise e


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Control your Pi camera using Telegram.')
    parser.add_argument('--token', '-t', required=False, help='Telegram API token.')
    parser.add_argument('--debug', '-d', required=False, action='store_true',
                        help='Turn on verbose logging and saves it to %s' % LOG_FILE)
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
        setup_log(args.debug)
        main(token)
