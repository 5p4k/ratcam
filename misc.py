import logging

__log = None

def log():
    global __log
    if __log is None:
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
        __log = logging.getLogger()
    return __log
