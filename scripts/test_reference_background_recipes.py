"""Array regression for real recipes, not visual approval scores."""
import unittest
import numpy as np
from reference_background_recipes import ReferenceBackgroundRecipes, pigment_fold
from matte_composite import matte_background_composite


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.yy,self.xx=np.mgrid[:90,:160].astype(np.float32)
        self.bg=ReferenceBackgroundRecipes(self.xx,self.yy)
        self.src=np.full((90,160,3),230,np.uint8);self.src[:,30:50]=20
        self.a=np.zeros((90,160),np.float32)

    def test_solid_dark_light_and_narrow_window(self):
        out,_=self.bg.build(self.src,self.a,5,'duotone')
        self.assertTrue(np.all(out[:,30:50]==(2,3,4)))
        self.assertLessEqual(len(np.unique(out.reshape(-1,3),axis=0)),2)
        self.assertGreater(np.all(out[:,:20]==self.bg.light,axis=2).mean(),.98)
        # Changing dot phase cannot change tones outside .45..51.
        self.bg.halftone[:]=0
        a,_=self.bg.build(self.src,self.a,5,'duotone')
        self.bg.halftone[:]=1
        b,_=self.bg.build(self.src,self.a,5,'duotone')
        self.assertTrue(np.array_equal(a,b))

    def test_ink_not_washed_by_color(self):
        out,_=self.bg.build(self.src,self.a,8,'ink_colorfield')
        self.assertTrue(np.all(out[:,30:50]==(2,3,4)))

    def test_finite_2d_bands_and_motion(self):
        a=pigment_fold(self.xx,self.yy,8)
        self.assertLessEqual(len(np.unique(a.reshape(-1,3),axis=0)),4)
        self.assertGreater(np.any(a[:,1:]!=a[:,:-1],axis=2).sum(),100)
        self.assertGreater(np.any(a[1:]!=a[:-1],axis=2).sum(),100)
        self.assertFalse(np.array_equal(a,pigment_fold(self.xx,self.yy,9)))

    def test_explicit_no_expansion(self):
        e=np.zeros(self.a.shape,np.float32);e[:,60:100]=.5
        out,got=self.bg.build(self.src,self.a,7,'liquid_replace',policy='explicit',allowed_mask=e)
        self.assertTrue(np.array_equal(out[e==0],self.src[e==0]))
        self.assertTrue(np.array_equal(got,e))

    def test_source_exact_and_inputs_unchanged(self):
        before=self.src.copy();mask=self.a.copy()
        out,_=self.bg.build(self.src,self.a,6,'source')
        self.assertTrue(np.array_equal(out,before));out[:]=0
        self.assertTrue(np.array_equal(self.src,before));self.assertTrue(np.array_equal(self.a,mask))

    def test_local_scan_uses_structure_not_global_stripes(self):
        rng=np.random.default_rng(3)
        src=rng.integers(0,256,self.src.shape,dtype=np.uint8)
        fill,_=self.bg.build(src,self.a,7,'ink_colorfield')
        glitch,_=self.bg.build(src,self.a,7,'horizontal_glitch')
        changed=np.any(fill!=glitch,axis=2)
        self.assertTrue(changed.any());self.assertLess(changed.mean(),.7)
        self.assertTrue(all(x1-x<160 for x,y,x1,y1,s,d in self.bg.rectangles))

    def test_scan_subject_poison_cannot_escape(self):
        a=self.a.copy();a[:,30:50]=.5
        poison=self.src.copy();poison[:,30:50]=(230,40,210)
        first,_=self.bg.build(self.src,a,7,'horizontal_glitch')
        second,_=self.bg.build(poison,a,7,'horizontal_glitch')
        self.assertTrue(np.array_equal(first[a==0],second[a==0]))

    def test_matte_core_soft_and_gate_regression(self):
        bg,_=self.bg.build(self.src,self.a,9,'liquid_replace')
        person=np.full_like(bg,70);approved=np.full_like(bg,200)
        alpha=self.a.copy();alpha[:,30:50]=1;alpha[:,50:55]=.5;core=alpha==1
        out=matte_background_composite(approved,person,bg,alpha,core_mask=core)
        self.assertTrue(np.array_equal(out[core],approved[core]))
        self.assertTrue(np.array_equal(out[alpha==0],bg[alpha==0]))
        poison=approved.copy();poison[~core]=0
        self.assertTrue(np.array_equal(out,matte_background_composite(poison,person,bg,alpha,core_mask=core)))
        natural=matte_background_composite(approved,person,bg,alpha,core_mask=core,natural_gate=True,natural_frame=self.src)
        self.assertTrue(np.array_equal(natural,self.src))

    def test_bad_shape_finite_tick_and_policy_rejected(self):
        for tick in (True,-1,.5,float('nan'),1000001):
            with self.assertRaises(ValueError):self.bg.build(self.src,self.a,tick,'source')
        for a in (self.a[:2],np.full_like(self.a,np.nan),np.full_like(self.a,2)):
            with self.assertRaises(ValueError):self.bg.build(self.src,a,1,'source')
        for kw in ({'policy':'guess'},{'policy':'explicit'},{'allowed_mask':self.a},{'palette':[(1,2,3)]}):
            with self.assertRaises(ValueError):self.bg.build(self.src,self.a,1,'duotone',**kw)
        with self.assertRaises(ValueError):self.bg.build(self.src.astype(float),self.a,1,'source')
        with self.assertRaises(ValueError):self.bg.build(self.src,self.a,1,'bad')

    def test_grid_invalid_no_silent_wrap(self):
        for xx in (self.xx[:2],np.full_like(self.xx,np.inf),self.xx+500):
            with self.assertRaises(ValueError):ReferenceBackgroundRecipes(xx,self.yy)


if __name__=='__main__':unittest.main()
