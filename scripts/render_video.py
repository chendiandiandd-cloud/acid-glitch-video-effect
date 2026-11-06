#!/usr/bin/env python3
"""Fixed portable offline acid print CLI. No preview, upload or automatic download."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','2')
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from fractions import Fraction
import cv2
from acid_test_io import ROOT, probe_source, MaskCache, Decoder, anchor_intervals
from acid_renderer import FrameEffects
cv2.setNumThreads(2)


def render(inp, out, *, start=0, duration=None, model=None, cache_dir=None,
           segmentation='auto', overwrite=False, optimized=True, frame_observer=None,
           diagnostics=False):
    """Diagnostics expose inline counters only; never probe/decode the output.
    optimized/frame_observer are developer hooks, deliberately not CLI flags.
    """
    begin=time.perf_counter();stats=defaultdict(float)
    for key in ('video_decode_passes','frames_decoded','cache_hit','cache_miss','model_inferences',
                'strong_branches_skipped','person_print_calls','wear_flow_calls','anchor_flow_samples',
                'anchors','cuts','lookahead_peak_frames'):stats[key]=0
    for key in ('segmentation_seconds','decode_read_seconds','cut_detection_seconds','effects_seconds',
                'encode_write_seconds','encode_finalize_seconds'):
        stats[key]=0.0
    inp=Path(inp).resolve();out=Path(out).resolve()
    if not inp.is_file(): raise ValueError('Input file missing: '+str(inp))
    if inp==out or (out.exists() and os.path.samefile(inp,out)):
        raise ValueError('Output must not overwrite input')
    if out.exists() and not overwrite: raise ValueError('Output exists; use --overwrite explicitly')
    if out.suffix.lower()!='.mp4': raise ValueError('Output must be an .mp4 file')
    if segmentation not in ('auto','none','cache-only'):raise ValueError('Unknown segmentation policy')
    if not math.isfinite(float(start)) or (duration is not None and not math.isfinite(float(duration))):
        raise ValueError('Start/duration must be finite')
    meta,width,height,fps,pts=probe_source(inp,start,duration)
    stats['preflight_seconds']=time.perf_counter()-begin
    ts=time.perf_counter()
    model=Path(model).resolve() if model else ROOT/'models/yolov8n-seg.onnx'
    cache=MaskCache(inp,model,cache_dir or Path(tempfile.gettempdir())/'acid-mask-cache',
                    width,height,pts,fps,segmentation,stats)
    stats['cache_setup_seconds']=time.perf_counter()-ts
    effects=FrameEffects(width,height,stats,optimized=optimized)
    # Odd native dimensions use 4:4:4 H264, avoiding crop, resize or changed aspect.
    pix_fmt='yuv444p' if width%2 or height%2 else 'yuv420p'
    audio=next((s for s in meta['streams'] if s['codec_type']=='audio'),None)
    audio_copy=audio is not None and audio['codec_name'] in ('aac','mp3','alac','ac3','eac3')
    clip_duration=Fraction(len(pts))/fps
    out.parent.mkdir(parents=True,exist_ok=True)
    decoder=None;writer=None;writer_error=None;frames=0
    with tempfile.TemporaryDirectory(prefix='.acid-render-',dir=out.parent) as work:
        temp=Path(work)/'render.mp4'
        try:
            decoder=Decoder(inp,width,height,pts[0],clip_duration,stats)
            writer_error=tempfile.TemporaryFile()
            command=['ffmpeg','-n','-v','error','-threads','2','-f','rawvideo','-pixel_format','bgr24',
                '-video_size',f'{width}x{height}','-framerate',str(fps),'-i','-']
            if audio is not None:
                command+=['-ss',str(float(pts[0])),'-i',str(inp)]
            command+=['-map','0:v:0']
            if audio is not None:command+=['-map','1:a:0']
            else:command+=['-an']
            command+=['-t',str(float(clip_duration)),'-c:v','libx264','-threads','2','-preset','veryfast',
                '-crf','18','-pix_fmt',pix_fmt]
            if audio is not None:
                command+=['-c:a','copy' if audio_copy else 'aac']
                if not audio_copy:command+=['-b:a','160k']
            command+=['-map_metadata','-1','-movflags','+faststart',str(temp)]
            writer=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=writer_error)
            for buffer,left,right in anchor_intervals(decoder,cache,pts,width,height,stats):
                for item in buffer:
                    rendered=effects.apply(item,left,right)
                    if frame_observer is not None:frame_observer(item[0],rendered)
                    ts=time.perf_counter()
                    try:writer.stdin.write(rendered.tobytes())
                    except BrokenPipeError as e:
                        writer.wait(timeout=30);writer_error.seek(0)
                        raise RuntimeError('FFmpeg encode/mux pipe failed: '+writer_error.read().decode(errors='replace')) from e
                    stats['encode_write_seconds']+=time.perf_counter()-ts;frames+=1
                buffer.clear()  # release consumed lookahead before requesting the next interval
            ts=time.perf_counter()
            try:writer.stdin.close()
            except BrokenPipeError as e:
                writer.wait(timeout=30);writer_error.seek(0)
                raise RuntimeError('FFmpeg encode/mux pipe failed: '+writer_error.read().decode(errors='replace')) from e
            code=writer.wait(timeout=120)
            stats['encode_finalize_seconds']=time.perf_counter()-ts
            if code:
                writer_error.seek(0)
                raise RuntimeError('FFmpeg encode/mux failed: '+writer_error.read().decode(errors='replace'))
            # Detach before checked close: a decoder failure must not be hidden
            # by a second close of its already-released stderr/stdout handles.
            finished_decoder=decoder;decoder=None
            finished_decoder.close(True)
            if overwrite:os.replace(temp,out)
            else:
                # Atomic no-clobber publication, including a concurrent output race.
                os.link(temp,out);temp.unlink()
        finally:
            try:
                if writer is not None:
                    if writer.poll() is None:
                        writer.kill();writer.wait(timeout=30)
                    if writer.stdin and not writer.stdin.closed:
                        try:writer.stdin.close()
                        except BrokenPipeError:pass
            finally:
                try:
                    if decoder is not None:decoder.close(False)
                finally:
                    if writer_error is not None:writer_error.close()
    if not diagnostics:return {'output':str(out)}
    stats['total_seconds']=time.perf_counter()-begin
    return {'output':str(out),'input':str(inp),'frames':frames,'size':[width,height],
            'fps':str(fps),'video_seconds':float(clip_duration),'source_pts_start':str(pts[0]),
            'source_pts_last':str(pts[-1]),'effect_extension':'repeat (source PTS continuous)',
            'segmentation':segmentation,'cache_key':cache.key,'pixel_format':pix_fmt,
            'audio':'none' if audio is None else 'copy' if audio_copy else 'aac',
            'counts':dict(effects.counts),'background_calls':effects.bg.calls,'stats':dict(stats),
            'completion':'FFmpeg decode/encode/mux exits checked; no output quality audit',
            'frames_decoded_scope':'frames delivered by sole decoder; seek/keyframe preroll not observable',
            'visual_status':'existing experimental aesthetics; not universally validated'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--start',type=float,default=0)
    parser.add_argument('--duration',type=float,help='Omit for full remaining source; no 4/6s limit')
    parser.add_argument('--model',help='Existing Kalray raw-head YOLOv8n-seg ONNX export')
    parser.add_argument('--cache-dir')
    parser.add_argument('--segmentation',choices=['auto','cache-only','none'],default='auto',
                        help='auto: cached anchors or existing lightweight person inference; none: explicit zero person matte')
    parser.add_argument('--overwrite',action='store_true')
    parser.add_argument('--diagnostics',action='store_true',help='Print inline development counters; no report file or output audit')
    args=parser.parse_args()
    try:result=render(args.input,args.output,start=args.start,duration=args.duration,model=args.model,
                      cache_dir=args.cache_dir,segmentation=args.segmentation,overwrite=args.overwrite,
                      diagnostics=args.diagnostics)
    except (ValueError,RuntimeError,OSError,subprocess.SubprocessError) as e:
        parser.exit(1,'Render failed: '+str(e)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2 if args.diagnostics else None))


if __name__=='__main__':main()
