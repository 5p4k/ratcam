import logging


def ensure_logging_setup(level=logging.INFO, reset=False):
    if reset:
        # Remove all handlers associated with the root logger object.
        # https://stackoverflow.com/a/12158233/1749822
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=level)

