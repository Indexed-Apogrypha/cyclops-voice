import time
import threading
import numpy as np
from cyclops_voice.player import Player, AudioSink

class FakeSink(AudioSink):
    def __init__(self):
        self.frames = []
        self.closed = False
    def write(self, block: np.ndarray) -> None:
        self.frames.append(block.copy())
    def close(self) -> None:
        self.closed = True

def _buffers(n_buffers=3, n=2205):
    for i in range(n_buffers):
        yield (np.ones((n, 2), dtype=np.float32) * (i + 1) * 0.01)

def test_plays_all_buffers():
    sink = FakeSink()
    p = Player(sample_rate=22050, sink=sink)
    p.submit("job1", _buffers())
    p.wait_idle(timeout=5)
    total = sum(len(f) for f in sink.frames)
    assert total == 3 * 2205
    assert p.state == "idle"

def test_stop_halts_playback():
    sink = FakeSink()
    p = Player(sample_rate=22050, sink=sink)
    def slow():
        for i in range(50):
            time.sleep(0.01)
            yield np.ones((2205, 2), dtype=np.float32) * 0.01
    p.submit("job2", slow())
    time.sleep(0.05)
    p.stop()
    p.wait_idle(timeout=5)
    assert p.state == "idle"
    assert sum(len(f) for f in sink.frames) < 50 * 2205  # didn't play everything

def test_skip_moves_to_idle_when_queue_empty():
    sink = FakeSink()
    p = Player(sample_rate=22050, sink=sink)
    p.submit("job3", _buffers(n_buffers=10))
    p.skip()
    p.wait_idle(timeout=5)
    assert p.state == "idle"

def test_set_gain_scales_output():
    sink = FakeSink()
    p = Player(sample_rate=22050, sink=sink, gain=0.5)
    p.submit("jobg", (b for b in [np.ones((1024, 2), dtype=np.float32)]))
    p.wait_idle(timeout=5)
    assert sink.frames and np.allclose(sink.frames[0], 0.5)

def test_set_sink_swaps_output():
    a, b = FakeSink(), FakeSink()
    p = Player(sample_rate=22050, sink=a)
    p.set_sink(b)
    p.submit("jobs", _buffers(n_buffers=2))
    p.wait_idle(timeout=5)
    assert sum(len(f) for f in b.frames) > 0
    assert a.frames == []  # nothing went to the old sink after swap
