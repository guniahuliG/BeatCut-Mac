"""No flashing images are displayed by these numerical tests."""
import unittest
import math
import cv2
import numpy as np
from fx_core import DEFAULTS, source_time, envelope, transform, smooth_track
from fx_media import detector, Reader


class EffectsTests(unittest.TestCase):
    def setUp(self):
        self.p=dict(DEFAULTS,start=1.,end=5.)
        rng=np.random.default_rng(3)
        self.frame=rng.integers(0,256,(90,160,3),dtype=np.uint8)

    def test_off_exactly_preserves_pixels(self):
        self.assertFalse(DEFAULTS['flash'])
        np.testing.assert_array_equal(transform(self.frame,2,2,self.p),self.frame)

    def test_scope(self):
        p=dict(self.p,zoom=True,shake=True,flash=True)
        for t in (0.,.99,5.,6.):
            self.assertEqual(envelope(t,p),0)
            np.testing.assert_array_equal(transform(self.frame,t,t,p),self.frame)

    def test_timewarp_monotonic_endpoints(self):
        for speed in (.2,.5,1.):
            p=dict(self.p,slow=True,speed=speed)
            ts=np.linspace(0,6,6001);mapped=np.array([source_time(t,p) for t in ts])
            self.assertTrue(np.all(np.diff(mapped)>0))
            self.assertAlmostEqual(source_time(1,p),1)
            self.assertAlmostEqual(source_time(5,p),5)
            self.assertAlmostEqual(np.min(np.diff(mapped)/.001),speed,places=4)
            self.assertTrue(np.all(mapped<=ts+1e-12))

    def test_repeatable_shake_and_zoom(self):
        p=dict(self.p,zoom=True,shake=True)
        a=transform(self.frame,2.3,2.3,p);b=transform(self.frame,2.3,2.3,p)
        np.testing.assert_array_equal(a,b)
        self.assertGreater(np.abs(a.astype(float)-self.frame).mean(),5)
        self.assertEqual(a.shape,self.frame.shape)

    def test_white_flash_formula(self):
        p=dict(self.p,flash=True,flash_hz=2.,flash_alpha=.5,fade=0)
        frame=np.zeros_like(self.frame)
        on=transform(frame,2.,2.,p);off=transform(frame,2.2,2.2,p)
        self.assertTrue(np.all(on==128));self.assertTrue(np.all(off==0))

    def test_face_translation(self):
        frame=np.zeros((100,200,3),np.uint8);frame[48:53,38:43]=255
        track=np.tile([.2,.5,.14,0,1,0],(100,1))
        p=dict(self.p,face=True,crop=1,face_roll=False)
        out=transform(frame,2,2,p,track,30)
        # Reflected borders can duplicate a bright mark; check the target itself.
        self.assertEqual(int(out[38,100,0]),255)
        self.assertEqual(int(out[50,40,0]),0)

    def test_smoothing_does_not_cross_cut(self):
        raw=np.zeros((20,6));raw[:10,0]=.2;raw[10:,0]=.8;raw[10:,5]=1
        out=smooth_track(raw,.5,30)
        np.testing.assert_allclose(out[:10,0],.2);np.testing.assert_allclose(out[10:,0],.8)
        np.testing.assert_array_equal(out[:,5],raw[:,5])

    def test_model_loads_locally(self):
        face=detector();face.setInputSize((320,320))
        _,result=face.detect(np.zeros((320,320,3),np.uint8))
        self.assertIsNone(result)


if __name__=='__main__':unittest.main()
