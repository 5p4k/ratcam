#!/usr/bin/env python
from multiprocessing import Process
from threading import Thread
from time import sleep


def noop():
    while True:
        sleep(0.1)


def proc1_thread():
    try:
        noop()
    except KeyboardInterrupt:
        print('Interrupt in proc1_thread')


def proc1_main():
    t = Thread(target=proc1_thread)
    t.start()
    try:
        noop()
    except KeyboardInterrupt:
        print('Interrupt in proc1_main')


def main():
    p = Process(target=proc1_main)
    p.start()
    try:
        p.join()
    except KeyboardInterrupt:
        print('Interrupt in main')


if __name__ == '__main__':
    main()
