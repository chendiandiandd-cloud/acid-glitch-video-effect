"""No media, model, renderer or frame-rate modification: clock tests only."""
import copy
import io
import json
import math
from contextlib import redirect_stdout, redirect_stderr
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import unittest

from reference_timeline import load_profile, validate_profile, select_reference, main

PROFILE = Path(__file__).resolve().parents[1] / 'references' / 'reference-profile.json'
NATURAL = {0, 2, 14, 17, 34, 38, 41}
PARTIAL = {6, 22, 25, 29}


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_profile(PROFILE)

    def lookup(self, pts, extension='truncate'):
        return select_reference(self.profile, pts, extension=extension)

    def test_all_42_cells(self):
        for frame in range(42):
            for pts in (Fraction(frame, 8), Fraction(2 * frame + 1, 16)):
                with self.subTest(frame=frame, pts=pts):
                    result = self.lookup(pts)
                    expected = 'natural' if frame in NATURAL else ('partial' if frame in PARTIAL else 'strong')
                    self.assertEqual(result['state'], expected)
                    self.assertEqual(result['reference_frame'], frame)
                    self.assertEqual(result['natural_gate'], frame in NATURAL)
                    self.assertEqual(result['strong_style_gain'], 0 if frame in NATURAL else 1)
                    self.assertEqual(result['natural_gate_scope'], 'whole_frame')
                    self.assertFalse(result['extension_is_inferred'])

    def test_natural_event_boundaries(self):
        epsilon = Fraction(1, 10**12)
        for frame in sorted(NATURAL):
            start, end = Fraction(frame, 8), Fraction(frame + 1, 8)
            self.assertTrue(self.lookup(start)['natural_gate'])
            self.assertTrue(self.lookup(end - epsilon)['natural_gate'])
            if frame:
                self.assertFalse(self.lookup(start - epsilon)['natural_gate'])
            if frame < 41:
                self.assertFalse(self.lookup(end)['natural_gate'])

    def test_baseline_is_not_return_event(self):
        self.assertEqual(self.lookup(0)['natural_event'], 'baseline')
        self.assertFalse(self.lookup(0)['is_return_event'])
        for frame in NATURAL - {0}:
            self.assertEqual(self.lookup(Fraction(frame, 8))['natural_event'], 'return_event')
        repeated = self.lookup(Fraction(21, 4), 'repeat')
        self.assertTrue(repeated['is_baseline'])
        self.assertFalse(repeated['is_return_event'])

    def test_30_60fps_pulse_sampling(self):
        # Each continuous pulse is exactly 1/8 s, not an output-frame count.
        for fps in (30, 60):
            for frame in NATURAL:
                samples = [n for n in range(math.ceil(5.25 * fps))
                           if self.lookup(Fraction(n, fps))['reference_frame'] == frame]
                self.assertIn(len(samples), (fps // 8, math.ceil(fps / 8)))
                for n in samples:
                    self.assertTrue(self.lookup(Fraction(n, fps))['natural_gate'])
                self.assertLess(abs(Fraction(len(samples), fps) - Fraction(1, 8)), Fraction(1, fps))

    def test_repeat_preserves_long_source_pts(self):
        for pts in (Fraction(100001, 8), Decimal('10000.25'), 10000.25, '10000.25'):
            result = self.lookup(pts, 'repeat')
            self.assertIs(result['source_pts'], pts)
            absolute = int(Fraction(pts) * 8)
            self.assertEqual(result['reference_frame'], absolute % 42)
            self.assertEqual(result['cycle_index'], absolute // 42)
            self.assertTrue(result['extension_is_inferred'])

    def test_truncate_endpoint_and_beyond(self):
        self.assertEqual(self.lookup(Fraction(21, 4) - Fraction(1, 10**9))['reference_frame'], 41)
        for pts in ('5.25', 6, 10000):
            with self.assertRaises(ValueError):
                self.lookup(pts)

    def test_explicit_extension_required(self):
        with self.assertRaises(TypeError):
            select_reference(self.profile, 0)
        for extension in (None, '', 'guess'):
            with self.assertRaises(ValueError):
                self.lookup(0, extension)

    def test_invalid_pts(self):
        for pts in (-1, '-0.0001', float('nan'), float('inf'), Decimal('NaN'), True, None, 'oops'):
            with self.subTest(pts=pts), self.assertRaises(ValueError):
                self.lookup(pts, 'repeat')

    def test_exact_and_float_boundaries(self):
        self.assertEqual(self.lookup(Decimal('1.75'))['reference_frame'], 14)
        boundary = 1.75
        self.assertEqual(self.lookup(math.nextafter(boundary, 0))['reference_frame'], 14)
        self.assertEqual(self.lookup(boundary - 1e-9)['reference_frame'], 13)
        exact = Fraction(7, 4) - Fraction(1, 10**18)
        self.assertEqual(self.lookup(exact)['reference_frame'], 13)
        self.assertEqual(self.lookup(0.1 + 0.15)['reference_frame'], 2)

    def test_partial_never_whole_frame_return(self):
        for frame in PARTIAL:
            result = self.lookup(Fraction(frame, 8))
            self.assertEqual(result['state'], 'partial')
            self.assertFalse(result['natural_gate'])
            self.assertFalse(result['is_return_event'])
            self.assertEqual(result['strong_style_gain'], 1)

    def test_profile_errors(self):
        patches = [('schema_version', True), ('reference_fps', 30), ('frame_count', 41),
                   ('duration_seconds', 5.0), ('frame_states', ['strong'] * 42),
                   ('natural_color_frames', [0]), ('return_event_frames', [0, 2]),
                   ('natural_branch', {})]
        for key, value in patches:
            bad = copy.deepcopy(self.profile)
            bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_profile(bad)
        for frame, state in [(1, 'liquid'), (6, 'strong'), (1, 'partial'), (2, 'partial')]:
            bad = copy.deepcopy(self.profile)
            bad['frame_states'][frame] = state
            with self.assertRaises(ValueError):
                validate_profile(bad)
        for key, value in [('scope', 'person'), ('source_time', 'reference_pts'),
                           ('strong_style_gain', 1), ('preserve_residual_distress', False)]:
            bad = copy.deepcopy(self.profile)
            bad['natural_branch'][key] = value
            with self.assertRaises(ValueError):
                validate_profile(bad)

    def test_low_fps_can_miss_pulses_without_extension(self):
        sampled = {self.lookup(Fraction(n, 2))['reference_frame'] for n in range(11)}
        self.assertNotIn(2, sampled)  # [.25, .375) missed entirely at 2 fps.
        self.assertNotIn(17, sampled)
        self.assertFalse(self.lookup(Fraction(1, 2))['natural_gate'])
        self.assertTrue(self.lookup(Fraction(1, 4))['natural_gate'])
        self.assertFalse(self.lookup(Fraction(3, 8))['natural_gate'])

    def test_cli_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            main(['--profile', str(PROFILE), '--pts', '10.75', '--extension', 'repeat'])
        result = json.loads(output.getvalue())
        self.assertEqual(result['source_pts'], '10.75')
        self.assertEqual(result['reference_frame'], 2)
        self.assertEqual(result['cycle_index'], 2)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--profile', str(PROFILE), '--pts', '0'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
