"""Cheap startup guards for the pinned runtime; no probes, installs or reports."""
from importlib import import_module, metadata
from pathlib import Path
import shutil
import sys

REQUIREMENTS = Path(__file__).resolve().parents[1] / 'requirements.txt'
PINS = {'numpy': '1.26.4', 'opencv-python-headless': '4.11.0.86',
        'onnxruntime': '1.16.3'}


def install_hint():
    return f'Install in a CPython 3.11 venv: python -m pip install -r "{REQUIREMENTS}"'


def check_python():
    # Other Python versions/wheel platforms have not been validated for this lock.
    if sys.version_info[:2] != (3, 11):
        raise ValueError('This dependency lock supports CPython 3.11; '
                         'other Python versions (including 3.13+) are not supported. ' + install_hint())


def require_pin(distribution):
    try:
        installed = metadata.version(distribution)
    except metadata.PackageNotFoundError as e:
        raise ValueError(f'Missing Python package: {distribution}. ' + install_hint()) from e
    expected = PINS[distribution]
    if installed != expected:
        reason = (' NumPy 2 is incompatible with the pinned ONNXRuntime 1.16.3 ABI.'
                  if distribution == 'numpy' else '')
        raise ValueError(f'Unsupported {distribution}=={installed}; required =={expected}.'
                         + reason + ' ' + install_hint())


def check_base():
    check_python()
    require_pin('numpy')
    require_pin('opencv-python-headless')


def load_native(module):
    try:
        return import_module(module)
    except (ImportError, OSError) as e:
        raise ValueError(f'Cannot load native Python package {module}: {e}. '
                         'Check OS/architecture wheel and native library support. ' + install_hint()) from e


def load_onnxruntime():
    check_base()
    require_pin('onnxruntime')  # metadata only, before any native ORT import/session
    return load_native('onnxruntime')


def require_ffmpeg():
    missing = [binary for binary in ('ffmpeg', 'ffprobe') if shutil.which(binary) is None]
    if missing:
        raise ValueError('Missing system executable(s): ' + ', '.join(missing) + '. '
                         'Install FFmpeg/ffprobe >=5 with libx264 separately and add them to PATH; '
                         'pip requirements do not provide FFmpeg. Nothing is installed automatically.')
