"""Copied 2026-11-06 from workspace scripts/person_instance_mask.py.
Public Kalray YOLOv8n-seg raw-head export, obtained 2026-11-04:
https://huggingface.co/Kalray/yolov8n-seg . CPU, all-person union only.
"""
from pathlib import Path
import cv2
import numpy as np


def sigmoid(x):
    return 1/(1+np.exp(-np.clip(x,-30,30)))


class PersonInstanceMask:
    def __init__(self, model=None):
        import onnxruntime as ort
        model = model or Path(__file__).resolve().parents[1] / 'models/yolov8n-seg.onnx'
        opts=ort.SessionOptions();opts.intra_op_num_threads=4;opts.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(model),sess_options=opts,providers=['CPUExecutionProvider'])
        self.input=self.session.get_inputs()[0].name
        self.names=[o.name for o in self.session.get_outputs()]

    def segment(self, bgr, detail=False):
        union,count=self._segment_once(bgr)
        if detail:
            h,w=bgr.shape[:2]
            extent=round(w*.62)
            for x1,x2 in ((0,extent),(w-extent,w)):
                local,n=self._segment_once(bgr[:,x1:x2])
                union[:,x1:x2]=np.maximum(union[:,x1:x2],local)
        return union,count

    def _segment_once(self, bgr):
        h,w=bgr.shape[:2];scale=min(640/w,640/h)
        rw,rh=round(w*scale),round(h*scale);left=(640-rw)//2;top=(640-rh)//2
        padded=np.full((640,640,3),114,np.uint8)
        padded[top:top+rh,left:left+rw]=cv2.resize(bgr,(rw,rh))
        tensor=cv2.cvtColor(padded,cv2.COLOR_BGR2RGB).transpose(2,0,1)[None].astype(np.float32)/255
        values=dict(zip(self.names,self.session.run(None,{self.input:tensor})))
        proto=values['output1'][0]
        heads=[]
        for grid,head_name,mask_name in (
            (80,'/model.22/Concat_1_output_0','/model.22/cv4.0/cv4.0.2/Conv_output_0'),
            (40,'/model.22/Concat_2_output_0','/model.22/cv4.1/cv4.1.2/Conv_output_0'),
            (20,'/model.22/Concat_3_output_0','/model.22/cv4.2/cv4.2.2/Conv_output_0')):
            head=values[head_name][0].reshape(144,-1)
            score=sigmoid(head[64]);valid=(score>.16)&(head[64:].argmax(axis=0)==0)
            if not valid.any():continue
            indices=np.flatnonzero(valid)
            dist=head[:64,valid].reshape(4,16,-1)
            dist=np.exp(dist-dist.max(axis=1,keepdims=True));dist/=dist.sum(axis=1,keepdims=True)
            dist=(dist*np.arange(16,dtype=np.float32)[None,:,None]).sum(axis=1)
            ax=(indices%grid+.5)*640/grid;ay=(indices//grid+.5)*640/grid;stride=640/grid
            xyxy=np.stack([ax-dist[0]*stride,ay-dist[1]*stride,ax+dist[2]*stride,ay+dist[3]*stride],axis=1)
            coeff=values[mask_name][0].reshape(32,-1)[:,valid].T
            heads.append((xyxy,score[valid],coeff))
        if not heads:return np.zeros((h,w),np.float32),0
        boxes=np.concatenate([z[0] for z in heads]);scores=np.concatenate([z[1] for z in heads]);coeffs=np.concatenate([z[2] for z in heads])
        xywh=boxes.copy();xywh[:,2:]-=xywh[:,:2]
        selected=np.array(cv2.dnn.NMSBoxes(xywh.tolist(),scores.tolist(),.16,.45)).reshape(-1)
        union=np.zeros((640,640),np.float32)
        for i in selected:
            mask=sigmoid(coeffs[i]@proto.reshape(32,-1)).reshape(160,160)
            mask=cv2.resize(mask,(640,640),interpolation=cv2.INTER_LINEAR)
            x1,y1,x2,y2=np.clip(boxes[i],0,640).astype(int)
            cropped=np.zeros_like(mask);cropped[y1:y2,x1:x2]=mask[y1:y2,x1:x2]
            union=np.maximum(union,cropped)
        union=cv2.resize(union[top:top+rh,left:left+rw],(w,h),interpolation=cv2.INTER_LINEAR)
        return union,len(selected)
