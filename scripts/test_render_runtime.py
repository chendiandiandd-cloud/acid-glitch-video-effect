"""Development-only runtime contracts; tiny temporary synthetic media, no inference."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import numpy as np
import acid_test_io as io
import render_video


class IOFailure(unittest.TestCase):
    def test_decoder_spawn_failure_closes_stderr(self):
        handles=[]
        factory=tempfile.TemporaryFile
        def opened():
            handle=factory();handles.append(handle);return handle
        with patch.object(io.tempfile,'TemporaryFile',side_effect=opened), \
             patch.object(io.subprocess,'Popen',side_effect=OSError('spawn sentinel')):
            with self.assertRaisesRegex(OSError,'spawn sentinel'):
                io.Decoder('unused',64,48,0,1,defaultdict(float))
        self.assertTrue(handles[0].closed)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class RuntimeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='acid-runtime-tests-')
        cls.root=Path(cls.tmp.name)
        cls.silent=cls.root/'silent.mkv';cls.audio=cls.root/'audio.mkv'
        for path,audio in ((cls.silent,False),(cls.audio,True)):
            cmd=['ffmpeg','-y','-v','error','-filter_threads','1','-f','lavfi','-i',
                 'testsrc2=size=64x48:rate=8:duration=0.5']
            if audio:cmd+=['-f','lavfi','-i','sine=frequency=440:duration=0.5']
            cmd+=['-c:v','ffv1','-threads','1']
            if audio:cmd+=['-c:a','pcm_s16le']
            subprocess.run(cmd+[str(path)],check=True,capture_output=True,timeout=30)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_default_no_report_no_postprobe_no_second_decode(self):
        out=self.root/'default.mp4'
        decoder=render_video.Decoder
        captured=[]
        def new_decoder(*args):
            captured.append(args[-1]);return decoder(*args)
        with patch.object(io.subprocess,'check_output',wraps=subprocess.check_output) as probes, \
             patch.object(io.subprocess,'Popen',wraps=subprocess.Popen) as processes, \
             patch.object(render_video,'Decoder',side_effect=new_decoder), \
             patch.object(render_video.json,'dumps',wraps=json.dumps) as reports, \
             patch.object(io,'fingerprint',side_effect=AssertionError('none must not hash')), \
             patch.object(io.np,'load',side_effect=AssertionError('none must not load cache')):
            result=render_video.render(self.silent,out,segmentation='none')
        self.assertEqual(result,{'output':str(out)})
        reports.assert_not_called()  # no diagnostic report construction, not just suppressed printing
        self.assertEqual(len(probes.call_args_list),2)  # input metadata + compressed video PTS only
        for call in probes.call_args_list:
            cmd=call.args[0]
            self.assertEqual(cmd[-1],str(self.silent))
            self.assertNotIn('-show_frames',cmd)
            if '-show_packets' in cmd:self.assertIn('v:0',cmd)
        ffmpeg=[c.args[0] for c in processes.call_args_list if c.args[0][0]=='ffmpeg']
        self.assertEqual(len(ffmpeg),2)  # sole decoder + encoder/mux
        self.assertEqual(captured[0]['video_decode_passes'],1)
        self.assertEqual(captured[0]['frames_decoded'],4)
        self.assertNotIn('output_probe_seconds',captured[0])
        encoder=next(cmd for cmd in ffmpeg if 'libx264' in cmd)
        self.assertEqual(encoder.count('-i'),1);self.assertNotIn(str(self.silent),encoder)
        self.assertEqual(list(self.root.glob('*.json')),[])
        self.assertEqual(list(self.root.glob('*.jpg')),[])
        self.assertEqual(list(self.root.glob('.acid-render-*')),[])

    def test_default_cli_is_one_line_output_only(self):
        out=self.root/'default-cli.mp4'
        result=subprocess.run([sys.executable,'-B',str(io.ROOT/'scripts/render_video.py'),
            '--input',str(self.silent),'--output',str(out),'--segmentation','none'],
            capture_output=True,check=True,timeout=30,cwd=self.root)
        self.assertEqual(json.loads(result.stdout),{'output':str(out)})
        self.assertEqual(len(result.stdout.splitlines()),1)
        self.assertEqual(result.stderr,b'')

    def test_diagnostics_reuses_counters_without_output_audit(self):
        out=self.root/'diagnostics.mp4'
        with patch.object(io.subprocess,'check_output',wraps=subprocess.check_output) as probes:
            result=render_video.render(self.audio,out,segmentation='none',diagnostics=True)
        self.assertEqual(len(probes.call_args_list),2)
        self.assertEqual(result['stats']['video_decode_passes'],1)
        self.assertEqual(result['stats']['frames_decoded'],4)
        self.assertEqual(result['frames'],4);self.assertEqual(result['fps'],'8')
        self.assertEqual(result['size'],[64,48]);self.assertEqual(result['audio'],'aac')
        self.assertNotIn('output_probe_seconds',result['stats'])
        self.assertEqual(list(self.root.glob('*.json')),[])

    def test_auto_cached_source_and_model_hashed_once_no_inference(self):
        model=self.root/'identity.onnx';model.write_bytes(b'identity only, never inferred')
        _,w,h,fps,pts=io.probe_source(self.silent)
        root=self.root/'cached'
        cache=io.MaskCache(self.silent,model,root,w,h,pts,fps,'cache-only',defaultdict(float))
        for i in range(len(pts)):np.save(cache.path/f'{i:09d}.npy',np.zeros((h,w),np.uint8))
        decoder=render_video.Decoder
        for diagnostics in (False,True):
            with self.subTest(diagnostics=diagnostics):
                captured=[]
                def new_decoder(*args):
                    captured.append(args[-1]);return decoder(*args)
                out=self.root/f'cached-{diagnostics}.mp4'
                with patch.object(io,'fingerprint',wraps=io.fingerprint) as hashes, \
                     patch.object(io.subprocess,'check_output',wraps=subprocess.check_output) as probes, \
                     patch.object(render_video,'Decoder',side_effect=new_decoder), \
                     patch.object(render_video.json,'dumps',wraps=json.dumps) as reports, \
                     patch('person_instance_mask.PersonInstanceMask',side_effect=AssertionError('no inference')):
                    result=render_video.render(self.silent,out,model=model,
                        cache_dir=root,diagnostics=diagnostics)  # actual default auto policy
                self.assertEqual([c.args[0] for c in hashes.call_args_list],[self.silent,model])
                self.assertEqual(len(probes.call_args_list),2)
                self.assertTrue(all(c.args[0][-1]==str(self.silent) for c in probes.call_args_list))
                self.assertEqual(captured[0]['video_decode_passes'],1)
                self.assertEqual(captured[0]['model_inferences'],0)
                self.assertEqual(captured[0]['cache_hit'],4)
                if diagnostics:self.assertEqual(result['cache_key'],cache.key)
                else:
                    self.assertEqual(result,{'output':str(out)})
                    # Sole dumps is necessary cache identity, not a stats report.
                    self.assertEqual(reports.call_count,1)
                    self.assertEqual(reports.call_args.args[0]['version'],3)

    def assert_clean_failure(self,out,processes,handles):
        self.assertEqual(out.read_bytes(),b'previous output')
        self.assertEqual(list(self.root.glob('.acid-render-*')),[])
        for proc in processes:
            self.assertIsNotNone(proc.poll())
            for stream in (proc.stdin,proc.stdout):
                if stream is not None:self.assertTrue(stream.closed)
        self.assertTrue(all(handle.closed for handle in handles))

    def failed_render(self,name,transform,exception,pattern,observer=None):
        out=self.root/(name+'.mp4');out.write_bytes(b'previous output')
        processes=[];handles=[];original=subprocess.Popen
        def spawn(command,*args,**kwargs):
            if command[0]!='ffmpeg':return original(command,*args,**kwargs)
            handles.append(kwargs['stderr'])
            command,after=transform(list(command))
            proc=original(command,*args,**kwargs);processes.append(proc)
            if after:after(proc)
            return proc
        with patch.object(render_video.subprocess,'Popen',side_effect=spawn):
            with self.assertRaisesRegex(exception,pattern):
                render_video.render(self.audio,out,segmentation='none',overwrite=True,
                                    frame_observer=observer)
        self.assert_clean_failure(out,processes,handles)

    def test_encoder_exit_failure_not_hidden_and_cleanup(self):
        def transform(cmd):
            if 'libx264' in cmd:cmd[cmd.index('libx264')]='no_such_encoder'
            return cmd,None
        self.failed_render('encoder-exit',transform,RuntimeError,'FFmpeg encode/mux')

    def test_decoder_nonzero_exit_not_hidden_by_double_close(self):
        def transform(cmd):
            def after(proc):
                wait=proc.wait
                def failed_wait(*args,**kwargs):wait(*args,**kwargs);return 9
                proc.wait=failed_wait
            return cmd,after if 'libx264' not in cmd else None
        self.failed_render('decoder-exit',transform,RuntimeError,'FFmpeg video decode failed')

    def test_encoder_wait_timeout_remains_failure_and_cleanup(self):
        def transform(cmd):
            def after(proc):
                wait=proc.wait;first=True
                def timed_wait(*args,**kwargs):
                    nonlocal first
                    if first:
                        first=False;raise subprocess.TimeoutExpired('encoder sentinel',120)
                    return wait(*args,**kwargs)
                proc.wait=timed_wait
            return cmd,after if 'libx264' in cmd else None
        self.failed_render('encoder-timeout',transform,subprocess.TimeoutExpired,'encoder sentinel')

    def test_effect_failure_preserved_and_all_processes_cleaned(self):
        def observer(i,frame):raise RuntimeError('effect sentinel')
        self.failed_render('effect-fail',lambda cmd:(cmd,None),RuntimeError,'effect sentinel',observer)

    def test_encoder_spawn_failure_cleans_decoder(self):
        out=self.root/'spawn-fail.mp4';processes=[];handles=[];original=subprocess.Popen
        def spawn(command,*args,**kwargs):
            if command[0]!='ffmpeg':return original(command,*args,**kwargs)
            handles.append(kwargs['stderr'])
            if 'libx264' in command:raise OSError('encoder spawn sentinel')
            proc=original(command,*args,**kwargs);processes.append(proc);return proc
        with patch.object(render_video.subprocess,'Popen',side_effect=spawn):
            with self.assertRaisesRegex(OSError,'encoder spawn sentinel'):
                render_video.render(self.audio,out,segmentation='none')
        self.assertFalse(out.exists());self.assertFalse(list(self.root.glob('.acid-render-*')))
        self.assertTrue(all(p.poll() is not None and p.stdout.closed for p in processes))
        self.assertTrue(all(h.closed for h in handles))


if __name__=='__main__':unittest.main()
