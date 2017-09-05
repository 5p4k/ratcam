#!/usr/bin/env python3
import argparse
import os
import sys

import logging
import io

from telegram.ext import Updater, CommandHandler
from picamera import PiCamera


TOKEN_FILE='token.txt'
CAM = None
LOG = None

def ensure_camera():
    global CAM
    if CAM is None:
        CAM = PiCamera()
        CAM.iso = 800
        CAM.sensor_mode = 3
        CAM.exposure_mode = 'night'
        CAM.shutter_speed = 2000000


def bot_start(bot, update):
    global CAM
    ensure_camera()
    bot.send_message(chat_id=update.message.chat_id, text='Ratcam SimpleBot active.')


def bot_photo(bot, update):
    global CAM, LOG
    ensure_camera()
    with io.BytesIO() as stream:
        LOG.info('A picture was taken by users %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        CAM.capture(stream, 'jpeg')
        stream.seek(0)
        bot.send_photo(chat_id=update.message.chat_id, photo=stream)


def main(token):
    global LOG
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    LOG = logging.getLogger()
    updater = Updater(token=token)
    updater.dispatcher.add_handler(CommandHandler('start', bot_start))
    updater.dispatcher.add_handler(CommandHandler('photo', bot_photo))
    updater.start_polling()
    updater.idle()


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
