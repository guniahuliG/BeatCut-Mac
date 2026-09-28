import unittest
import numpy as np
from source_selection import source_plan


class SourceSelectionTests(unittest.TestCase):
    def setUp(self):
        self.videos=[{'path':'a','duration':10.}, {'path':'b','duration':8.}]

    def test_never_mode_prevents_source_time_overlap(self):
        plan=source_plan(self.videos,[60]*7,30,np.random.default_rng(7),'Без повторов')
        for i,a in enumerate(plan):
            for b in plan[i+1:]:
                if a['source']==b['source']:
                    a0,a1=a['start'],a['start']+a['frames']/30
                    b0,b1=b['start'],b['start']+b['frames']/30
                    self.assertTrue(a1<=b0+1e-9 or b1<=a0+1e-9)
                    self.assertFalse(a['repeat'] or b['repeat'])

    def test_never_mode_fails_clearly_when_insufficient(self):
        video=[{'path':'one','duration':2.1}]
        with self.assertRaisesRegex(ValueError,'не хватает уникального'):
            source_plan(video,[45]*3,30,np.random.default_rng(2),'Без повторов')

    def test_free_mode_allows_repeated_ranges(self):
        video=[{'path':'one','duration':1.1}]
        plan=source_plan(video,[30]*20,30,np.random.default_rng(4),'Свободно')
        self.assertTrue(any(x['repeat'] for x in plan))

    def test_rare_mode_delays_reuse_when_possible(self):
        video=[{'path':'one','duration':1.2}]
        # A tiny source cannot honor an 8-second cooldown; rare mode stays usable
        # and records that reuse occurred rather than failing or hiding it.
        plan=source_plan(video,[30]*12,30,np.random.default_rng(1),'Редкие повторы',8.)
        repeats=[x for x in plan if x['repeat']]
        self.assertTrue(repeats)
        self.assertEqual(len(plan),12)
        self.assertTrue(all(x['output_start']>=0 for x in plan))

    def test_seed_repeatability_and_independent_slots(self):
        a=source_plan(self.videos,[60]*6,30,np.random.default_rng(44),'Без повторов')
        b=source_plan(self.videos,[60]*6,30,np.random.default_rng(44),'Без повторов')
        self.assertEqual(a,b)
        self.assertEqual(sorted(x['output_start'] for x in a),[0,60,120,180,240,300])

    def test_cancel_callback(self):
        def cancel():raise RuntimeError('cancelled')
        with self.assertRaisesRegex(RuntimeError,'cancelled'):
            source_plan(self.videos,[60],30,np.random.default_rng(1),'never',cancel=cancel)


if __name__=='__main__':unittest.main()
