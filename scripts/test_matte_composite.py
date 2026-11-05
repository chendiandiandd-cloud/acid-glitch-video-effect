import unittest
import numpy as np
from matte_composite import matte_background_composite


class MatteCompositeTests(unittest.TestCase):
    def setUp(self):
        self.old = np.full((5, 9, 3), [255, 0, 255], dtype=np.uint8)
        self.person = np.full_like(self.old, [200, 210, 0])
        self.background = np.full_like(self.old, [0, 30, 50])
        self.alpha = np.zeros((5, 9), dtype=np.float32)
        self.alpha[:, 2] = .25
        self.alpha[:, 3] = .75
        self.alpha[:, 4:7] = 1
        self.core = np.zeros_like(self.alpha)
        self.core[:, 5] = 1

    def compose(self, **kwargs):
        args = dict(approved_frame=self.old, person_frame=self.person,
                    changed_background=self.background, alpha=self.alpha,
                    core_mask=self.core)
        args.update(kwargs)
        return matte_background_composite(**args)

    def test_no_old_background_in_soft_edge(self):
        result = self.compose()
        for col in (2, 3):
            a = self.alpha[0, col]
            expected = np.rint(self.person[0, col].astype(float)*a
                               + self.background[0, col].astype(float)*(1-a)).astype(np.uint8)
            np.testing.assert_array_equal(result[0, col], expected)
        changed_old = np.zeros_like(self.old)
        other = self.compose(approved_frame=changed_old)
        np.testing.assert_array_equal(result[self.core==0], other[self.core==0])

    def test_background_and_opaque_person_endpoints(self):
        result = self.compose()
        np.testing.assert_array_equal(result[self.alpha==0], self.background[self.alpha==0])
        opaque = (self.alpha==1) & (self.core==0)
        np.testing.assert_array_equal(result[opaque], self.person[opaque])

    def test_core_unchanged_bytewise(self):
        result = self.compose()
        np.testing.assert_array_equal(result[self.core>0], self.old[self.core>0])

    def test_core_cannot_freeze_soft_rim(self):
        wrong = self.core.copy(); wrong[:, 2] = .01
        with self.assertRaises(ValueError):
            self.compose(core_mask=wrong)

    def test_whole_frame_natural_bypasses_core(self):
        natural = np.full_like(self.old, 64)
        result = self.compose(natural_gate=True, natural_frame=natural)
        np.testing.assert_array_equal(result, natural)
        self.assertFalse(np.shares_memory(result, natural))

    def test_missing_natural_and_nonboolean_gate_rejected(self):
        with self.assertRaises(ValueError): self.compose(natural_gate=True)
        for gate in (1, 'true', None):
            with self.assertRaises(ValueError): self.compose(natural_gate=gate)

    def test_inputs_immutable(self):
        before = [v.copy() for v in (self.old, self.person, self.background, self.alpha, self.core)]
        self.compose()
        for a, b in zip(before, (self.old, self.person, self.background, self.alpha, self.core)):
            np.testing.assert_array_equal(a, b)

    def test_invalid_masks_and_frames(self):
        for key in ('alpha', 'core_mask'):
            for mask in (np.zeros((9, 5)), np.full_like(self.alpha, np.nan),
                         np.full_like(self.alpha, np.inf), np.full_like(self.alpha, -.1),
                         np.full_like(self.alpha, 1.1), np.ones((5, 9), dtype=complex)):
                with self.subTest(key=key, dtype=mask.dtype):
                    with self.assertRaises(ValueError): self.compose(**{key:mask})
        for key in ('person_frame', 'changed_background', 'approved_frame', 'natural_frame'):
            for frame in (np.zeros((5, 9, 3), dtype=float), np.zeros((9, 5, 3), dtype=np.uint8),
                          np.zeros((5, 9), dtype=np.uint8)):
                with self.subTest(key=key):
                    with self.assertRaises(ValueError): self.compose(**{key:frame})

    def test_landscape_portrait_and_empty_core(self):
        for shape in ((2, 8, 3), (8, 2, 3), (1, 1, 3)):
            old = np.full(shape, 255, np.uint8); p = np.full(shape, 200, np.uint8)
            bg = np.zeros(shape, np.uint8); a = np.full(shape[:2], .5)
            result = matte_background_composite(old, p, bg, a, core_mask=np.zeros_like(a))
            np.testing.assert_array_equal(result, np.full(shape, 100))


if __name__ == '__main__':
    unittest.main()
