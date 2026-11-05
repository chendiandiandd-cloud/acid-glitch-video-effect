"""NumPy-only background primitives; no media IO, models, renderer or clock."""
import numpy as np


def _frame(value, name, shape=None):
    if not isinstance(value, np.ndarray) or value.dtype != np.uint8:
        raise TypeError(f'{name} must be a uint8 ndarray')
    if value.ndim != 3 or value.shape[2] != 3 or min(value.shape[:2]) < 1:
        raise ValueError(f'{name} must have nonempty HxWx3 shape')
    if shape is not None and value.shape != shape:
        raise ValueError(f'{name} shape must match source frame')
    return value


def _float_array(value, name, shape, mask=False):
    if not isinstance(value, np.ndarray) or value.dtype.kind != 'f':
        raise TypeError(f'{name} must be a floating ndarray')
    if value.shape != shape:
        raise ValueError(f'{name} shape must be {shape}')
    if not np.isfinite(value).all():
        raise ValueError(f'{name} must be finite')
    if mask and ((value < 0).any() or (value > 1).any()):
        raise ValueError(f'{name} must be in [0, 1]')
    # Computation uses float64; refuse values not representable in that domain.
    if (np.abs(value) > np.finfo(np.float64).max).any():
        raise ValueError(f'{name} exceeds float64 range')
    return value.astype(np.float64)


def _regions(frame, editable_mask, protected_mask):
    shape = frame.shape[:2]
    return (_float_array(editable_mask, 'editable_mask', shape, True),
            _float_array(protected_mask, 'protected_mask', shape, True))


def protected_background_composite(approved_frame, changed_background,
                                   editable_mask, protected_mask, *,
                                   natural_gate=False, natural_frame=None):
    """Blend uint8 HxWx3 frames, independently of RGB/BGR channel convention.

    Floating HxW masks must be finite in [0,1]. E weights background alpha;
    any P>0 (including soft edges), and E==0, retain approved bytes exactly.
    Blend rounds to nearest integer with ties to even (np.rint). A boolean
    whole-frame natural_gate instead returns a copy of required natural_frame,
    ignoring E/P for selection and allowing subject recoloring. All supplied
    arrays are validated even on the natural branch; none are mutated.
    Caller supplies branches from the SAME current source PTS: this primitive
    accepts no clock, does not replay frames and cannot alter source PTS.
    This is not a renderer or semantic mask detector.
    """
    approved = _frame(approved_frame, 'approved_frame')
    changed = _frame(changed_background, 'changed_background', approved.shape)
    e, p = _regions(approved, editable_mask, protected_mask)
    if not isinstance(natural_gate, (bool, np.bool_)):
        raise TypeError('natural_gate must be boolean')
    if natural_frame is not None:
        _frame(natural_frame, 'natural_frame', approved.shape)
    if natural_gate:
        if natural_frame is None:
            raise ValueError('natural_gate requires natural_frame')
        return natural_frame.copy()
    weight = np.where(p > 0, 0, e)[..., None]
    result = np.rint(approved.astype(np.float64) * (1 - weight)
                     + changed.astype(np.float64) * weight).astype(np.uint8)
    return result


def bounded_structure_warp(source_frame, displacement_px, editable_mask,
                           protected_mask, max_displacement_px):
    """Backward nearest-neighbour remap of the CURRENT uint8 HxWx3 source.

    Floating displacement is HxWx2 [dx,dy] in source pixels: output (x,y)
    samples source (x+dx,y+dy). Clamp vector LENGTH to finite nonnegative
    max_displacement_px, then weight displacement once by floating E in [0,1].
    No second alpha blend. Nearest ties use np.rint (ties to even).
    E==0 and any P>0 preserve original bytes. Continuous sample coordinates
    outside [0,W-1] x [0,H-1], or rounded samples with E==0 / P>0, fall back
    to the original pixel; no wraparound or dragging protected subject colors.
    Inputs are not mutated. No semantic detection, PTS handling, generated
    stripes or full renderer; nearest sampling is NOT a final high-quality
    reference reconstruction. Caller must supply same-current-PTS content.
    """
    source = _frame(source_frame, 'source_frame')
    e, p = _regions(source, editable_mask, protected_mask)
    d = _float_array(displacement_px, 'displacement_px', source.shape[:2] + (2,))
    if (isinstance(max_displacement_px, (bool, np.bool_))
            or not isinstance(max_displacement_px, (int, float, np.integer, np.floating))):
        raise TypeError('max_displacement_px must be a real scalar')
    if not np.isfinite(max_displacement_px) or max_displacement_px < 0:
        raise ValueError('max_displacement_px must be finite and nonnegative')
    if max_displacement_px > np.finfo(np.float64).max:
        raise ValueError('max_displacement_px exceeds float64 range')
    maximum = float(max_displacement_px)
    # Normalize via largest component so even enormous finite vectors are safe.
    scale = np.max(np.abs(d), axis=2)
    unit = np.divide(d, scale[..., None], out=np.zeros_like(d),
                     where=scale[..., None] > 0)
    length = np.hypot(unit[..., 0], unit[..., 1])
    allowed_scale = np.divide(maximum, length, out=np.zeros_like(length),
                              where=length > 0)
    bounded = unit * np.minimum(scale, allowed_scale)[..., None]
    bounded *= e[..., None]
    y, x = np.indices(source.shape[:2])
    sx, sy = x + bounded[..., 0], y + bounded[..., 1]
    h, w = source.shape[:2]
    inside = (sx >= 0) & (sx <= w - 1) & (sy >= 0) & (sy <= h - 1)
    ix = np.rint(np.clip(sx, 0, w - 1)).astype(np.intp)
    iy = np.rint(np.clip(sy, 0, h - 1)).astype(np.intp)
    legal = inside & (e > 0) & (p == 0) & (e[iy, ix] > 0) & (p[iy, ix] == 0)
    result = source.copy()
    result[legal] = source[iy[legal], ix[legal]]
    return result
