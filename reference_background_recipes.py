"""Reference-direction background recipes, NumPy only; NOT semantic segmentation.
Original implementation 2026-11-05. Rotating-domain idea adapted from workspace
scripts/acid_matte_ink_algorithms.py (2026-11-05 extraction); redesigned broad
branched bands and structure-derived local scan. No video/cache/model paths.
All colors use BGR. Thresholds/scales are calibration starts, not measurements.
"""
import numpy as np
from background_print_states import background_state, STATES


def _mask(a, shape, name):
    if not isinstance(a, np.ndarray) or a.shape != shape or a.dtype.kind not in 'fibu':
        raise ValueError(name + ' must be a numeric HxW mask')
    if not np.isfinite(a).all() or np.any((a < 0) | (a > 1)):
        raise ValueError(name + ' must be finite in [0,1]')
    return a


def _tick(tick):
    if isinstance(tick, (bool, np.bool_)) or not isinstance(tick, (int, np.integer)) or not 0 <= tick <= 1000000:
        raise ValueError('tick must be integer in [0,1000000]')
    return int(tick)


def pigment_fold(xx, yy, tick):
    """Four opaque inks, broad unequal bands, spatial bifurcation + local curls.
    No HSV, glow, contour-distance lines or sampled subject colors.
    """
    tick = _tick(tick)
    if not isinstance(xx, np.ndarray) or not isinstance(yy, np.ndarray) or xx.shape != yy.shape or xx.ndim != 2 or min(xx.shape) < 1:
        raise ValueError('grid must be matching nonempty HxW')
    for a in (xx, yy):
        if a.dtype.kind not in 'fiu' or not np.isfinite(a).all():
            raise ValueError('grid must be numeric finite')
    h, w = xx.shape
    if np.any((xx < 0) | (xx > w-1)) or np.any((yy < 0) | (yy > h-1)):
        raise ValueError('grid outside image')
    t = tick / 8
    qx = xx.astype(np.float32) / w * 2 - 1
    qy = yy.astype(np.float32) / h * 2 - 1
    # Change orientation between phrases without a periodic color spectrum.
    angle = (.38, -.64, .82)[(tick // 4) % 3]
    qx, qy = qx*np.cos(angle)-qy*np.sin(angle), qx*np.sin(angle)+qy*np.cos(angle)
    for i, (cx, cy, radius, strength) in enumerate(((-.54,-.35,.84,4.6),(.53,-.04,.70,-4.9),(-.10,.63,.79,3.9))):
        cx += .13*np.sin(t*.71+i); cy += .11*np.cos(t*.57+i)
        dx, dy = qx-cx, qy-cy
        a = strength*np.exp(-(dx*dx+dy*dy)/radius**2)
        qx, qy = cx+dx*np.cos(a)-dy*np.sin(a), cy+dx*np.sin(a)+dy*np.cos(a)
    f = qy + .30*np.sin(qx*2.7 + t*.45) + .12*np.sin(qx*4.2-qy*1.3)
    # Wide main band splits into two branches, recombines after local domain curls.
    branch = .29*np.maximum(0, np.sin(qx*2.6+t*.32))
    distance = np.minimum(np.abs(f-branch), np.abs(f+branch))
    idx = np.full((h,w), 1, np.uint8)
    idx[f < -.53] = 2
    idx[(distance < .22) & (qx > -.78)] = 3
    idx[(f > .65) | ((f < -.25) & (f > -.43))] = 0
    palettes = (((4,3,2),(191,48,230),(51,190,246),(93,222,54)),
                ((4,3,2),(229,58,182),(74,211,247),(192,209,38)),
                ((4,3,2),(193,50,234),(223,172,43),(78,221,116)))
    return np.asarray(palettes[(tick//4)%3], np.uint8)[idx]


class ReferenceBackgroundRecipes:
    """Reusable array builder. No PTS schedule, inference, encoder or fixed seam.
    alpha is used ONLY to forbid source sampling from subject/soft edge.
    Compose result with matte_background_composite afterwards; gate is last.
    full_background is explicit artistic range, never a building/sky claim.
    """
    def __init__(self, xx, yy):
        pigment_fold(xx, yy, 0)  # fail-closed grid validation
        self.xx, self.yy = xx.copy(), yy.copy()
        self.h, self.w = xx.shape
        pitch = max(2., min(xx.shape)/180.)
        u = (xx+yy)/1.414/pitch % 1 - .5
        v = (xx-yy)/1.414/pitch % 1 - .5
        self.halftone = np.clip((u*u+v*v)*np.pi, 0, 1).astype(np.float32)
        self.calls = {}; self.rectangles = []; self.tick = -1

    def build(self, bgr, alpha, tick, state, palette=None, *, policy='full_background', allowed_mask=None):
        tick = _tick(tick)
        if not isinstance(bgr, np.ndarray) or bgr.dtype != np.uint8 or bgr.shape != (self.h,self.w,3):
            raise ValueError('source must be matching uint8 BGR')
        _mask(alpha, (self.h,self.w), 'alpha')
        if not isinstance(state, str) or state not in STATES:
            raise ValueError('unknown state')
        if palette is not None:
            raise ValueError('custom palette unsupported: use documented BGR inks')
        if policy == 'full_background' and allowed_mask is None:
            allowed = np.ones(alpha.shape, np.float32)
        elif policy == 'explicit' and allowed_mask is not None:
            allowed = _mask(allowed_mask, alpha.shape, 'allowed_mask').astype(np.float32)
        else:
            raise ValueError('explicit requires mask; full_background forbids mask; unknown policy rejected')
        if tick != self.tick:
            self.fluid = pigment_fold(self.xx, self.yy, tick)
            self.light = (12,218,255) if tick%3 else (8,179,255)
            rng = np.random.default_rng(9210+tick)
            self.flecks = rng.random(alpha.shape) > .993
            self.rectangles = []
            for _ in range(15):
                x = int(rng.integers(0,max(1,self.w-1))); y = int(rng.integers(0,self.h))
                rw = max(2,int(rng.integers(70,720)*self.w/1280))
                rh = max(1,int(rng.integers(5,70)*self.h/720))
                self.rectangles.append((x,y,min(self.w,x+rw),min(self.h,y+rh),int(rng.integers(-160,160)*self.w/1280),bool(rng.random()<.4)))
            self.tick = tick
        kw = dict(color_order='BGR',dark_color=(2,3,4),light_color=self.light,
                  threshold=.48,transition_width=.06,halftone=self.halftone)
        duo = background_state(bgr,'duotone',**kw)
        fill = background_state(bgr,'ink_colorfield',color_field=self.fluid,**kw)
        if state == 'horizontal_glitch':
            glitch = fill.copy()
            safe = (alpha == 0) & (allowed == 1)
            # Stretch current printed scene structure, not uniform generated stripes.
            for x,y,x1,y1,shift,cut in self.rectangles:
                if x1 <= x: continue
                stretch = 5 if cut else 3
                sx = x + shift + ((np.arange(x,x1)-x)//stretch)*stretch//3
                valid_x = (sx >= 0) & (sx < self.w)
                sx_safe = np.clip(sx,0,self.w-1)
                valid = safe[y:y1,x:x1] & safe[y:y1,sx_safe] & valid_x[None,:]
                sampled = fill[y:y1,sx_safe].copy()
                if cut:
                    # Local interrupted scan cuts, unequal lengths; never full width.
                    sampled[::max(2,(y1-y)//3+1)] = (2,3,4)
                block = glitch[y:y1,x:x1]
                block[valid] = sampled[valid]
            result = background_state(bgr,state,glitch_frame=glitch,**kw)
        elif state == 'liquid_replace':
            result = background_state(bgr,state,liquid_frame=self.fluid,**kw)
        elif state == 'ink_colorfield': result = fill
        elif state == 'duotone': result = duo
        else: result = background_state(bgr,'source',**kw)
        if state != 'source':
            # Sparse crisp missing ink; no white fog, no random RGB spectrum.
            bright = np.any(result > 8, axis=2)
            result[self.flecks & bright] = (2,3,4)
        if policy == 'explicit':
            result = np.rint(result*allowed[...,None]+bgr*(1-allowed[...,None])).astype(np.uint8)
        self.calls[state] = self.calls.get(state,0)+1
        return result, allowed.copy()


InkBackground = ReferenceBackgroundRecipes
