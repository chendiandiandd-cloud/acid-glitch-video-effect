"""Small generated-array tests only: no file/media IO or models."""
import unittest
import numpy as np
from background_structure import protected_background_composite as composite
from background_structure import bounded_structure_warp as warp


class BackgroundStructureTests(unittest.TestCase):
    def setUp(self):
        self.src = np.arange(4 * 7 * 3, dtype=np.uint8).reshape(4, 7, 3)
        self.changed = np.full_like(self.src, 240)
        self.e = np.ones((4, 7), dtype=np.float32)
        self.p = np.zeros((4, 7), dtype=np.float64)
        self.d = np.zeros((4, 7, 2), dtype=np.float64)

    def test_protected_soft_edges_byte_equal(self):
        self.p[1, 1:4] = [1, .3, np.nextafter(0., 1.)]
        self.d[..., 0] = 1
        for out in (composite(self.src, self.changed, self.e, self.p),
                    warp(self.src, self.d, self.e, self.p, 3)):
            np.testing.assert_array_equal(out[self.p > 0], self.src[self.p > 0])

    def test_outside_editable_unchanged(self):
        self.e[:, :2] = 0
        self.d[..., 0] = 1
        for out in (composite(self.src, self.changed, self.e, self.p),
                    warp(self.src, self.d, self.e, self.p, 3)):
            np.testing.assert_array_equal(out[self.e == 0], self.src[self.e == 0])

    def test_blend_rounding(self):
        self.e.fill(.5)
        out = composite(self.src, self.changed, self.e, self.p)
        expected = np.rint((self.src.astype(float) + 240) / 2).astype(np.uint8)
        np.testing.assert_array_equal(out, expected)
        self.assertEqual(out.dtype, np.uint8)

    def test_natural_whole_frame_copy_and_no_mutation(self):
        self.p.fill(1)
        self.e.fill(0)
        natural = 255 - self.src
        arrays = [self.src, self.changed, self.e, self.p, natural]
        before = [a.copy() for a in arrays]
        out = composite(*arrays[:4], natural_gate=True, natural_frame=natural)
        np.testing.assert_array_equal(out, natural)
        self.assertFalse(np.shares_memory(out, natural))
        out.fill(0)
        for a, b in zip(arrays, before):
            np.testing.assert_array_equal(a, b)

    def test_missing_natural(self):
        with self.assertRaises(ValueError):
            composite(self.src, self.changed, self.e, self.p, natural_gate=True)

    def test_invalid_frames(self):
        for bad in (self.src.tolist(), self.src.astype(float),
                    self.src.astype(np.int16), self.src[..., 0],
                    np.zeros((0, 7, 3), np.uint8), self.src[:, :3]):
            with self.subTest(shape=getattr(bad, 'shape', None)):
                with self.assertRaises((TypeError, ValueError)):
                    composite(self.src, bad, self.e, self.p)
                with self.assertRaises((TypeError, ValueError)):
                    composite(self.src, self.changed, self.e, self.p,
                              natural_gate=True, natural_frame=bad)
        with self.assertRaises(TypeError):
            warp(self.src.astype(float), self.d, self.e, self.p, 1)

    def test_invalid_masks_both_functions(self):
        for bad in (self.e.tolist(), self.e.astype(int), self.e.astype(bool),
                    self.e[..., None], self.e[:, :2], self.e * np.nan,
                    self.e * np.inf, self.e * -0.1, self.e * 1.1):
            for e, p in ((bad, self.p), (self.e, bad)):
                with self.assertRaises((TypeError, ValueError)):
                    composite(self.src, self.changed, e, p)
                with self.assertRaises((TypeError, ValueError)):
                    warp(self.src, self.d, e, p, 2)

    def test_invalid_displacement(self):
        for bad in (self.d.tolist(), self.d.astype(int), self.d[..., 0],
                    self.d[:, :2], self.d + np.nan, self.d + np.inf,
                    self.d.astype(complex)):
            with self.assertRaises((TypeError, ValueError)):
                warp(self.src, bad, self.e, self.p, 1)

    def test_invalid_scalar_options(self):
        for bad in (True, '2', None, [2], np.array(2), -1, np.nan, np.inf):
            with self.assertRaises((TypeError, ValueError)):
                warp(self.src, self.d, self.e, self.p, bad)
        for bad in (1, 'true', None, np.array(True)):
            with self.assertRaises(TypeError):
                composite(self.src, self.changed, self.e, self.p, natural_gate=bad)

    def test_identity_and_zero_max(self):
        np.testing.assert_array_equal(warp(self.src, self.d, self.e, self.p, 5), self.src)
        self.d.fill(10)
        np.testing.assert_array_equal(warp(self.src, self.d, self.e, self.p, 0), self.src)

    def test_really_moves_source_building_structure(self):
        self.d[..., 0] = 1
        out = warp(self.src, self.d, self.e, self.p, 2)
        np.testing.assert_array_equal(out[:, :-1], self.src[:, 1:])
        self.assertFalse(np.array_equal(out[:, :-1], self.src[:, :-1]))
        np.testing.assert_array_equal(out[:, -1], self.src[:, -1])

    def test_vector_length_clamp(self):
        self.d[0, 0] = [6, 8]
        out = warp(self.src, self.d, self.e, self.p, 2.5)
        np.testing.assert_array_equal(out[0, 0], self.src[2, 2])
        # Independent component clipping would incorrectly sample [2,2]
        # for max=2; vector clamp gives [1.2,1.6] -> [x=1,y=2].
        out = warp(self.src, self.d, self.e, self.p, 2)
        np.testing.assert_array_equal(out[0, 0], self.src[2, 1])

    def test_editable_weights_displacement_only_once(self):
        self.e.fill(.5)
        self.d[..., 0] = 2
        out = warp(self.src, self.d, self.e, self.p, 2)
        np.testing.assert_array_equal(out[:, :-1], self.src[:, 1:])

    def test_cannot_sample_protected_subject(self):
        self.p[1, 3] = .001
        self.d[1, 2] = [1, 0]
        out = warp(self.src, self.d, self.e, self.p, 2)
        np.testing.assert_array_equal(out[1, 2], self.src[1, 2])

    def test_cannot_sample_outside_editable(self):
        self.e[1, 3] = 0
        self.d[1, 2] = [1, 0]
        np.testing.assert_array_equal(warp(self.src, self.d, self.e, self.p, 2), self.src)

    def test_no_wraparound_or_out_of_image_samples(self):
        for index, vector in (((0, 0), [-1, 0]), ((0, 0), [0, -1]),
                              ((3, 6), [1, 0]), ((3, 6), [0, 1]),
                              ((0, 0), [-.1, 0])):
            self.d.fill(0)
            self.d[index] = vector
            np.testing.assert_array_equal(warp(self.src, self.d, self.e, self.p, 3), self.src)

    def test_portrait_and_landscape(self):
        for h, w in ((3, 8), (8, 3), (1, 1)):
            src = np.arange(h * w * 3, dtype=np.uint8).reshape(h, w, 3)
            e, p = np.ones((h, w), float), np.zeros((h, w), float)
            d = np.zeros((h, w, 2), float)
            d[..., 1] = 1
            out = warp(src, d, e, p, 1)
            np.testing.assert_array_equal(out[:-1], src[1:])
            np.testing.assert_array_equal(out[-1], src[-1])
            np.testing.assert_array_equal(composite(src, src, e, p), src)

    def test_warp_inputs_immutable_and_extreme_finite_displacement(self):
        self.d.fill(np.finfo(float).max)
        arrays = [self.src, self.d, self.e, self.p]
        copies = [a.copy() for a in arrays]
        with np.errstate(over='raise', invalid='raise'):
            out = warp(*arrays, 1)
        np.testing.assert_array_equal(out[0, 0], self.src[1, 1])
        out.fill(0)
        for a, b in zip(arrays, copies):
            np.testing.assert_array_equal(a, b)


if __name__ == '__main__':
    unittest.main(verbosity=2)
