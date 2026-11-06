"""Portable IO migrated 2026-11-06 from workspace scripts/acid_test_io.py.
Packet PTS audit is demux only. One sequential video decode; bounded lookahead.
"""
import hashlib
import json
import subprocess
import tempfile
import time
from pathlib import Path
from fractions import Fraction
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def probe_json(inp):
    try:
        return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams',
            '-show_format','-of','json',str(inp)], stderr=subprocess.STDOUT, timeout=60))
    except subprocess.CalledProcessError as e:
        raise ValueError('ffprobe failed: '+e.output.decode(errors='replace')) from e


def probe_source(inp, start=0, duration=None):
    meta=probe_json(inp)
    video=next((s for s in meta['streams'] if s['codec_type']=='video'),None)
    if video is None: raise ValueError('Input has no video stream')
    w,h=video['width'],video['height']
    rotation=next((int(s['rotation']) for s in video.get('side_data_list',[]) if 'rotation' in s),
                  int(video.get('tags',{}).get('rotate',0)))
    if rotation % 90: raise ValueError('Only right-angle rotation supported')
    if rotation%180: w,h=h,w
    if min(w,h)<4: raise ValueError('Display geometry must be at least 4x4 for optical flow')
    if video.get('sample_aspect_ratio','1:1') not in ('1:1','N/A'):
        raise ValueError('Non-square SAR needs explicit adapter')
    if video.get('color_transfer') in ('smpte2084','arib-std-b67'):
        raise ValueError('HDR needs explicit color conversion')
    fps=Fraction(video['avg_frame_rate'])
    if fps<=0: raise ValueError('Invalid frame rate')
    # Reading compressed packets does NOT decode frames, even for full duration.
    packets=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
        '-show_packets','-show_entries','packet=pts','-of','json',str(inp)],timeout=120))['packets']
    if not packets or any('pts' not in p for p in packets): raise ValueError('Missing packet PTS')
    tb=Fraction(video['time_base'])
    raw=sorted(Fraction(p['pts'])*tb for p in packets);origin=raw[0]
    relative=[p-origin for p in raw]
    if any(abs(p-Fraction(i)/fps)>tb for i,p in enumerate(relative)) or len(set(raw))!=len(raw):
        raise ValueError('VFR/non-grid packet PTS unsupported; no silent CFR conversion')
    start=Fraction(str(start));end=relative[-1]+1/fps
    if start<0 or start>=end: raise ValueError('Start outside source coverage')
    if duration is not None:
        duration=Fraction(str(duration))
        if duration<=0 or start+duration>end+tb: raise ValueError('Duration outside source coverage')
        end=min(end,start+duration)
    pts=[p for p in relative if start<=p<end]
    if not pts: raise ValueError('No frames in requested range')
    return meta,w,h,fps,pts


def fingerprint(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): digest.update(block)
    return digest.hexdigest()


class MaskCache:
    def __init__(self, inp, model, root, width, height, pts, fps, policy, stats):
        self.stats=stats;self.policy=policy;self.model=None;self.model_path=model
        scale=min(1,960/max(width,height));self.cw,self.ch=round(width*scale),round(height*scale)
        if policy=='none': self.path=None;self.key=None;return
        if not Path(model).is_file(): raise ValueError('Missing segmentation model: '+str(model)+'; use --model or --segmentation none')
        spec={'version':3,'source_sha256':fingerprint(inp),'model_sha256':fingerprint(model),
              'geometry':[width,height],'mask_geometry':[self.cw,self.ch],
              'coverage':[str(pts[0]),str(pts[-1]+1/fps)],'fps':str(fps),
              'configuration':'all-person-detail-long960-native-aspect-v2;anchors8Hz;hist-cut-v1',
              'rotation':'ffmpeg-auto'}
        self.key=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()[:24]
        self.path=Path(root)/self.key;self.path.mkdir(parents=True,exist_ok=True)
        manifest=self.path/'manifest.json'
        if manifest.exists():
            try: stored=json.loads(manifest.read_text())
            except (ValueError,OSError) as e: raise ValueError('Corrupt cache manifest: '+str(manifest)) from e
            if stored!=spec: raise ValueError('Cache identity mismatch: '+str(manifest))
        else:
            manifest.write_text(json.dumps(spec,indent=2))

    def anchor(self, bgr, i):
        ts=time.perf_counter()
        if self.policy=='none': return np.zeros((self.ch,self.cw),np.uint8)
        file=self.path/f'{i:09d}.npy'
        if file.exists():
            try: compact=np.load(file,allow_pickle=False)
            except (ValueError,OSError,EOFError) as e: raise ValueError('Corrupt mask cache: '+str(file)) from e
            self.stats['cache_hit']+=1
        else:
            self.stats['cache_miss']+=1
            if self.policy=='cache-only': raise ValueError('Required mask cache missing: '+str(file))
            try:
                if self.model is None:
                    from person_instance_mask import PersonInstanceMask
                    self.model=PersonInstanceMask(self.model_path)
                confidence,_=self.model.segment(cv2.resize(bgr,(self.cw,self.ch)),detail=True)
            except Exception as e:
                raise ValueError('Person segmentation failed with model '+str(self.model_path)+': '+str(e)) from e
            compact=np.rint(confidence*255).astype(np.uint8)
            # Atomic cache writes; incomplete files never become usable anchors.
            with tempfile.NamedTemporaryFile(dir=self.path,suffix='.npy',delete=False) as temp:
                name=Path(temp.name)
                try: np.save(temp,compact,allow_pickle=False)
                except BaseException: name.unlink(missing_ok=True);raise
            name.replace(file);self.stats['model_inferences']+=1
        if compact.shape!=(self.ch,self.cw) or compact.dtype!=np.uint8:
            raise ValueError('Invalid mask cache geometry/dtype: '+str(file))
        self.stats['segmentation_seconds']+=time.perf_counter()-ts
        return compact


class Decoder:
    def __init__(self, inp, width, height, start, duration, stats):
        self.stats=stats;self.width=width;self.height=height
        self.err=tempfile.TemporaryFile()
        try:
            self.proc=subprocess.Popen(['ffmpeg','-v','error','-threads','2','-filter_threads','2',
                '-ss',str(float(start)),'-i',str(inp),'-t',str(float(duration)),
                '-map','0:v:0','-an','-vsync','0','-pix_fmt','bgr24','-f','rawvideo','-'],
                stdout=subprocess.PIPE,stderr=self.err)
        except BaseException:
            self.err.close();raise
        stats['video_decode_passes']+=1

    def read(self):
        ts=time.perf_counter();size=self.width*self.height*3
        raw=self.proc.stdout.read(size)
        self.stats['decode_read_seconds']+=time.perf_counter()-ts
        if len(raw)!=size: raise ValueError('Source decode ended early or geometry mismatch')
        self.stats['frames_decoded']+=1
        return np.frombuffer(raw,np.uint8).reshape(self.height,self.width,3)

    def close(self, success):
        if not success and self.proc.poll() is None: self.proc.kill()
        self.proc.stdout.close()
        try: code=self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill();self.proc.wait();code=-1
        self.err.seek(0);error=self.err.read().decode(errors='replace');self.err.close()
        if success and code: raise RuntimeError('FFmpeg video decode failed: '+error)


def anchor_intervals(decoder, cache, pts, width, height, stats):
    """Emit (buffer,left,right). Right cut disables interpolation exactly as legacy.
    At most one 8Hz interval of full-size frames, plus its right anchor, in memory.
    Cut histograms and masks advance during lookahead; render flow remains ordered.
    """
    previous=None;last_hist=None;left=None;buffer=[]
    for i,t in enumerate(pts):
        bgr=decoder.read();ts=time.perf_counter()
        gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY);small=cv2.resize(gray,(width//4,height//4))
        hsv=cv2.cvtColor(cv2.resize(bgr,(160,160)),cv2.COLOR_BGR2HSV)
        hist=cv2.calcHist([hsv],[0,1],None,[24,16],[0,180,0,256]);cv2.normalize(hist,hist)
        cut=False
        if previous is not None:
            delta=float(np.abs(small.astype(np.float32)-previous).mean())
            hd=cv2.compareHist(last_hist,hist,cv2.HISTCMP_BHATTACHARYYA)
            cut=delta>45 or (delta>18 and hd>.55)
        previous=small;last_hist=hist
        anchor=i==0 or int(t*8)!=int(pts[i-1]*8) or cut
        item=(i,t,bgr,gray,small,cut,anchor)
        stats['cut_detection_seconds']+=time.perf_counter()-ts
        if cut: stats['cuts']+=1
        if anchor:
            compact=cache.anchor(bgr,i)
            right=(i,t,compact,small,cut)
            stats['anchors']+=1
            if left is not None:
                yield buffer,left,(left if cut else right)
                buffer=[]
            left=right
        buffer.append(item)
        stats['lookahead_peak_frames']=max(stats['lookahead_peak_frames'],len(buffer)+1)
    if buffer: yield buffer,left,left
