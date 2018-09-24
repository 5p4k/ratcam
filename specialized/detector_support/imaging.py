from PIL import Image, ImageFilter, ImageChops
import numpy as np


def pil_median(a, size=3, reshape=True):
    filt = ImageFilter.MedianFilter(size=size)
    b = np.array(Image.fromarray(a).filter(filt).getdata())
    if reshape:
        b = b.reshape(a.shape)
    return b


def get_denoised_motion_vector_norm(a, median_size=3, reshape=True, dtype=np.float):
    # Need to use uint16 to avoid overflow. Also seems faster than float and uint32
    norm = np.sqrt(np.square(a['x'].astype(np.uint16)) + np.square(a['y'].astype(np.uint16)))
    # Scale to fill. Max norm value for 8bit signed vectors is ~182
    norm = np.interp(norm, (0, 182), (0, 255)).astype(np.uint8)
    # Apply median filter
    if median_size > 1:
        norm = pil_median(norm, size=median_size, reshape=reshape)
    # Convert to destination type
    return norm.astype(dtype)


def motion_vector_to_image(mv, size, lut):
    r_lut, g_lut, b_lut = np.array(lut, dtype=np.uint8).transpose()
    # Convert from float array
    motionv_img = Image.fromarray(mv).convert(mode='L')
    # The last column is extra (part of H264 motion vector spec I suppose)
    motionv_img = motionv_img.crop((0, 0, motionv_img.width - 1, motionv_img.height))
    # Now resize, bicubic
    motionv_img = motionv_img.resize(size, Image.BICUBIC)
    # Now map it though each of the LUTs. Faster to resize first though
    r = motionv_img.point(r_lut)
    g = motionv_img.point(g_lut)
    b = motionv_img.point(b_lut)
    # Pack and return the image.
    return Image.merge('RGB', (r, g, b))


def overlay_motion_vector_to_image(rgb_data, mv, lut):
    gray_img = Image.fromarray(rgb_data, mode='RGB').convert('L')
    col_mv = motion_vector_to_image(mv, gray_img.size, lut).convert('HSV')
    # Blend the value channel using the multiply blend mode
    value = ImageChops.multiply(gray_img, col_mv.getchannel('V'))
    # Re-merge using the newly obtained value and the colorization hue and saturation
    return Image.merge('HSV', (col_mv.getchannel('H'), col_mv.getchannel('S'), value)).convert('RGB')
