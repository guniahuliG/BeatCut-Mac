import unittest
import threading
import numpy as np
from studio_engine import timeline, check, Cancelled


class PlanningTests(unittest.TestCase):
    def test_limits_and_repeatability(self):
        ts=np.arange(.5,30,.5); ws=np.ones(len(ts))
        for seed in range(100):
            args=(ts,ws,900,30)
            a=timeline(*args,np.random.default_rng(seed),.7,.8,.35,4)
            b=timeline(*args,np.random.default_rng(seed),.7,.8,.35,4)
            self.assertEqual(a,b)
            self.assertEqual(a[0][0],0); self.assertEqual(a[0][-1],900)
            self.assertGreaterEqual(min(np.diff(a[0])),11)
            self.assertLessEqual(max(np.diff(a[0])),120)

    def test_no_accents(self):
        cuts,fallback=timeline([],[],900,30,np.random.default_rng(1),.5,.5,.35,4)
        self.assertTrue(fallback)
        self.assertEqual(cuts[-1],900)

    def test_short_track(self):
        cuts,_=timeline([],[],5,30,np.random.default_rng(1),.5,.5,.35,4)
        self.assertEqual(cuts,[0,5])

    def test_cancel(self):
        event=threading.Event();event.set()
        with self.assertRaises(Cancelled):check(event)


if __name__=='__main__':unittest.main()
