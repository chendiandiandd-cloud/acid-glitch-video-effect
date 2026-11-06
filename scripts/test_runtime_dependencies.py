"""Development-only dependency guards; never import incompatible native libraries."""
import subprocess
import sys
import unittest
from unittest.mock import patch

import runtime_dependencies as deps


class DependencyGuards(unittest.TestCase):
    def test_pinned_base_metadata_only(self):
        with patch.object(deps.metadata, 'version', side_effect=deps.PINS.__getitem__), \
             patch.object(deps, 'import_module') as native:
            deps.check_base()
        native.assert_not_called()

    def test_numpy2_rejected_before_any_native_import(self):
        def version(name):
            return '2.2.6' if name == 'numpy' else deps.PINS[name]
        with patch.object(deps.metadata, 'version', side_effect=version), \
             patch.object(deps, 'import_module') as native:
            with self.assertRaisesRegex(ValueError, 'NumPy 2.*ONNXRuntime 1.16.3 ABI'):
                deps.load_onnxruntime()
        native.assert_not_called()

    def test_missing_base_package_is_actionable(self):
        with patch.object(deps.metadata, 'version', side_effect=deps.metadata.PackageNotFoundError), \
             patch.object(deps, 'import_module') as native:
            with self.assertRaisesRegex(ValueError, 'Missing Python package: numpy.*pip install -r'):
                deps.check_base()
        native.assert_not_called()

    def test_missing_ort_is_actionable_and_not_imported(self):
        def version(name):
            if name == 'onnxruntime':
                raise deps.metadata.PackageNotFoundError(name)
            return deps.PINS[name]
        with patch.object(deps.metadata, 'version', side_effect=version), \
             patch.object(deps, 'import_module') as native:
            with self.assertRaisesRegex(ValueError, 'Missing Python package: onnxruntime'):
                deps.load_onnxruntime()
        native.assert_not_called()

    def test_wrong_ort_pin_rejected_before_import(self):
        def version(name):
            return '1.17.0' if name == 'onnxruntime' else deps.PINS[name]
        with patch.object(deps.metadata, 'version', side_effect=version), \
             patch.object(deps, 'import_module') as native:
            with self.assertRaisesRegex(ValueError, 'Unsupported onnxruntime==1.17.0'):
                deps.load_onnxruntime()
        native.assert_not_called()

    def test_unsupported_python(self):
        for version in ((3, 10), (3, 12), (3, 13)):
            with self.subTest(version=version), patch.object(deps.sys, 'version_info', version):
                with self.assertRaisesRegex(ValueError, 'supports CPython 3.11'):
                    deps.check_python()

    def test_missing_ffmpeg_without_spawning(self):
        with patch.object(deps.shutil, 'which', return_value=None), \
             patch.object(subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(ValueError, 'ffmpeg, ffprobe.*pip requirements do not provide FFmpeg'):
                deps.require_ffmpeg()
        spawn.assert_not_called()

    def test_native_library_error_has_wheel_hint(self):
        with patch.object(deps, 'import_module', side_effect=OSError('missing shared library')):
            with self.assertRaisesRegex(ValueError, 'native.*cv2.*OS/architecture wheel'):
                deps.load_native('cv2')

    def test_cli_missing_packages_no_traceback(self):
        result = subprocess.run([sys.executable, '-S', '-B',
            str(deps.REQUIREMENTS.parent / 'scripts/render_video.py'), '--help'],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Missing Python package: numpy', result.stderr)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
