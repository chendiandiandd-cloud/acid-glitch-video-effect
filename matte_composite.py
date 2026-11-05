"""Composite corrected subject mattes without keeping rejected old-background rims.

No segmentation or rendering: caller provides same-current-PTS layers and matte.
The approved frame is used ONLY for a reliable, fully opaque subject core.
"""
import numpy as np


def _frame(value, name, shape=None):
    frame = np.asarray(value)
    if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3 or not all(frame.shape):
        raise ValueError(f'{name} must be nonempty uint8 H x W x 3')
    if shape is not None and frame.shape != shape:
        raise ValueError(f'{name} shape mismatch')
    return frame


def _mask(value, name, shape):
    mask = np.asarray(value)
    if mask.shape != shape or mask.dtype.kind not in 'buif':
        raise ValueError(f'{name} must be real numeric H x W, matching the frames')
    if not np.all(np.isfinite(mask)) or np.any(mask < 0) or np.any(mask > 1):
        raise ValueError(f'{name} must be finite in [0, 1]')
    return mask


def matte_background_composite(approved_frame, person_frame, changed_background,
                               alpha, *, core_mask, natural_gate=False,
                               natural_frame=None):
    """Corrected branch: pure subject ink at edges, never approved background.

    Core requires alpha==1; any nonzero core support preserves approved bytes.
    Outside core uses alpha person + (1-alpha) new background. Subject alpha
    must come from a separate, checked matte; this function cannot fix detection.
    Natural gate bypasses all layers using supplied complete natural branch.
    No input is changed. uint8 blend rounds with np.rint (ties to even).
    """
    approved = _frame(approved_frame, 'approved_frame')
    person = _frame(person_frame, 'person_frame', approved.shape)
    background = _frame(changed_background, 'changed_background', approved.shape)
    a = _mask(alpha, 'alpha', approved.shape[:2])
    core = _mask(core_mask, 'core_mask', approved.shape[:2]) > 0
    if np.any(core & (a != 1)):
        raise ValueError('core_mask may only protect fully opaque alpha==1 pixels')
    if not isinstance(natural_gate, (bool, np.bool_)):
        raise ValueError('natural_gate must be boolean')
    if natural_frame is not None:
        natural = _frame(natural_frame, 'natural_frame', approved.shape)
    if natural_gate:
        if natural_frame is None:
            raise ValueError('natural gate requires current complete natural_frame')
        return natural.copy()
    weight = a.astype(np.float64)[..., None]
    result = np.rint(person.astype(np.float64) * weight
                     + background.astype(np.float64) * (1-weight)).astype(np.uint8)
    result[core] = approved[core]
    return result
