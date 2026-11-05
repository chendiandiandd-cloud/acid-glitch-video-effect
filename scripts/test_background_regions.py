import unittest
import numpy as np
from background_regions import editable_background_region, horizontal_cut_rows
from background_structure import protected_background_composite


class BackgroundRegionsTests(unittest.TestCase):
    def test_full_background_has_no_height_boundary(self):
        for h, w in ((40, 80), (80, 40), (1, 2)):
            region = editable_background_region(np.zeros((h, w)), policy='full_background')
            np.testing.assert_array_equal(region, np.ones((h, w)))
            self.assertEqual(horizontal_cut_rows(region), ())

    def test_nonzero_soft_support_is_fully_excluded(self):
        mask = np.array([[0, 1e-12, .5, 1]], dtype=np.float64)
        copy = mask.copy()
        region = editable_background_region(mask, policy='full_background')
        np.testing.assert_array_equal(region, [[1, 0, 0, 0]])
        np.testing.assert_array_equal(mask, copy)

    def test_explicit_keeps_soft_values_and_protection(self):
        allowed = np.array([[0, .2], [.7, 1]], dtype=np.float32)
        before = allowed.copy()
        region = editable_background_region([[0, 0], [.01, 0]], policy='explicit', allowed_mask=allowed)
        np.testing.assert_array_equal(region, np.array([[0, .2], [0, 1]], dtype=np.float32))
        np.testing.assert_array_equal(allowed, before)
        self.assertFalse(np.shares_memory(region, allowed))

    def test_region_updates_with_moving_protection(self):
        first = np.zeros((12, 20)); first[2:8, 2:5] = 1
        second = np.zeros_like(first); second[2:8, 12:15] = 1
        a = editable_background_region(first, policy='full_background')
        b = editable_background_region(second, policy='full_background')
        self.assertEqual(b[4, 3], 1)
        self.assertEqual(b[4, 13], 0)
        self.assertFalse(np.array_equal(a, b))
        self.assertEqual(horizontal_cut_rows(b), ())

    def test_explicit_policy_does_not_hide_bad_horizontal_cut(self):
        bad = np.ones((20, 100)); bad[10:] = 0
        region = editable_background_region(np.zeros_like(bad), policy='explicit', allowed_mask=bad)
        self.assertEqual(horizontal_cut_rows(region), (10,))
        # Known content-derived horizontal boundaries require contextual review.
        self.assertEqual(horizontal_cut_rows(1-region), (10,))

    def test_soft_transition_not_reported_as_hard_cut(self):
        ramp = np.repeat(np.linspace(0, 1, 30)[:, None], 40, axis=1)
        self.assertEqual(horizontal_cut_rows(ramp), ())

    def test_boolean_and_uint8_diagnostic(self):
        for dtype in (bool, np.uint8, np.float32):
            region = np.zeros((8, 10), dtype=dtype); region[4:] = 1
            self.assertEqual(horizontal_cut_rows(region), (4,))

    def test_short_edges_not_reported_as_framewide(self):
        region = np.ones((20, 100)); region[8:12, 30:50] = 0
        self.assertEqual(horizontal_cut_rows(region), ())

    def test_composite_keeps_person_and_separates_full_natural_gate(self):
        rng = np.random.default_rng(7)
        approved = rng.integers(0, 256, (12, 18, 3), dtype=np.uint8)
        changed = np.full_like(approved, 200)
        natural = np.full_like(approved, 35)
        protected = np.zeros((12, 18), dtype=np.float32)
        protected[2:10, 5:9] = .001
        region = editable_background_region(protected, policy='full_background')
        strong = protected_background_composite(approved, changed, region, protected)
        np.testing.assert_array_equal(strong[protected > 0], approved[protected > 0])
        np.testing.assert_array_equal(strong[protected == 0], changed[protected == 0])
        for row in (0, 5, 11):
            np.testing.assert_array_equal(strong[row, 0], changed[row, 0])
        restored = protected_background_composite(approved, changed, region, protected,
                                                  natural_gate=True, natural_frame=natural)
        np.testing.assert_array_equal(restored, natural)

    def test_invalid_policy_combinations(self):
        base = np.zeros((3, 4))
        for kwargs in ({'policy': 'unknown'}, {'policy':'explicit'},
                       {'policy':'full_background', 'allowed_mask':base},
                       {'policy':'explicit', 'allowed_mask':np.zeros((4, 3))}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    editable_background_region(base, **kwargs)

    def test_invalid_masks_fail_closed(self):
        for mask in ([], np.zeros((2, 2, 1)), [[-1]], [[1.01]], [[np.nan]],
                     [[np.inf]], [['x']], [[1j]]):
            with self.subTest(mask=mask):
                with self.assertRaises(ValueError):
                    editable_background_region(mask, policy='full_background')
                with self.assertRaises(ValueError):
                    horizontal_cut_rows(mask)

    def test_invalid_diagnostic_parameters(self):
        for value in (0, -1, 1.1, np.nan, np.inf, True, 'x', [1]):
            for key in ('min_span', 'min_step'):
                with self.subTest(value=value, key=key):
                    with self.assertRaises(ValueError):
                        horizontal_cut_rows(np.ones((2, 3)), **{key:value})


if __name__ == '__main__':
    unittest.main()
