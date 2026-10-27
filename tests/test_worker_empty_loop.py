import unittest

from gui.bus import Bus
from gui.worker import PipelineWorker


class EmptyLoopTest(unittest.TestCase):
    def test_empty_infinite_loop_is_skipped_not_spun(self):
        bus = Bus()
        worker = PipelineWorker(None, None, {}, [], bus)
        worker._run_stage = lambda node: None
        # would never return before the fix
        worker._run_nodes([{"type": "loop", "count": 0, "children": []}])
        prints = Bus.drain(bus.prints)
        self.assertTrue(any("no stages inside it" in p for p in prints))

    def test_has_stage_looks_through_nested_loops(self):
        self.assertFalse(PipelineWorker._has_stage([]))
        self.assertFalse(PipelineWorker._has_stage(
            [{"type": "loop", "children": [{"type": "loop", "children": []}]}]))
        self.assertTrue(PipelineWorker._has_stage(
            [{"type": "loop", "children": [{"type": "stage", "experiment": "x"}]}]))


if __name__ == "__main__":
    unittest.main()
