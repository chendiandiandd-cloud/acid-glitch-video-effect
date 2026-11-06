"""Mock-only preflight tests; no media decoding, generation or model execution."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import inspect_video

SOURCE = {'codec': 'mock', 'display_width': 1280, 'display_height': 720,
          'rotation': 0, 'duration': 12.7, 'fps': 30, 'audio_present': True}


class InspectTests(unittest.TestCase):
    def run_metadata(self, require_mask=False, mismatch=False):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.fixture'
            source.touch()
            output = Path(tmp) / 'report'
            argv = ['inspect_video.py', str(source), '--output-dir', str(output),
                    '--metadata-only', '--segmentation-mode', 'lightweight']
            if require_mask:
                argv.append('--require-mask')
            if mismatch:
                mask = Path(tmp) / 'mask.fixture'
                mask.touch()
                argv.extend(['--mask', str(mask)])
            probes = [SOURCE, {**SOURCE, 'display_width': 640}] if mismatch else [SOURCE]
            with patch('sys.argv', argv), patch.object(inspect_video, 'probe', side_effect=probes), \
                 patch.object(inspect_video.shutil, 'which', return_value='/mock/ffprobe'), \
                 patch.object(inspect_video.subprocess, 'run') as process, \
                 contextlib.redirect_stdout(io.StringIO()):
                code = inspect_video.main()
                process.assert_not_called()
            report = json.loads((output / 'preflight.json').read_text())
            self.assertFalse((output / 'input_contact.jpg').exists())
            self.assertIsNone(report['contact_sheet'])
            self.assertFalse(report['models_used'])
            self.assertTrue(report['metadata_only'])
            return code, report

    def test_metadata_never_extracts(self):
        code, report = self.run_metadata()
        self.assertEqual(code, 0)
        self.assertEqual(report['render_gate'], 'input_metadata_ready')
        self.assertIn('metadata-only needs no contact sheet', report['notes'][1])
        self.assertNotIn('before rendering', report['notes'][1])

    def test_required_mask_missing_blocks(self):
        code, report = self.run_metadata(require_mask=True)
        self.assertEqual(code, 2)
        self.assertIn('subject_mask_missing', report['blocking_reasons'])

    def test_geometry_mismatch_blocks(self):
        code, report = self.run_metadata(mismatch=True)
        self.assertEqual(code, 2)
        self.assertIn('display_size_matches', report['blocking_reasons'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
