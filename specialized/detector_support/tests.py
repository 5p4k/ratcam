import unittest
from specialized.detector_support.ramp import normalize_linear_rgb_gradient, make_rgb_lut, linear_blend
from srgb.srgb_gamma import srgb_to_linear_rgb, linear_rgb_to_srgb


class TestNormalizeGradient(unittest.TestCase):
    def test_simple(self):
        arg = [
            (0., (0, 127, 0)),
            (1., (0, 255, 0))
        ]
        exp = [
            (0, (0, 127, 0)),
            (255, (0, 255, 0))
        ]
        self.assertEqual(exp, list(normalize_linear_rgb_gradient(arg)))

    def test_with_missing_data(self):
        arg = [
            (0.1, (0, 127, 0)),
            (1., (0, 255, 0))
        ]
        exp = [
            (0, (0, 0, 0)),
            (26, (0, 127, 0)),
            (255, (0, 255, 0))
        ]
        self.assertEqual(exp, list(normalize_linear_rgb_gradient(arg)))
        arg = [
            (0., (0, 127, 0)),
            (0.9, (0, 255, 0))
        ]
        exp = [
            (0, (0, 127, 0)),
            (230, (0, 255, 0)),
            (255, (0, 0, 0)),
        ]
        self.assertEqual(exp, list(normalize_linear_rgb_gradient(arg)))
        arg = [
            (0.1, (0, 127, 0)),
            (0.9, (0, 255, 0))
        ]
        exp = [
            (0, (0, 0, 0)),
            (26, (0, 127, 0)),
            (230, (0, 255, 0)),
            (255, (0, 0, 0)),
        ]
        self.assertEqual(exp, list(normalize_linear_rgb_gradient(arg)))

    def test_out_of_range(self):
        arg = [
            (0., (0, 127, 0)),
            (1.1, (0, 255, 0))
        ]
        exp = [
            (0, (0, 127, 0)),
            (255, (0, 255, 0))
        ]
        self.assertEqual(exp, list(normalize_linear_rgb_gradient(arg)))
        arg = [
            (-0.1, (0, 127, 0)),
            (1.1, (0, 255, 0))
        ]
        exp = [
            (0, (0, 127, 0)),
            (255, (0, 255, 0))
        ]
        self.assertEqual(exp, list(normalize_linear_rgb_gradient(arg)))

    def test_non_consecutive(self):
        arg = [
            (0., (1, 0, 0)),
            (-1.5, (2, 0, 0)),
            (0.1, (3, 0, 0)),
            (0.09, (4, 0, 0)),
            (1., (5, 0, 0))
        ]
        exp = [
            (0, (1, 0, 0)),
            (26, (3, 0, 0)),
            (255, (5, 0, 0))
        ]
        self.assertEqual(exp, list(normalize_linear_rgb_gradient(arg)))


class TestLUTHelper(unittest.TestCase):
    def test_simple(self):
        ramp = [
            (0.0, linear_rgb_to_srgb((0,    64, 128))),
            (0.5, linear_rgb_to_srgb((128, 192,   0))),
            (1.0, linear_rgb_to_srgb((255,  65, 127)))
        ]
        exp_r = list(range(127)) + list(range(127, 256))
        exp_g = list(range(64, 192)) + list(range(192, 63, -1))
        exp_b = list(range(128, 0, -1)) + list(range(128))
        exp = list(enumerate(map(linear_rgb_to_srgb, zip(exp_r, exp_g, exp_b))))
        self.assertEqual(exp, list(make_rgb_lut(ramp)))

    def test_mismatch_dim_in_blend(self):
        with self.assertRaises(ValueError):
            linear_blend((1, 2), 3, 0.5)
