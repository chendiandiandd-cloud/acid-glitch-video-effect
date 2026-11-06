"""Copied 2026-11-06 from workspace scripts/acid_matte_ink_algorithms.py.
Local matte refinement; original formulas unchanged. No semantic inference.
"""
import cv2
import numpy as np


def refine_alpha(confidence, gray, legacy_person):
    c=np.asarray(confidence,np.float32)
    if c.shape!=gray.shape or c.shape!=legacy_person.shape or not np.isfinite(c).all():
        raise ValueError('matte geometry/finite')
    if np.any((c<0)|(c>1)): raise ValueError('confidence range')
    g=gray.astype(np.float32)/255 if gray.dtype==np.uint8 else gray
    cp=cv2.copyMakeBorder(c,1,1,1,1,cv2.BORDER_REFLECT_101)
    gp=cv2.copyMakeBorder(g,1,1,1,1,cv2.BORDER_REFLECT_101)
    numerator=c.copy(); denominator=np.ones_like(c)
    h,w=c.shape
    for dy,dx in ((-1,0),(1,0),(0,-1),(0,1)):
        other=gp[1+dy:1+dy+h,1+dx:1+dx+w]
        weight=.45*np.exp(-np.abs(other-g)/.055)
        numerator+=cp[1+dy:1+dy+h,1+dx:1+dx+w]*weight
        denominator+=weight
    refined=numerator/denominator
    a=np.clip((refined-.42)/.30,0,1)
    a=a*a*(3-2*a)
    a[c<=.38]=0
    core=cv2.erode(((refined>=.86)&(legacy_person==1)).astype(np.uint8),
                   np.ones((3,3),np.uint8)).astype(bool)
    a[core]=1
    return a.astype(np.float32),core


def reliable_flow_sample(mask, current_gray, anchor_gray, xx, yy):
    h,w=mask.shape;sh,sw=current_gray.shape
    if np.array_equal(current_gray,anchor_gray):
        return mask.copy(),np.ones_like(mask)
    flow=cv2.calcOpticalFlowFarneback(current_gray,anchor_gray,None,.5,3,17,3,5,1.1,0)
    reverse=cv2.calcOpticalFlowFarneback(anchor_gray,current_gray,None,.5,3,17,3,5,1.1,0)
    sy,sx=np.mgrid[:sh,:sw].astype(np.float32)
    tx,ty=sx+flow[...,0],sy+flow[...,1]
    back=cv2.remap(reverse,tx,ty,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    error=np.linalg.norm(flow+back,axis=2)
    sampled_gray=cv2.remap(anchor_gray,tx,ty,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    photo=np.abs(sampled_gray.astype(np.float32)-current_gray)/255
    valid=(tx>=0)&(tx<=sw-1)&(ty>=0)&(ty<=sh-1)
    reliability=np.exp(-error**2/1.5**2-photo**2/.16**2)*valid
    full=cv2.resize(flow,(w,h)); full[...,0]*=w/sw;full[...,1]*=h/sh
    mx,my=xx+full[...,0],yy+full[...,1]
    sample=cv2.remap(mask,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    rel=cv2.resize(reliability.astype(np.float32),(w,h))
    rel[(mx<0)|(mx>w-1)|(my<0)|(my>h-1)]=0
    return sample,rel


def blend_anchor_samples(left,right,left_rel,right_rel,fraction):
    wl=(1-fraction)*left_rel;wr=fraction*right_rel
    denom=wl+wr
    nearest=left if fraction<.5 else right
    result=np.where(denom>.12,(left*wl+right*wr)/np.maximum(denom,1e-6),nearest)
    disagree=np.abs(left-right)>.45
    choose_left=wl>=wr
    result[disagree]=np.where(choose_left,left,right)[disagree]
    return np.clip(result,0,1).astype(np.float32)


from reference_background_recipes import pigment_fold, ReferenceBackgroundRecipes as InkBackground
