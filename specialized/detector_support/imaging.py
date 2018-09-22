from PIL import Image, ImageFilter
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
