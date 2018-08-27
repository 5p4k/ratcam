import os


def generate_password(length=10, charset='abcdefghjkmnpqrstuvwxyz23456789_?!-'):
    def _pick_random_char():
        c = len(charset)
        while c >= len(charset):
            c = int(os.urandom(1)[0])
        return charset[c]

    return ''.join(_pick_random_char() for _ in range(length))
