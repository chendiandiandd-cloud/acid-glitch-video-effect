"""NumPy-only background state selector: no IO, clock, masks or renderer."""
import numpy as np


STATES = ('source', 'duotone', 'ink_colorfield', 'liquid_replace',
          'horizontal_glitch')


def _frame(value, name, shape=None):
    if not isinstance(value, np.ndarray) or value.dtype != np.uint8:
        raise TypeError(f'{name} must be a uint8 ndarray')
    if value.ndim != 3 or value.shape[2] != 3 or min(value.shape[:2]) < 1:
        raise ValueError(f'{name} must be nonempty HxWx3')
    if shape is not None and value.shape != shape:
        raise ValueError(f'{name} must match source shape')
    return value


def _color(value, name):
    # Integer tuples are accepted as explicit 0..255 colors, never normalized.
    a = np.asarray(value)
    if a.dtype.kind not in 'iu' or a.dtype.kind == 'b':
        raise TypeError(f'{name} must contain integers in uint8 color domain')
    if a.shape != (3,):
        raise ValueError(f'{name} must have three channels')
    if (a < 0).any() or (a > 255).any():
        raise ValueError(f'{name} must be in [0,255]')
    return a.astype(np.uint8)


def _scalar(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(
            value, (int, float, np.integer, np.floating)):
        raise TypeError(f'{name} must be a real scalar')
    if not np.isfinite(value) or abs(value) > np.finfo(np.float64).max:
        raise ValueError(f'{name} must be finite and float64 representable')
    return float(value)


def background_state(source_frame, state, *, color_order, dark_color,
                     light_color, threshold=.5, transition_width=.08,
                     halftone=None, color_field=None, liquid_frame=None,
                     glitch_frame=None):
    """Return a new uint8 HxWx3 background, never mutate supplied arrays.

    color_order is explicitly RGB or BGR; all frames and colors use that order.
    Colors are integer triples in 0..255, not normalized floats. No defaults
    imply reference-measured colors. Luma is Rec.709 weighted encoded channels
    (0.2126 R + 0.7152 G + 0.0722 B)/255, not linear-light luminance.
    threshold is in (0,1); transition_width is the FULL width centered on it,
    nonnegative with both endpoints in [0,1]. Without halftone use luma >=
    threshold. With floating HxW halftone in [0,1], the open transition window
    uses light iff normalized position > halftone; endpoints stay solid.
    Thus printing never retains photographic gradients. ink_colorfield uses
    exactly the same binary ink mask, substituting caller color_field only
    for light pixels. Replacement states require their corresponding frame
    and copy it wholesale, without source blending or generated displacement.

    All supplied parameters (even unused optional arrays) are validated.
    This selector has no PTS, timing, building recognition or semantic regions.
    Caller generates the background first, then protects approved subject via
    protected_background_composite; its whole-frame natural_gate is last and
    has priority. This module intentionally does not import that compositor.
    """
    source = _frame(source_frame, 'source_frame')
    if not isinstance(state, str) or state not in STATES:
        raise ValueError('unknown background state')
    if not isinstance(color_order, str) or color_order not in ('RGB', 'BGR'):
        raise ValueError('color_order must explicitly be RGB or BGR')
    dark = _color(dark_color, 'dark_color')
    light = _color(light_color, 'light_color')
    t = _scalar(threshold, 'threshold')
    width = _scalar(transition_width, 'transition_width')
    if not 0 < t < 1:
        raise ValueError('threshold must be in (0,1)')
    if width < 0 or t - width / 2 < 0 or t + width / 2 > 1:
        raise ValueError('transition window must lie in [0,1]')
    if halftone is not None:
        if not isinstance(halftone, np.ndarray) or halftone.dtype.kind != 'f':
            raise TypeError('halftone must be a floating ndarray')
        if halftone.shape != source.shape[:2]:
            raise ValueError('halftone must be HxW')
        if (not np.isfinite(halftone).all() or (halftone < 0).any()
                or (halftone > 1).any()):
            raise ValueError('halftone must be finite in [0,1]')
    for value, name in ((color_field, 'color_field'),
                        (liquid_frame, 'liquid_frame'),
                        (glitch_frame, 'glitch_frame')):
        if value is not None:
            _frame(value, name, source.shape)
    if state == 'source':
        return source.copy()
    if state in ('liquid_replace', 'horizontal_glitch'):
        frame = liquid_frame if state == 'liquid_replace' else glitch_frame
        if frame is None:
            raise ValueError(f'{state} requires its explicit replacement frame')
        return frame.copy()
    if state == 'ink_colorfield' and color_field is None:
        raise ValueError('ink_colorfield requires color_field')
    weights = np.array([.2126, .7152, .0722])
    if color_order == 'BGR':
        weights = weights[::-1]
    luma = (source.astype(np.float64) @ weights) / 255
    bright = luma >= t
    if halftone is not None and width > 0:
        low, high = t - width / 2, t + width / 2
        # Stabilize endpoint equality against encoded-luma float roundoff.
        eps = 4 * np.finfo(np.float64).eps
        at_low = np.abs(luma - low) <= eps
        at_high = np.abs(luma - high) <= eps
        inside = (luma > low) & (luma < high) & ~at_low & ~at_high
        bright = np.where(inside, (luma - low) / width > halftone,
                          (luma >= high) | at_high)
        bright = np.where(at_low, False, bright)
    bright_color = color_field if state == 'ink_colorfield' else light
    return np.where(bright[..., None], bright_color, dark).astype(np.uint8)
