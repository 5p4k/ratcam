BOOL_YES = ['yes', 'y', 'on', '1', 't', 'true']
BOOL_NO = ['no', 'n', 'off', '0', 'f', 'false']


def fuzzy_bool(arg):
    arg = arg.lower().strip()
    if arg in BOOL_YES:
        return True
    elif arg in BOOL_NO:
        return False
    raise ValueError()


def bool_desc(arg):
    if arg is True:
        return 'on'
    elif arg is False:
        return 'off'
    elif arg is None:
        return 'none'
    raise ValueError()


def user_desc(update):
    user = update.message.from_user
    return '@%s %s %s' % (user.username, user.first_name, user.last_name)
