"""Explicit editable-background policies and mask-only horizontal-cut diagnostics.

No semantic segmentation, clock, feathering, or media rendering is performed.
A full-background policy is an explicit artistic choice, not a semantic claim.
"""
import numpy as np


def _mask(value, name):
    array = np.asarray(value)
    if array.ndim != 2 or not all(array.shape):
        raise ValueError(f'{name} must be a nonempty H x W mask')
    if array.dtype.kind not in 'buif':
        raise ValueError(f'{name} must be real numeric or boolean')
    if not np.all(np.isfinite(array)) or np.any(array < 0) or np.any(array > 1):
        raise ValueError(f'{name} must contain finite values in [0, 1]')
    return array


def editable_background_region(protected_mask, *, policy, allowed_mask=None):
    """Return float32 E with every nonzero protected pixel excluded.

    full_background: deliberately process all unprotected background; no height
    cutoff and no guessed near-ground boundary. explicit: use a caller-provided
    content-derived allowed mask, retaining its soft values. No automatic fallback
    or hidden smoothing is applied. Existing source restoration is a separate state.
    """
    protected = _mask(protected_mask, 'protected_mask')
    if policy == 'full_background':
        if allowed_mask is not None:
            raise ValueError('full_background does not accept allowed_mask')
        region = np.ones(protected.shape, dtype=np.float32)
    elif policy == 'explicit':
        if allowed_mask is None:
            raise ValueError('explicit policy requires allowed_mask')
        allowed = _mask(allowed_mask, 'allowed_mask')
        if allowed.shape != protected.shape:
            raise ValueError('mask shapes must match')
        region = allowed.astype(np.float32, copy=True)
    else:
        raise ValueError('policy must be full_background or explicit')
    region[protected > 0] = 0
    return region


def horizontal_cut_rows(region, *, min_span=.8, min_step=.75):
    """Return destination row indices for unusually long hard mask steps.

    Only a diagnostic: real horizontal scene boundaries can also trigger it;
    fault status needs region intent/content checks. It is NOT a test on image
    pixels and must not reject intentionally horizontal glitch imagery.
    """
    mask = _mask(region, 'region')
    for name, value in (('min_span', min_span), ('min_step', min_step)):
        if isinstance(value, (bool, np.bool_)) or not np.isscalar(value):
            raise ValueError(f'{name} must be a finite scalar in (0, 1]')
        try:
            valid = np.isfinite(value) and 0 < value <= 1
        except TypeError as exc:
            raise ValueError(f'{name} must be a finite scalar in (0, 1]') from exc
        if not valid:
            raise ValueError(f'{name} must be a finite scalar in (0, 1]')
    # Convert before subtraction to avoid uint8 underflow/boolean subtraction.
    delta = np.abs(np.diff(mask.astype(np.float64), axis=0))
    spans = np.mean(delta >= min_step, axis=1)
    return tuple(int(row + 1) for row in np.flatnonzero(spans >= min_span))
