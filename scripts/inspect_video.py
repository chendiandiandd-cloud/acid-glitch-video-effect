"""Explicit development tool: metadata report/contact sheet, never a render prerequisite.
Original implementation for this skill, 2026-11-04. Uses only stdlib + FFmpeg.
"""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys


def ratio(value):
    try:
        numerator, denominator = str(value).split('/')
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe(path):
    result = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    data = json.loads(result.stdout)
    video = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
    if video is None:
        raise ValueError('Input has no video stream')
    rotation = next((float(s['rotation']) for s in video.get('side_data_list', []) if 'rotation' in s), 0)
    width, height = int(video['width']), int(video['height'])
    if math.isclose(abs(rotation) % 180, 90, abs_tol=0.1):
        width, height = height, width
    duration = float(video.get('duration') or data.get('format', {}).get('duration') or 0)
    if duration <= 0:
        raise ValueError('Input duration is not available')
    return {
        'codec': video.get('codec_name'), 'display_width': width, 'display_height': height,
        'rotation': rotation, 'duration': duration,
        'fps': ratio(video.get('avg_frame_rate', '0/1')),
        'audio_present': any(s.get('codec_type') == 'audio' for s in data.get('streams', [])),
        'color_transfer': video.get('color_transfer'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--mask', type=Path, help='Optional synchronized black/white foreground-mask video')
    parser.add_argument('--require-mask', action='store_true', help='Block reference-style rendering if no mask provided')
    parser.add_argument('--output-dir', type=Path, required=True, help='Runtime directory outside source/assets')
    parser.add_argument('--metadata-only', action='store_true', help='Read metadata without extracting images')
    parser.add_argument('--segmentation-mode', choices=('none', 'lightweight'), default='none',
                        help='Declared downstream policy only; this tool never runs a model')
    args = parser.parse_args()
    for binary in (('ffprobe',) if args.metadata_only else ('ffmpeg', 'ffprobe')):
        if not shutil.which(binary):
            raise ValueError(f'Missing executable: {binary}')
    if not args.input.is_file():
        raise ValueError(f'Input not found: {args.input}')
    source = probe(args.input)
    mask_checks = {}
    blocking = []
    if args.mask:
        if not args.mask.is_file():
            raise ValueError('Mask file not found')
        mask = probe(args.mask)
        mask_checks = {
            'display_size_matches': all(mask[k] == source[k] for k in ('display_width', 'display_height')),
            'duration_matches': abs(mask['duration'] - source['duration']) <= max(.1, 2 / max(source['fps'], 1)),
            'fps_matches': abs(mask['fps'] - source['fps']) < .05,
            'semantic_outline_verified': False,
        }
        blocking.extend(k for k, v in mask_checks.items() if k != 'semantic_outline_verified' and not v)
    elif args.require_mask:
        blocking.append('subject_mask_missing')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sheet = None
    if not args.metadata_only:
        sheet = args.output_dir / 'input_contact.jpg'
        sample_rate = 8 / source['duration']
        result = subprocess.run([
            'ffmpeg', '-y', '-v', 'error', '-i', str(args.input), '-an',
            '-vf', f'fps={sample_rate:.9f},scale=320:-2,tile=4x2:padding=4:margin=4',
            '-frames:v', '1', str(sheet),
        ], capture_output=True, text=True, timeout=90)
        if result.returncode or not sheet.is_file():
            raise ValueError('Contact-sheet extraction failed: ' + result.stderr[-1000:])
    report = {
        'input': str(args.input.resolve()), 'source': source,
        'contact_sheet': str(sheet.resolve()) if sheet is not None else None,
        'metadata_only': args.metadata_only, 'declared_segmentation_mode': args.segmentation_mode,
        'models_used': False, 'mask_checks': mask_checks, 'blocking_reasons': blocking,
        'render_gate': 'blocked' if blocking else 'input_metadata_ready',
        'reference_replication_verified': False,
        'notes': [
            'Metadata/geometry checks are not semantic foreground segmentation.',
            'Inspect relevant frames/motion only for uncertain regions or explicit visual debugging; metadata-only needs no contact sheet.',
            'No mask: do not substitute a luma threshold or fixed screen band.',
        ],
    }
    report_path = args.output_dir / 'preflight.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(report_path.resolve()), **report}, ensure_ascii=False))
    return 2 if blocking else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, subprocess.SubprocessError, OSError) as exc:
        print(json.dumps({'error': str(exc), 'models_used': False}), file=sys.stderr)
        sys.exit(1)
