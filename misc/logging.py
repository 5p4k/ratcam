import logging
import re


def ensure_logging_setup(level=logging.INFO, reset=False, **kwargs):
    if reset:
        # Remove all handlers associated with the root logger object.
        # https://stackoverflow.com/a/12158233/1749822
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=level, **kwargs)


_RGX_FIRST_CAP = re.compile('(.)([A-Z][a-z]+)')
_RGX_ALL_CAP = re.compile('([a-z0-9])([A-Z])')


def camel_to_snake(camel_txt):
    # https://stackoverflow.com/a/1176023/1749822
    return _RGX_ALL_CAP.sub(r'\1_\2', _RGX_FIRST_CAP.sub(r'\1_\2', camel_txt)).lower()
