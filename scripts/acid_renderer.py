"""Portable renderer, migrated 2026-11-06 from workspace
scripts/render_acid_print_states_4s.py and ink_print from render_acid_flash_4s.py.
Only the latest matte/print render graph is retained, not old experimental CLIs.
No generated media, no semantic models beyond optional existing person ONNX.
"""
import time
from collections import Counter
from pathlib import Path
import cv2
import numpy as np
from reference_timeline import load_profile, select_reference
from reference_background_recipes import ReferenceBackgroundRecipes
from matte_composite import matte_background_composite
from acid_matte_ink_algorithms import refine_alpha, reliable_flow_sample, blend_anchor_samples

PROFILE=load_profile(Path(__file__).resolve().parents[1]/'references/reference-profile.json')


def choreography(tick):
    if tick in (6,22,25,29):return 'source'
    if tick in (1,3,4,10,16,23,31):return 'duotone'
    if tick in (5,11,12,20,26,27):return 'ink_colorfield'
    if tick in (7,9,15,19,21,30):return 'horizontal_glitch'
    return 'liquid_replace'


def ink_print(gray, radial):
    local=np.clip(gray+1.0*(gray-cv2.GaussianBlur(gray,(0,0),1.2)),0,1)
    black_fraction=np.clip((.40-local)/.16,0,1)
    dots=radial<black_fraction/np.pi
    black=(local<=.24)|((local<.40)&dots)
    return np.where(black[...,None],np.array([.008,.009,.012],np.float32),
                    np.array([.01,.98,1.],np.float32))


class FrameEffects:
    def __init__(self,width,height,stats,optimized=True):
        self.width=width;self.height=height;self.stats=stats;self.optimized=optimized
        self.yy,self.xx=np.mgrid[0:height,0:width].astype(np.float32)
        u=(self.xx+self.yy)/1.414;v=(self.xx-self.yy)/1.414
        self.radial=(u/5%1-.5)**2+(v/5%1-.5)**2
        self.scratches=np.zeros((height,width),np.float32);self.flecks=np.zeros_like(self.scratches)
        self.rng=np.random.default_rng(5081);self.previous=None;self.tick_prev=-1;self.confidence=None
        self.bg=ReferenceBackgroundRecipes(self.xx,self.yy);self.counts=Counter()

    def mask(self,anchor):
        return cv2.resize(anchor[2].astype(np.float32)/255,(self.width,self.height))

    def apply(self,item,left,right):
        begin=time.perf_counter()
        i,t,bgr,gray8,small,cut,is_anchor=item
        tick=int(t*8);new_tick=tick!=self.tick_prev
        if cut:
            self.previous=None;self.confidence=None
            self.scratches.fill(0);self.flecks.fill(0)
        if is_anchor:self.confidence=self.mask(left)
        if self.previous is not None:
            flow=cv2.calcOpticalFlowFarneback(small,self.previous,None,.5,2,13,2,5,1.1,0)
            full=cv2.resize(flow,(self.width,self.height))
            full[...,0]*=self.width/small.shape[1];full[...,1]*=self.height/small.shape[0]
            mx,my=self.xx+full[...,0],self.yy+full[...,1]
            if not is_anchor:self.confidence=cv2.remap(self.confidence,mx,my,cv2.INTER_LINEAR)
            self.scratches=cv2.remap(self.scratches,mx,my,cv2.INTER_LINEAR)
            self.flecks=cv2.remap(self.flecks,mx,my,cv2.INTER_NEAREST)
            self.stats['wear_flow_calls']+=1
        self.previous=small
        if new_tick:
            self.tick_prev=tick;self.scratches*=.87;self.flecks*=.62
            for _ in range(36):
                px=int(self.rng.integers(self.width));py=int(self.rng.integers(self.height))
                length=int(self.rng.integers(20,180))
                for offset in range(0,length,11):
                    if self.rng.random()>.35:
                        cv2.line(self.scratches,(px,min(self.height-1,py+offset)),
                            (px+1,min(self.height-1,py+offset+7)),float(self.rng.uniform(.2,.55)),1)
            dots=self.rng.random((self.height,self.width))
            fresh=(dots>.9986).astype(np.float32)
            self.flecks=np.maximum(self.flecks,fresh)
            # Keep exact RNG consumption and temporal history on natural frames.
            self.rng.random((self.height,self.width,3)).astype(np.float32)
            for _ in range(13):
                self.rng.integers(self.width);self.rng.integers(self.height*.55)
                self.rng.integers(40,260);self.rng.integers(4,35);self.rng.uniform(.3,.85)
        wear=np.clip(self.scratches*.65+self.flecks*.48,0,.55)
        timing=select_reference(PROFILE,t,extension='repeat')
        gate=timing['natural_gate']
        natural=None
        if gate or not self.optimized:
            frame=bgr.astype(np.float32)/255;residual=wear*.10
            natural=np.clip((frame*(1-residual[...,None])+
                np.array([.78,.82,.80])*residual[...,None])*255,0,255).astype(np.uint8)
        if gate and self.optimized:
            self.counts['natural']+=1;self.stats['strong_branches_skipped']+=1
            rendered=natural
        else:
            legacy=cv2.GaussianBlur(np.clip((self.confidence-.35)/.25,0,1),(3,3),.65)
            if is_anchor:current_confidence=self.mask(left)
            else:
                lc,lr=reliable_flow_sample(self.mask(left),small,left[3],self.xx,self.yy)
                self.stats['anchor_flow_samples']+=1
                if right[0]==left[0]:current_confidence=lc
                else:
                    rc,rr=reliable_flow_sample(self.mask(right),small,right[3],self.xx,self.yy)
                    self.stats['anchor_flow_samples']+=1
                    current_confidence=blend_anchor_samples(lc,rc,lr,rr,float((t-left[1])/(right[1]-left[1])))
            alpha,core=refine_alpha(current_confidence,gray8,legacy)
            printed=ink_print(gray8.astype(np.float32)/255,self.radial)
            self.stats['person_print_calls']+=1
            person=np.clip((printed*(1-wear[...,None])+
                np.array([.78,.82,.80])*wear[...,None])*255,0,255).astype(np.uint8)
            state=choreography(timing['reference_frame'])
            changed,_=self.bg.build(bgr,alpha,timing['reference_frame'],state)
            rendered=matte_background_composite(person,person,changed,alpha,
                core_mask=core,natural_gate=gate,natural_frame=natural)
            self.counts['natural' if gate else 'strong']+=1
            if not gate:self.counts[state]+=1
        self.stats['effects_seconds']+=time.perf_counter()-begin
        return rendered
