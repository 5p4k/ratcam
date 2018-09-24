def clamp(v, min_, max_):
    return max(min(v, max_), min_)


def blend(l, r, alpha, clamp_alpha=False):
    def _dim(x):
        return len(x) if isinstance(x, (tuple, list)) else 1
    if _dim(l) != _dim(r):
        raise ValueError('Mismatching dimensions.')
    if clamp_alpha:
        alpha = clamp(alpha, 0., 1.)
    if _dim(l) == 1:
        return alpha * l + (1. - alpha) * r
    else:
        return tuple(map(lambda lr: blend(*lr, alpha, clamp_alpha=False), zip(l, r)))


def fill_rgb_lut(val_and_color):
    lval = None
    lcolor = None
    for rval, rcolor in val_and_color:
        if lval is not None and lcolor is not None:
            n_steps = rval - lval
            if n_steps <= 0:
                continue
            for j in range(n_steps):
                yield lval + j, tuple(map(round, blend(rcolor, lcolor, j / n_steps)))
        lval, lcolor = rval, rcolor
    yield lval, lcolor


def normalize_rgb_gradient(ramp):
    last_unit_pos = None
    for unit_pos, color in ramp:
        if last_unit_pos is None:
            last_unit_pos = 0
            if unit_pos > 0.:
                yield 0, (0, 0, 0)
                # And fallthough
            elif unit_pos <= 0.:
                yield 0, color
                continue
        new_unit_pos = round(clamp(255 * unit_pos, last_unit_pos, 255))
        if new_unit_pos != last_unit_pos:
            yield new_unit_pos, color
            last_unit_pos = new_unit_pos
    if last_unit_pos < 255:
        yield 255, (0, 0, 0)


def make_rgb_lut(rgb_gradient_ramp):
    yield from fill_rgb_lut(normalize_rgb_gradient(rgb_gradient_ramp))
