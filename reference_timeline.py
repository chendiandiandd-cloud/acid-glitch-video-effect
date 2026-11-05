"""Reference-clock lookup only; not a renderer. No media IO or model calls.

Intervals are left-closed/right-open, including the 5.25 s endpoint.
Use Fraction/Decimal or decimal strings for exact timestamps. Floats within
four ULPs of a reference boundary are snapped to that boundary (only for
lookup); source_pts is always returned unchanged. No cut/shot clock exists.
"""
import argparse
import json
import math
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

NATURAL = [0, 2, 14, 17, 34, 38, 41]
RETURNS = NATURAL[1:]
PARTIAL = [6, 22, 25, 29]
# strong is unconfirmed whole-frame natural return, NOT a rendering preset.
STATES = {'natural', 'strong', 'partial'}


def _seconds(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal, Fraction)):
        raise ValueError('PTS must be a finite number of seconds')
    try:
        result = Fraction(str(value)) if isinstance(value, float) else Fraction(value)
    except (ValueError, TypeError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError('PTS must be a finite number of seconds') from exc
    return result


def validate_profile(profile):
    """Validate this observed 42-frame reference, not arbitrary renderer presets."""
    if not isinstance(profile, dict):
        raise ValueError('profile must be an object')
    for key, expected in [('schema_version', 1), ('reference_fps', 8), ('frame_count', 42)]:
        if type(profile.get(key)) is not int or profile[key] != expected:
            raise ValueError(f'{key} must be {expected}')
    if _seconds(profile.get('duration_seconds')) != Fraction(21, 4):
        raise ValueError('duration_seconds must equal frame_count/reference_fps')
    states = profile.get('frame_states')
    if not isinstance(states, list) or len(states) != 42:
        raise ValueError('frame_states must contain 42 entries')
    if any(not isinstance(s, str) or s not in STATES for s in states):
        raise ValueError('unknown frame state')
    for key, expected in [('natural_color_frames', NATURAL), ('return_event_frames', RETURNS)]:
        frames = profile.get(key)
        if not isinstance(frames, list) or any(type(f) is not int for f in frames) or frames != expected:
            raise ValueError(f'{key} does not match observed events')
    if [i for i, state in enumerate(states) if state == 'natural'] != NATURAL:
        raise ValueError('natural events must correspond exactly to natural states')
    if [i for i, state in enumerate(states) if state == 'partial'] != PARTIAL:
        raise ValueError('partial membership must match confirmed frames')
    branch = profile.get('natural_branch')
    if not isinstance(branch, dict) or branch.get('scope') != 'whole_frame':
        raise ValueError('natural gate must be whole_frame, never a person mask')
    if branch.get('source_time') != 'current_input_pts':
        raise ValueError('natural branch must use current_input_pts')
    gain = branch.get('strong_style_gain')
    if isinstance(gain, bool) or not isinstance(gain, (int, float)) or gain != 0:
        raise ValueError('natural strong_style_gain must be zero')
    if branch.get('preserve_residual_distress') is not True:
        raise ValueError('natural residual distress must remain caller-calibrated')
    return profile


def load_profile(path):
    with Path(path).open(encoding='utf-8') as stream:
        return validate_profile(json.load(stream))


def select_reference(profile, source_pts, *, extension):
    """Select by continuous input PTS; extension must be explicitly supplied.

    repeat is inferred adaptation only beyond the observed block. It maps the
    effect clock, not source playback. Gain 1 outside natural is a routing
    weight, not a calibrated style intensity. Baseline F0 is not a return event,
    even at the start of an inferred repeat cycle.
    """
    validate_profile(profile)
    if extension not in ('repeat', 'truncate'):
        raise ValueError('extension must be repeat or truncate')
    pts = _seconds(source_pts)
    if pts < 0:
        raise ValueError('PTS must be nonnegative')
    ticks = pts * 8
    if isinstance(source_pts, float):
        nearest = round(ticks)
        boundary = nearest / 8
        tolerance = 4 * max(math.ulp(source_pts), math.ulp(boundary))
        if abs(pts - Fraction(boundary)) <= Fraction(tolerance):
            ticks = Fraction(nearest)
    absolute_frame = ticks.numerator // ticks.denominator
    if extension == 'truncate' and absolute_frame >= 42:
        raise ValueError('PTS is outside reference interval [0, 5.25)')
    cycle, frame = divmod(absolute_frame, 42)
    state = profile['frame_states'][frame]
    natural = state == 'natural'
    return {
        'state': state, 'natural_gate': natural, 'natural_gate_scope': 'whole_frame',
        'strong_style_gain': 0.0 if natural else 1.0,
        'reference_frame': frame, 'cycle_index': cycle, 'source_pts': source_pts,
        'extension_policy': extension, 'extension_is_inferred': cycle > 0,
        'is_baseline': frame == 0, 'is_return_event': frame in RETURNS,
        'natural_event': 'baseline' if frame == 0 else ('return_event' if natural else None),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, help='reference profile JSON path')
    parser.add_argument('--pts', required=True, help='current input PTS in seconds (decimal)')
    parser.add_argument('--extension', required=True, choices=('repeat', 'truncate'))
    args = parser.parse_args(argv)
    try:
        # Preserve the supplied decimal exactly in JSON, as a decimal string.
        pts = Decimal(args.pts)
        result = select_reference(load_profile(args.profile), pts, extension=args.extension)
    except (ValueError, OSError, ArithmeticError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, default=str, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
