#!/usr/bin/env python3
import argparse
import os
import sys

import logging
import io

from time import sleep
from telegram.ext import Updater, CommandHandler
from picamera import PiCamera


TOKEN_FILE='token.txt'
CAM = None
LOG = None

CUR_MODE = None
MODE_PHOTO = {'sensor_mode': 3, 'shutter_speed': 200000, 'resolution': '1640x1232'}
MODE_VIDEO = {'sensor_mode': 4, 'framerate': 15, 'resolution': '640x480'}

def ensure_camera(mode):
    global CAM, CUR_MODE
    if CAM is None:
        CAM = PiCamera()
        CAM.iso = 800
        CAM.sensor_mode = 3
        CAM.exposure_mode = 'night'
        CAM.shutter_speed = 2000000
    if CUR_MODE is not mode:
        CUR_MODE = mode
        for k in mode:
            setattr(CAM, k, mode[k])
        sleep(2)



def bot_start(bot, update):
    global CAM
    ensure_camera(MODE_PHOTO)
    bot.send_message(chat_id=update.message.chat_id, text='Ratcam SimpleBot active.')


def bot_photo(bot, update):
    global CAM, LOG
    ensure_camera(MODE_PHOTO)
    with io.BytesIO() as stream:
        LOG.info('A picture is going to be taken for user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        CAM.capture(stream, 'jpeg')
        stream.seek(0)
        bot.send_photo(chat_id=update.message.chat_id, photo=stream)


def bot_video(bot, update):
    global CAM, LOG
    ensure_camera(MODE_VIDEO)
    with io.BytesIO() as stream:
        LOG.info('A video is going to be recorder for user %s, %s (%s)',
            update.message.from_user.first_name,
            update.message.from_user.last_name,
            update.message.from_user.username)
        CAM.start_recording(stream, format='h264', quality=23)
        CAM.wait_recording(8)
        stream.seek(0)
        bot.send_video(chat_id=update.message.chat_id, video=stream)


def main(token):
    global LOG
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
    LOG = logging.getLogger()
    updater = Updater(token=token)
    updater.dispatcher.add_handler(CommandHandler('start', bot_start))
    updater.dispatcher.add_handler(CommandHandler('photo', bot_photo))
    updater.dispatcher.add_handler(CommandHandler('video', bot_video))
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
