"""Synthetic-array tests only; no media IO or models."""
import unittest
import numpy as np
from background_print_states import background_state, STATES
from background_structure import protected_background_composite


class BackgroundPrintStatesTests(unittest.TestCase):
    def setUp(self):
        self.source = np.repeat(np.array([[0, 64, 120, 128, 136, 192, 255]],
                                        dtype=np.uint8)[..., None], 3, axis=2)
        self.kw = dict(color_order='RGB', dark_color=(0, 0, 0),
                       light_color=(255, 230, 0))

    def run_state(self, state='duotone', **kwargs):
        return background_state(self.source, state, **(self.kw | kwargs))

    def test_duotone_only_two_colors(self):
        out = self.run_state()
        self.assertEqual(set(map(tuple, out.reshape(-1, 3))),
                         {(0, 0, 0), (255, 230, 0)})
        np.testing.assert_array_equal(out[0, :3], np.zeros((3, 3), np.uint8))

    def test_source_copy_and_immutable(self):
        before = self.source.copy()
        out = self.run_state('source')
        np.testing.assert_array_equal(out, before)
        out[:] = 9
        np.testing.assert_array_equal(self.source, before)

    def test_halftone_narrow_only(self):
        zero = self.run_state(halftone=np.zeros((1, 7)))
        one = self.run_state(halftone=np.ones((1, 7)))
        np.testing.assert_array_equal(zero[:, [0, 1, 5, 6]],
                                      one[:, [0, 1, 5, 6]])
        self.assertTrue(np.all(zero[0, 2:5] == (255, 230, 0)))
        self.assertTrue(np.all(one[0, 2:5] == 0))

    def test_zero_width_hard_threshold(self):
        np.testing.assert_array_equal(self.run_state(transition_width=0),
            self.run_state(transition_width=0, halftone=np.ones((1, 7))))

    def test_transition_endpoints_solid(self):
        self.source = np.repeat(np.array([[51, 204]], np.uint8)[..., None], 3, 2)
        out = self.run_state(threshold=.5, transition_width=.6,
                             halftone=np.array([[0., 1.]]))
        np.testing.assert_array_equal(out[0], [(0, 0, 0), (255, 230, 0)])

    def test_colorfield_shared_ink_mask(self):
        field = np.arange(21, dtype=np.uint8).reshape(1, 7, 3) + 80
        dots = np.array([[0., 1., .2, .8, .9, 0., 1.]])
        duo = self.run_state(halftone=dots)
        out = self.run_state('ink_colorfield', color_field=field, halftone=dots)
        ink = np.all(duo == 0, axis=2)
        np.testing.assert_array_equal(out[ink], np.zeros((ink.sum(), 3), np.uint8))
        np.testing.assert_array_equal(out[~ink], field[~ink])

    def test_liquid_whole_replacement(self):
        frame = np.full_like(self.source, 77)
        out = self.run_state('liquid_replace', liquid_frame=frame)
        np.testing.assert_array_equal(out, frame)
        self.assertFalse(np.shares_memory(out, frame))

    def test_glitch_exact_caller_frame(self):
        frame = self.source[:, ::-1].copy()
        np.testing.assert_array_equal(self.run_state('horizontal_glitch',
                                                     glitch_frame=frame), frame)

    def test_missing_required_frames(self):
        for state in ('ink_colorfield', 'liquid_replace', 'horizontal_glitch'):
            with self.subTest(state=state), self.assertRaises(ValueError):
                self.run_state(state)

    def test_rgb_bgr_luma(self):
        self.source = np.array([[[255, 0, 0], [0, 0, 255], [0, 255, 0]]], np.uint8)
        rgb = self.run_state(threshold=.15, transition_width=0)
        bgr = self.run_state(color_order='BGR', threshold=.15, transition_width=0)
        np.testing.assert_array_equal(rgb[0], [(255, 230, 0), (0, 0, 0), (255, 230, 0)])
        np.testing.assert_array_equal(bgr[0], [(0, 0, 0), (255, 230, 0), (255, 230, 0)])

    def test_explicit_order_required(self):
        with self.assertRaises(TypeError):
            background_state(self.source, 'source', dark_color=(0, 0, 0),
                             light_color=(255, 230, 0))
        with self.assertRaises(ValueError):
            self.run_state(color_order='rgb')

    def test_invalid_scalars(self):
        for args in ({'threshold': 0}, {'threshold': 1}, {'threshold': np.nan},
                     {'threshold': np.inf}, {'transition_width': -.1},
                     {'transition_width': 1.1}, {'transition_width': np.nan},
                     {'threshold': .02}, {'threshold': True}):
            with self.subTest(args=args), self.assertRaises((ValueError, TypeError)):
                self.run_state(**args)

    def test_invalid_colors(self):
        for color in ((-1, 0, 0), (256, 0, 0), (0., 0., 0.),
                      (np.nan, 0, 0), (True, False, True), (0, 0)):
            with self.subTest(color=color), self.assertRaises((ValueError, TypeError)):
                self.run_state(dark_color=color)

    def test_invalid_halftone(self):
        for dots in (np.zeros((1, 7), np.uint8), np.zeros((7, 1)),
                     np.full((1, 7), np.nan), np.full((1, 7), np.inf),
                     np.full((1, 7), -.01), np.full((1, 7), 1.01)):
            with self.subTest(), self.assertRaises((ValueError, TypeError)):
                self.run_state(halftone=dots)

    def test_invalid_frame_shapes_dtypes_even_unused(self):
        for name in ('color_field', 'liquid_frame', 'glitch_frame'):
            for frame in (np.zeros((1, 7, 3)), np.zeros((2, 7, 3), np.uint8),
                          np.zeros((1, 7, 4), np.uint8)):
                with self.subTest(name=name), self.assertRaises((ValueError, TypeError)):
                    self.run_state('source', **{name: frame})
        for frame in (np.zeros((0, 7, 3), np.uint8), np.zeros((1, 7)),
                      np.zeros((1, 7, 3), np.int16)):
            with self.assertRaises((ValueError, TypeError)):
                background_state(frame, 'source', **self.kw)

    def test_unknown_state(self):
        for state in ('invalid', None, ['source']):
            with self.assertRaises(ValueError):
                self.run_state(state)

    def test_all_inputs_immutable(self):
        field = np.full_like(self.source, 91)
        dots = np.full((1, 7), .5)
        originals = [a.copy() for a in (self.source, field, dots)]
        for state in STATES:
            self.run_state(state, color_field=field, liquid_frame=field,
                           glitch_frame=field, halftone=dots)
        for a, before in zip((self.source, field, dots), originals):
            np.testing.assert_array_equal(a, before)

    def test_integration_source_background_subject_stays_ink(self):
        approved = np.full_like(self.source, (255, 230, 0))
        approved[0, 3] = 0
        protected = np.zeros((1, 7)); protected[0, 3] = 1
        result = protected_background_composite(approved, self.run_state('source'),
                    np.ones((1, 7)), protected, natural_gate=False)
        np.testing.assert_array_equal(result[0, 3], (0, 0, 0))
        np.testing.assert_array_equal(result[protected == 0], self.source[protected == 0])

    def test_natural_gate_overrides_all_states_and_subject(self):
        for state in STATES:
            bg = self.run_state(state, color_field=np.full_like(self.source, 90),
                                liquid_frame=np.full_like(self.source, 70),
                                glitch_frame=np.full_like(self.source, 40))
            result = protected_background_composite(np.zeros_like(self.source), bg,
                        np.ones((1, 7)), np.ones((1, 7)), natural_gate=True,
                        natural_frame=self.source)
            np.testing.assert_array_equal(result, self.source)
            self.assertFalse(np.shares_memory(result, self.source))


if __name__ == '__main__':
    unittest.main()
