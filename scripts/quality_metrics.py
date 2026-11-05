"""Array-only diagnostics, not a renderer or aesthetic similarity score.
Original implementation for this skill. Requires NumPy; never writes media.
"""
import hashlib
import json
import math
import numpy as np


def _mask(value):
    array = np.asarray(value, dtype=np.float32)
    if array.ndim != 2 or not array.size:
        raise ValueError('Expected nonempty HxW mask')
    if not np.isfinite(array).all() or np.any((array < 0) | (array > 1)):
        raise ValueError('Masks must be finite and normalized to [0, 1]')
    return array


def merge_person_masks(masks, shape=None):
    """Union ALL instance probabilities. Empty detections are not proof of no people."""
    arrays = [_mask(item) for item in masks]
    if not arrays:
        if shape is None or len(shape) != 2 or any(int(d) != d or d <= 0 for d in shape):
            raise ValueError('Empty instances require explicit positive HxW shape')
        return np.zeros(tuple(map(int, shape)), dtype=np.float32)
    target = arrays[0].shape
    if any(item.shape != target for item in arrays) or (shape is not None and tuple(shape) != target):
        raise ValueError('Instance geometry mismatch')
    return np.maximum.reduce(arrays)


def region_metrics(effect_mask, allowed_mask, protected_mask):
    """Weighted legal coverage and leakage; None when denominator region is empty."""
    effect, allowed, protected = map(_mask, (effect_mask, allowed_mask, protected_mask))
    if not (effect.shape == allowed.shape == protected.shape):
        raise ValueError('Region geometry mismatch')
    legal = allowed * (1 - protected)
    forbidden = 1 - legal
    def ratio(numerator, denominator):
        total = float(denominator.sum(dtype=np.float64))
        return None if total == 0 else float(numerator.sum(dtype=np.float64)) / total
    return {
        'legal_region_coverage': ratio(effect * legal, legal),
        'protected_region_leakage': ratio(effect * protected, protected),
        'forbidden_region_leakage': ratio(effect * forbidden, forbidden),
        'effect_outside_legal_fraction': ratio(effect * forbidden, effect),
    }


def wear_region_contrast(wear_mask, region_mask, block_size=16):
    """Compare block means, not high-frequency noise variance. No automatic pass score."""
    wear, region = map(_mask, (wear_mask, region_mask))
    if wear.shape != region.shape:
        raise ValueError('Wear/region geometry mismatch')
    if not isinstance(block_size, int) or block_size < 1:
        raise ValueError('block_size must be a positive integer')
    means = []
    for y in range(0, wear.shape[0], block_size):
        for x in range(0, wear.shape[1], block_size):
            patch = wear[y:y+block_size, x:x+block_size]
            weights = region[y:y+block_size, x:x+block_size]
            total = float(weights.sum())
            if total > 0:
                means.append(float((patch * weights).sum()) / total)
    if not means:
        return {'block_count': 0, 'p10': None, 'p90': None, 'p90_minus_p10': None}
    lo, hi = np.percentile(means, [10, 90])
    return {'block_count': len(means), 'p10': float(lo), 'p90': float(hi),
            'p90_minus_p10': float(hi - lo)}


def mask_cache_key(source_fingerprint, model_version, segmentation_params, geometry, fps, person_policy='all'):
    """Caller computes source content fingerprint; visual parameters intentionally absent."""
    if not source_fingerprint or not model_version or person_policy != 'all':
        raise ValueError('Source fingerprint, model version and all-person policy required')
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('fps must be positive and finite')
    payload = {'source': source_fingerprint, 'model': model_version,
               'segmentation': segmentation_params, 'geometry': geometry,
               'fps': fps, 'person_policy': person_policy}
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def estimate_runtime(duration, output_fps, segmentation_hz, segmentation_ms,
                     composite_ms, encode_ms, cold_start_seconds=0, cached_mask=False):
    """Sequential cost estimate; measured inputs required, not a wall-time guarantee."""
    values = (duration, output_fps, segmentation_hz, segmentation_ms,
              composite_ms, encode_ms, cold_start_seconds)
    if any(not math.isfinite(v) or v < 0 for v in values) or duration == 0 or output_fps == 0:
        raise ValueError('Positive duration/fps and finite nonnegative costs required')
    frames = math.ceil(duration * output_fps)
    mask_frames = 0 if cached_mask else math.ceil(duration * segmentation_hz)
    parts = {'cold_start_seconds': cold_start_seconds,
             'segmentation_seconds': mask_frames * segmentation_ms / 1000,
             'composite_seconds': frames * composite_ms / 1000,
             'encode_seconds': frames * encode_ms / 1000}
    return {**parts, 'estimated_total_seconds': sum(parts.values()),
            'output_frames': frames, 'segmentation_frames': mask_frames}
