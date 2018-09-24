from srgb.srgb_gamma import srgb_to_linear_rgb, linear_rgb_to_srgb


def clamp(v, min_, max_):
    return max(min(v, max_), min_)


def linear_blend(l, r, alpha, clamp_alpha=False):
    def _dim(x):
        return len(x) if isinstance(x, (tuple, list)) else 1
    if _dim(l) != _dim(r):
        raise ValueError('Mismatching dimensions.')
    if clamp_alpha:
        alpha = clamp(alpha, 0., 1.)
    if _dim(l) == 1:
        return alpha * l + (1. - alpha) * r
    else:
        return tuple(map(lambda lr: linear_blend(*lr, alpha, clamp_alpha=False), zip(l, r)))


def fill_linear_rgb_lut(val_and_color):
    lval = None
    lcolor = None
    for rval, rcolor in val_and_color:
        if lval is not None and lcolor is not None:
            n_steps = rval - lval
            if n_steps <= 0:
                continue
            for j in range(n_steps):
                yield lval + j, tuple(map(round, linear_blend(rcolor, lcolor, j / n_steps)))
        lval, lcolor = rval, rcolor
    yield lval, lcolor


def normalize_linear_rgb_gradient(gradient):
    last_pos = None
    for pos, color in gradient:
        if last_pos is None:
            last_pos = 0
            if pos > 0.:
                yield 0, (0, 0, 0)
                # And fallthough
            elif pos <= 0.:
                yield 0, color
                continue
        new_pos = round(clamp(255 * pos, last_pos, 255))
        if new_pos != last_pos:
            yield new_pos, color
            last_pos = new_pos
    if last_pos < 255:
        yield 255, (0, 0, 0)


def make_rgb_lut(gradient):
    yield from [(val, linear_rgb_to_srgb(color))
                for val, color in fill_linear_rgb_lut([(v, srgb_to_linear_rgb(rgb))
                                                       for v, rgb in normalize_linear_rgb_gradient(gradient)])]
