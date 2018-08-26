import os


PWD_CHARS = 'abcdefghjkmnpqrstuvwxyz23456789_?!-'  # No zeros or ones or o or l


def _pick_random_char():
    c = len(PWD_CHARS)
    while c >= len(PWD_CHARS):
        c = int(os.urandom(1)[0])
    return PWD_CHARS[c]


def generate_password(length=10, charset=PWD_CHARS):
    return ''.join(_pick_random_char() for _ in range(length))
