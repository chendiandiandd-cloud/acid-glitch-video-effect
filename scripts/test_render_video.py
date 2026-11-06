"""Development-only tiny synthetic media tests; never consumes user videos or infers.
Copied baseline matte contracts from workspace test_acid_matte_ink.py (2026-11-06).
"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import cv2
import numpy as np
import acid_test_io as io
import render_video
from acid_renderer import FrameEffects, ink_print
from acid_matte_ink_algorithms import refine_alpha, blend_anchor_samples, reliable_flow_sample
import reference_background_recipes as recipes
from background_print_states import background_state

ROOT=Path(__file__).resolve().parents[1]


def run(command):
    return subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=60)


def media(path,seconds=7,size='64x48',audio=False,vfr=False):
    command=['ffmpeg','-y','-v','error','-threads','1','-filter_threads','1',
             '-f','lavfi','-i',f'testsrc2=size={size}:rate=8:duration={seconds}']
    if audio:command+=['-f','lavfi','-i',f'sine=frequency=440:duration={seconds}']
    if vfr:command+=['-vf','setpts=if(lt(N\,4)\,N\,2*N-4)/(8*TB)','-fps_mode','vfr']
    command+=['-c:v','ffv1','-threads','1']
    if audio:command+=['-c:a','pcm_s16le']
    run(command+[str(path)])


class ArrayRegression(unittest.TestCase):
    def test_holes_small_people_core_and_soft_edges(self):
        c=np.zeros((80,120),np.float32);c[10:65,30:85]=1;c[25:40,48:63]=0
        c[7:12,7:12]=1;c[65:78,112:]=1
        a,core=refine_alpha(c,np.full(c.shape,128,np.uint8),c.copy())
        self.assertTrue(np.all(a[c<=.38]==0));self.assertEqual(a[30,54],0)
        self.assertGreater(a[9,9],.8);self.assertGreater(a[73,118],.8)
        self.assertTrue(np.all(a[core]==1));self.assertTrue(np.all(c[core]==1))
        c=np.tile(np.linspace(0,1,120,dtype=np.float32),(60,1))
        a,core=refine_alpha(c,np.full(c.shape,128,np.uint8),c)
        self.assertFalse(core.any());self.assertTrue(((a>0)&(a<1)).any())

    def test_original_core_ink_arithmetic(self):
        rng=np.random.default_rng(1);gray=rng.random((40,50),dtype=np.float32)
        printed=ink_print(gray,rng.random(gray.shape,dtype=np.float32)*.5)
        wear=rng.random(gray.shape,dtype=np.float32)*.55;bg=rng.random(printed.shape,dtype=np.float32)
        person=np.ones(gray.shape,np.float32)
        baseline=printed*person[...,None]+bg*(1-person[...,None])
        expected=np.clip((baseline*(1-wear[...,None])+np.array([.78,.82,.80])*wear[...,None])*255,0,255).astype(np.uint8)
        actual=np.clip((printed*(1-wear[...,None])+np.array([.78,.82,.80])*wear[...,None])*255,0,255).astype(np.uint8)
        np.testing.assert_array_equal(actual,expected)

    def test_disagreement_and_identity_flow(self):
        left=np.zeros((20,50),np.float32);left[:,5:14]=1
        right=np.zeros_like(left);right[:,22:31]=1;rel=np.ones_like(left)
        np.testing.assert_array_equal(blend_anchor_samples(left,right,rel,rel,.25),left)
        np.testing.assert_array_equal(blend_anchor_samples(left,right,rel,rel,.75),right)
        yy,xx=np.mgrid[:20,:50].astype(np.float32);gray=np.full((5,12),123,np.uint8)
        sample,reliability=reliable_flow_sample(left,gray,gray,xx,yy)
        np.testing.assert_array_equal(sample,left);self.assertTrue(np.all(reliability==1))

    def test_lazy_recipes_eager_oracle_and_counts(self):
        yy,xx=np.mgrid[:48,:64].astype(np.float32)
        bg=recipes.ReferenceBackgroundRecipes(xx,yy);rng=np.random.default_rng(42)
        bgr=rng.integers(0,256,(48,64,3),dtype=np.uint8);alpha=np.zeros((48,64),np.float32)
        alpha[8:30,12:32]=.5
        with patch.object(recipes,'background_state',wraps=background_state) as calls:
            for tick in (0,5,7,9):
                for state in ('source','duotone','ink_colorfield','liquid_replace','horizontal_glitch'):
                    # Eager legacy precomputations had no side effects or history.
                    fluid=recipes.pigment_fold(xx,yy,tick)
                    kw=dict(color_order='BGR',dark_color=(2,3,4),light_color=(12,218,255) if tick%3 else (8,179,255),
                            threshold=.48,transition_width=.06,halftone=bg.halftone)
                    duo=background_state(bgr,'duotone',**kw)
                    fill=background_state(bgr,'ink_colorfield',color_field=fluid,**kw)
                    before=calls.call_count
                    actual,_=bg.build(bgr,alpha,tick,state)
                    self.assertEqual(calls.call_count-before,2 if state=='horizontal_glitch' else 1)
                    if state=='source':expected=bgr.copy()
                    elif state=='duotone':expected=duo
                    elif state=='ink_colorfield':expected=fill
                    elif state=='liquid_replace':expected=fluid.copy()
                    else:
                        expected=fill.copy();safe=alpha==0
                        for x,y,x1,y1,shift,cut in bg.rectangles:
                            if x1<=x:continue
                            sx=x+shift+((np.arange(x,x1)-x)//(5 if cut else 3))*(5 if cut else 3)//3
                            sx_safe=np.clip(sx,0,63)
                            valid=safe[y:y1,x:x1]&safe[y:y1,sx_safe]&(sx>=0)[None,:]&(sx<64)[None,:]
                            sampled=fill[y:y1,sx_safe].copy()
                            if cut:sampled[::max(2,(y1-y)//3+1)]=(2,3,4)
                            expected[y:y1,x:x1][valid]=sampled[valid]
                    if state!='source':expected[bg.flecks & np.any(expected>8,axis=2)]=(2,3,4)
                    np.testing.assert_array_equal(actual,expected)

    def test_online_lookahead_matches_predecoded_anchor_oracle(self):
        rng=np.random.default_rng(8)
        # Smooth motion plus one unmistakable cut, nonzero synthetic person matte.
        base=rng.integers(0,256,(48,64,3),dtype=np.uint8)
        frames=[np.roll(base,i//2,axis=1) if i<12 else np.full_like(base,220) for i in range(28)]
        pts=[Fraction(i,24) for i in range(len(frames))];stats=defaultdict(float)
        class Decoder:
            def __init__(self):self.i=0
            def read(self):frame=frames[self.i];self.i+=1;return frame
        class Cache:
            def anchor(self,bgr,i):
                mask=np.zeros((48,64),np.uint8);mask[8:40,10+i%9:30+i%9]=255;return mask
        intervals=list(io.anchor_intervals(Decoder(),Cache(),pts,64,48,stats))
        items=[item for buffer,_,_ in intervals for item in buffer]
        # Independent predecoded oracle discovers all anchors before rendering.
        anchors={item[0]:(item[0],item[1],Cache().anchor(item[2],item[0]),item[4],item[5])
                 for item in items if item[6]}
        indices=sorted(anchors);a=FrameEffects(64,48,defaultdict(float),True)
        b=FrameEffects(64,48,defaultdict(float),False)
        actual={}
        for buffer,left,right in intervals:
            for item in buffer:actual[item[0]]=a.apply(item,left,right)
        for item in items:
            i=item[0];left=max(j for j in indices if j<=i)
            right=next((j for j in indices if j>i),left)
            if anchors[right][4]:right=left
            np.testing.assert_array_equal(actual[i],b.apply(item,anchors[left],anchors[right]))
        self.assertGreater(stats['cuts'],0);self.assertLessEqual(stats['lookahead_peak_frames'],5)
        self.assertGreater(a.stats['strong_branches_skipped'],0)
        self.assertEqual(a.stats['person_print_calls']+a.stats['strong_branches_skipped'],len(items))


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class PortableIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='acid-synthetic-tests-');cls.root=Path(cls.tmp.name)
        cls.silent=cls.root/'silent.mkv';media(cls.silent)
        cls.audio=cls.root/'audio.mkv';media(cls.audio,seconds=1,audio=True)
        cls.package=cls.root/'standalone'
        cls.package.mkdir()
        for directory in ('scripts','references','models'):
            shutil.copytree(ROOT/directory,cls.package/directory,ignore=shutil.ignore_patterns('__pycache__'))
        for file in ('SKILL.md','requirements.txt','.skillignore'):
            shutil.copy2(ROOT/file,cls.package/file)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def cli(self,inp,out,*options,success=True,diagnostics=True):
        command=[sys.executable,'-B',str(self.package/'scripts/render_video.py'),
                 '--input',str(inp),'--output',str(out),'--segmentation','none',*options]
        if diagnostics:command+=['--diagnostics']
        result=subprocess.run(command,cwd=self.root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        if success:
            self.assertEqual(result.returncode,0,result.stderr.decode())
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode,0);return result.stderr.decode()

    def test_real_cli_standalone_full_long_and_silent(self):
        report=self.cli(self.silent,self.root/'full.mp4')
        self.assertEqual(report['frames'],56);self.assertEqual(report['video_seconds'],7)
        self.assertEqual(report['audio'],'none');self.assertEqual(report['stats']['video_decode_passes'],1)
        self.assertEqual(report['stats']['frames_decoded'],56)
        self.assertEqual(report['stats']['model_inferences'],0)
        print('SYNTHETIC_FULL_STATS '+json.dumps(report['stats'])+' STATES '+json.dumps(report['background_calls']))

    def test_real_cli_start_duration_and_audio_fallback(self):
        report=self.cli(self.audio,self.root/'audio.mp4','--start','.25','--duration','.5')
        self.assertEqual(report['frames'],4);self.assertEqual(report['source_pts_start'],'1/4')
        self.assertEqual(report['audio'],'aac')
        meta=io.probe_json(self.root/'audio.mp4')
        self.assertTrue(any(s['codec_type']=='audio' for s in meta['streams']))

    def test_real_cli_audio_copy(self):
        aac=self.root/'aac.mp4'
        run(['ffmpeg','-y','-v','error','-i',str(self.audio),'-c:v','libx264','-threads','1','-c:a','aac',str(aac)])
        report=self.cli(aac,self.root/'audio-copy.mp4');self.assertEqual(report['audio'],'copy')

    def test_odd_geometry_no_resize(self):
        odd=self.root/'odd.mkv'
        # testsrc (RGB) retains odd sizes, unlike testsrc2's subsampled generator.
        run(['ffmpeg','-y','-v','error','-filter_threads','1','-f','lavfi','-i',
             'testsrc=size=65x49:rate=8:duration=1','-c:v','ffv1','-threads','1',str(odd)])
        report=self.cli(odd,self.root/'odd.mp4')
        self.assertEqual(report['size'],[65,49]);self.assertEqual(report['pixel_format'],'yuv444p')

    def test_rotation_cfr_geometry(self):
        base=self.root/'rotation-base.mp4';rot=self.root/'rotation.mp4'
        run(['ffmpeg','-y','-v','error','-i',str(self.audio),'-an','-c:v','libx264','-threads','1',str(base)])
        run(['ffmpeg','-y','-v','error','-i',str(base),'-c','copy','-metadata:s:v:0','rotate=90',str(rot)])
        report=self.cli(rot,self.root/'rotated.mp4');self.assertEqual(report['size'],[48,64])
        self.assertEqual(report['fps'],'8')

    def test_vfr_rejected_without_render(self):
        vfr=self.root/'vfr.mkv';media(vfr,seconds=1,vfr=True)
        error=self.cli(vfr,self.root/'vfr.mp4',success=False)
        self.assertIn('VFR',error);self.assertFalse((self.root/'vfr.mp4').exists())

    def test_overwrite_input_and_existing_errors(self):
        error=self.cli(self.silent,self.silent,success=False);self.assertIn('overwrite input',error)
        out=self.root/'existing.mp4';out.write_bytes(b'original')
        self.assertIn('Output exists',self.cli(self.silent,out,success=False));self.assertEqual(out.read_bytes(),b'original')
        self.cli(self.audio,out,'--overwrite');self.assertNotEqual(out.read_bytes(),b'original')

    def test_invalid_ranges_and_missing_model(self):
        for options in (('--duration','0'),('--duration','8'),('--start','9'),('--start','nan')):
            self.cli(self.silent,self.root/'bad-range.mp4',*options,success=False)
        with self.assertRaisesRegex(ValueError,'Missing segmentation model'):
            render_video.render(self.audio,self.root/'missing-model.mp4',model=self.root/'missing.onnx')
        self.assertFalse((self.root/'missing-model.mp4').exists())

    def test_cache_contract_and_corruption_no_inference(self):
        model=self.root/'fake.onnx';model.write_bytes(b'no inference allowed')
        _,w,h,fps,pts=io.probe_source(self.audio)
        def make(inp=self.audio,width=w,coverage=pts):
            return io.MaskCache(inp,model,self.root/'cache',width,h,coverage,fps,'cache-only',defaultdict(float))
        cache=make();other=make(self.silent);self.assertNotEqual(cache.key,other.key)
        self.assertNotEqual(cache.key,make(width=w+2).key)
        self.assertNotEqual(cache.key,make(coverage=pts[1:]).key)
        model.write_bytes(b'different model');self.assertNotEqual(cache.key,make().key)
        image=np.zeros((h,w,3),np.uint8)
        with self.assertRaisesRegex(ValueError,'cache missing'):cache.anchor(image,0)
        file=cache.path/'000000000.npy';file.write_bytes(b'broken')
        with self.assertRaisesRegex(ValueError,'Corrupt mask cache'):cache.anchor(image,0)
        np.save(file,np.zeros((h,w),np.uint8),allow_pickle=False)
        np.testing.assert_array_equal(cache.anchor(image,0),np.zeros((h,w),np.uint8))
        np.save(file,np.zeros((h+1,w),np.uint8),allow_pickle=False)
        with self.assertRaisesRegex(ValueError,'geometry/dtype'):cache.anchor(image,0)
        current=make();(current.path/'manifest.json').write_text('{bad')
        with self.assertRaisesRegex(ValueError,'Corrupt cache manifest'):make()
        none=io.MaskCache(self.audio,self.root/'absent.onnx',self.root/'cache2',w,h,pts,fps,'none',defaultdict(float))
        np.testing.assert_array_equal(none.anchor(image,0),np.zeros((h,w),np.uint8))

    def test_segmentation_model_error_is_clear_without_inference(self):
        model=self.root/'invalid-model.onnx';model.write_bytes(b'invalid test identity')
        image=np.zeros((48,64,3),np.uint8)
        cache=io.MaskCache(self.audio,model,self.root/'invalid-model-cache',64,48,
                           [Fraction(0)],Fraction(8),'auto',defaultdict(float))
        with patch('person_instance_mask.PersonInstanceMask',side_effect=ValueError('invalid ONNX test')):
            with self.assertRaisesRegex(ValueError,'Person segmentation failed.*invalid ONNX test'):
                cache.anchor(image,0)
        self.assertFalse(list(cache.path.glob('*.npy')))

    def test_cache_only_synthetic_masks_real_cli_24fps(self):
        source=self.root/'flow24.mkv'
        run(['ffmpeg','-y','-v','error','-filter_threads','1','-f','lavfi','-i',
             'testsrc2=size=64x48:rate=24:duration=1','-c:v','ffv1','-threads','1',str(source)])
        model=self.root/'synthetic-cache-identity.onnx';model.write_bytes(b'identity only; never inferred')
        _,w,h,fps,pts=io.probe_source(source)
        cache_dir=self.root/'cache-only-e2e'
        cache=io.MaskCache(source,model,cache_dir,w,h,pts,fps,'cache-only',defaultdict(float))
        for i,t in enumerate(pts):
            if i==0 or int(t*8)!=int(pts[i-1]*8):
                mask=np.zeros((h,w),np.uint8);mask[8:40,12+i//3:32+i//3]=255
                np.save(cache.path/f'{i:09d}.npy',mask,allow_pickle=False)
        result=self.cli(source,self.root/'flow24.mp4','--segmentation','cache-only',
                        '--model',str(model),'--cache-dir',str(cache_dir))
        self.assertEqual(result['frames'],24);self.assertEqual(result['stats']['cache_hit'],8)
        self.assertEqual(result['stats']['model_inferences'],0)
        self.assertGreater(result['stats']['anchor_flow_samples'],0)
        self.assertLessEqual(result['stats']['lookahead_peak_frames'],4)
        print('CACHE_ONLY_24FPS '+json.dumps(result['stats']))

    def test_ffmpeg_failure_cleanup(self):
        original=subprocess.Popen
        def fail_encoder(command,*args,**kwargs):
            command=list(command)
            if 'libx264' in command:command[command.index('libx264')]='no_such_encoder'
            return original(command,*args,**kwargs)
        out=self.root/'encoder-fail.mp4'
        with patch.object(render_video.subprocess,'Popen',side_effect=fail_encoder):
            with self.assertRaises((RuntimeError,BrokenPipeError,ValueError)):
                render_video.render(self.audio,out,segmentation='none')
        self.assertFalse(out.exists());self.assertFalse(list(self.root.glob('.acid-render-*')))

    def test_optimized_off_end_to_end_pixel_equivalence(self):
        frames_a=[];frames_b=[]
        a=render_video.render(self.silent,self.root/'on.mp4',segmentation='none',
            frame_observer=lambda i,f:frames_a.append(f.copy()),diagnostics=True)
        b=render_video.render(self.silent,self.root/'off.mp4',segmentation='none',optimized=False,
            frame_observer=lambda i,f:frames_b.append(f.copy()),diagnostics=True)
        for x,y in zip(frames_a,frames_b):np.testing.assert_array_equal(x,y)
        self.assertEqual(len(frames_a),56);self.assertGreater(a['stats']['strong_branches_skipped'],0)
        self.assertEqual(a['stats']['person_print_calls']+a['stats']['strong_branches_skipped'],b['stats']['person_print_calls'])
        # Decode generated tiny outputs only to compare actual H264 encoded pixels.
        def decode(path):return run(['ffmpeg','-v','error','-i',str(path),'-f','rawvideo','-pix_fmt','bgr24','-']).stdout
        self.assertEqual(decode(self.root/'on.mp4'),decode(self.root/'off.mp4'))
        print('OPTIMIZATION_EVIDENCE '+json.dumps({'on':a['stats'],'off':b['stats'],'pixel_differences':0}))


if __name__=='__main__':unittest.main()
