import unittest
import numpy as np
from fx_core import DEFAULTS,transform,source_time
from fx_random import events,active


class RandomEffectsTests(unittest.TestCase):
    def setUp(self):
        self.p=dict(DEFAULTS,random_mode=True,start=0.,end=60.,random_seed=13,
                    zoom=True,shake=True,slow=True,rate_zoom=10,rate_shake=8,rate_slow=5)

    def test_reproducible_and_rate(self):
        a=events(self.p,'zoom')
        self.assertEqual(a,events(dict(self.p,zoom_amount=.9),'zoom'))
        self.assertEqual(len(a),10)
        self.assertEqual(len(events(dict(self.p,rate_zoom=20),'zoom')),20)
        self.assertNotEqual(a,events(dict(self.p,random_seed=14),'zoom'))
        self.assertEqual(events(dict(self.p,rate_zoom=0),'zoom'),())

    def test_bounds_gaps_and_durations(self):
        for kind in ('zoom','shake','slow'):
            previous=0
            for a,b in events(self.p,kind):
                self.assertGreaterEqual(a,previous)
                self.assertLessEqual(b,60)
                self.assertGreaterEqual(b-a,self.p['random_min']-1e-9)
                self.assertLessEqual(b-a,self.p['random_max']+1e-9)
                previous=b

    def test_disabled_and_independent(self):
        self.assertEqual(events(self.p,'flash'),())
        self.assertEqual(events(dict(self.p,zoom=False),'zoom'),())
        self.assertEqual(events(self.p,'zoom'),events(dict(self.p,rate_shake=25),'zoom'))
        self.assertEqual(events(dict(self.p,end=.05),'zoom'),())

    def test_timewarp_continuity_and_monotonicity(self):
        ts=np.linspace(0,60,20001)
        mapped=np.array([source_time(t,self.p) for t in ts])
        self.assertTrue(np.all(np.diff(mapped)>0))
        for a,b in events(self.p,'slow'):
            self.assertAlmostEqual(source_time(a,self.p),a)
            self.assertAlmostEqual(source_time(b,self.p),b)
        self.assertEqual(source_time(60,self.p),60)

    def test_render_repeatable_and_inactive(self):
        frame=np.random.default_rng(2).integers(0,256,(90,160,3),dtype=np.uint8)
        p=dict(self.p,slow=False)
        a,b=events(p,'zoom')[0];t=(a+b)/2
        first=transform(frame,t,t,p)
        np.testing.assert_array_equal(first,transform(frame,t,t,p))
        self.assertFalse(np.array_equal(first,frame))
        np.testing.assert_array_equal(transform(frame,60,60,p),frame)
        np.testing.assert_array_equal(transform(frame,2,2,dict(p,zoom=False,shake=False)),frame)


if __name__=='__main__':unittest.main()
