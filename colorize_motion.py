#
# Copyright (C) 2017  Pietro Saccardi

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from srgb.srgb_gamma import srgb_to_linear_rgb, linear_rgb_to_srgb
import numpy as np
from PIL import Image, ImageChops


def _lin_blend(left, right, factor):
    return int(0.5 + (1. - factor) * left[0] + factor * right[0]), \
           int(0.5 + (1. - factor) * left[1] + factor * right[1]), \
           int(0.5 + (1. - factor) * left[2] + factor * right[2])


def _make_lin_ramp(left, right, n_val):
    return [_lin_blend(left, right, n / n_val) for n in range(n_val)]


def _make_linear_gradient_lut(step_color):
    retval = []
    for i in range(len(step_color) - 1):
        t0, lcol = step_color[i]
        t1, rcol = step_color[i + 1]
        retval += _make_lin_ramp(lcol, rcol, t1 - t0)
    retval.append(step_color[-1][1])
    return retval


def _colors_to_step_color(colors, conv_fn=None):
    assert (len(colors) > 1)
    clamp = lambda x: int(min(max(x, 0.), 1.) * 255)
    conv = lambda x: x if conv_fn is None else conv_fn(x)
    # Rearrange the colors, using 0-255 as first tuple entry and the numpy representation as second
    colors = sorted([(clamp(t), conv(col)) for t, col in colors])
    # Patch missing start and end colors
    if colors[0][0] != 0:
        colors.insert(0, (0, (0, 0, 0)))
    if colors[-1][0] != 255:
        colors.append((255, (0, 0, 0)))
    return colors


def make_rgb_gradient_lut(*colors):
    return list(map(linear_rgb_to_srgb, _make_linear_gradient_lut(_colors_to_step_color(colors, srgb_to_linear_rgb))))


# Make the color lookup tables
_MOTION_GRADIENT = [(0., (255, 255, 255)), (0.25, (66, 134, 244)), (0.75, (193, 65, 244)), (1., (255, 0, 246))]
_R_LUT, _G_LUT, _B_LUT = np.array(make_rgb_gradient_lut(*_MOTION_GRADIENT), dtype=np.uint8).transpose()


def _colorize_motionv(motionv, expected_size):
    # Convert from float array
    motionv_img = Image.fromarray(motionv).convert(mode='L')
    # The last column is extra (part of H264 motion vector spec I suppose)
    motionv_img = motionv_img.crop((0, 0, motionv_img.width - 1, motionv_img.height))
    # Now resize, bicubic
    motionv_img = motionv_img.resize(expected_size, Image.BICUBIC)
    # Now map it though each of the LUTs. Faster to resize first though
    r = motionv_img.point(_R_LUT)
    g = motionv_img.point(_G_LUT)
    b = motionv_img.point(_B_LUT)
    # Pack and return the image.
    return Image.merge('RGB', (r, g, b))


def overlay_motionv(rgb_data, motionv):
    gray_img = Image.fromarray(rgb_data, mode='RGB').convert('L')
    col_mv = _colorize_motionv(motionv, gray_img.size).convert('HSV')
    # Blend the value channel using the multiply blend mode
    value = ImageChops.multiply(gray_img, col_mv.getchannel('V'))
    # Re-merge using the newly obtained value and the colorization hue and saturation
    return Image.merge('HSV', (col_mv.getchannel('H'), col_mv.getchannel('S'), value)).convert('RGB')
