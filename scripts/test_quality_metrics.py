"""Pure numerical tests: no video loading, models, extraction or media output."""
import unittest
import numpy as np
from quality_metrics import (merge_person_masks, region_metrics, wear_region_contrast,
                             mask_cache_key, estimate_runtime)


class QualityTests(unittest.TestCase):
    def test_union_keeps_small_and_edge_people(self):
        large = np.zeros((10, 10), dtype=np.float32)
        small = large.copy()
        large[2:8, 2:8] = .9
        small[0, 9] = .8
        merged = merge_person_masks([large, small])
        self.assertAlmostEqual(float(merged[0, 9]), .8, places=6)
        self.assertEqual(np.count_nonzero(merged), 37)

    def test_empty_instances_require_shape(self):
        self.assertEqual(merge_person_masks([], (2, 3)).shape, (2, 3))
        with self.assertRaises(ValueError):
            merge_person_masks([])

    def test_invalid_masks(self):
        for array in (np.ones((2, 2)) * 255, np.array([[np.nan]]), np.ones(3)):
            with self.assertRaises(ValueError):
                merge_person_masks([array])
        with self.assertRaises(ValueError):
            merge_person_masks([np.zeros((2, 2)), np.zeros((3, 3))])

    def test_coverage_and_leakage_separate(self):
        allowed = np.array([[1, 1], [0, 0]])
        protected = np.array([[0, 1], [0, 0]])
        clean = region_metrics(np.array([[1, 0], [0, 0]]), allowed, protected)
        leaking = region_metrics(np.ones((2, 2)), allowed, protected)
        self.assertEqual(clean['legal_region_coverage'], 1)
        self.assertEqual(clean['protected_region_leakage'], 0)
        self.assertEqual(leaking['legal_region_coverage'], 1)
        self.assertEqual(leaking['protected_region_leakage'], 1)
        self.assertEqual(leaking['effect_outside_legal_fraction'], .75)

    def test_empty_regions_are_unmeasured(self):
        result = region_metrics(np.zeros((2, 2)), np.zeros((2, 2)), np.zeros((2, 2)))
        self.assertIsNone(result['legal_region_coverage'])
        self.assertIsNone(result['effect_outside_legal_fraction'])

    def test_wear_is_low_frequency_contrast(self):
        checker = (np.indices((32, 32)).sum(axis=0) % 2).astype(float)
        patch = np.zeros((32, 32))
        patch[:, 16:] = 1
        region = np.ones((32, 32))
        self.assertEqual(wear_region_contrast(checker, region)['p90_minus_p10'], 0)
        self.assertEqual(wear_region_contrast(patch, region)['p90_minus_p10'], 1)
        self.assertIsNone(wear_region_contrast(patch, region * 0)['p90'])

    def test_cache_tracks_segmentation_not_visuals(self):
        args = ('content-hash', 'model-v1', {'confidence': .3}, {'width': 960, 'height': 540}, 30)
        key = mask_cache_key(*args)
        same = mask_cache_key(*args)
        changed = mask_cache_key('new-content', *args[1:])
        self.assertEqual(key, same)
        self.assertNotEqual(key, changed)
        with self.assertRaises(ValueError):
            mask_cache_key(*args, person_policy='largest')

    def test_runtime_cache_saves_segmentation(self):
        uncached = estimate_runtime(10, 30, 10, 20, 5, 2, 1)
        cached = estimate_runtime(10, 30, 10, 20, 5, 2, 1, cached_mask=True)
        self.assertEqual(uncached['segmentation_frames'], 100)
        self.assertEqual(cached['segmentation_frames'], 0)
        self.assertAlmostEqual(uncached['estimated_total_seconds'] - cached['estimated_total_seconds'], 2)
        with self.assertRaises(ValueError):
            estimate_runtime(-1, 30, 10, 20, 5, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
