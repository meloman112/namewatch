import unittest

from namewatch.app import App
from namewatch.detector import Event
from namewatch.ducker import DryBackend, Ducker

SPEECH, SILENCE = b"S" * 960, b"_" * 960


class FakeVad:
    def is_speech(self, frame):
        return frame == SPEECH


class ScriptedDetector:
    """Выдаёт заранее заданные события на N-й кадр речи, на flush — финальные."""

    def __init__(self, on_feed=None, on_flush=None):
        self.on_feed, self.on_flush, self.n = on_feed or {}, on_flush or [], 0

    def feed(self, pcm):
        self.n += 1
        return self.on_feed.get(self.n, [])

    def flush(self):
        return self.on_flush


def run(det, script, hold_s=0.5):
    be = DryBackend(80)
    d = Ducker(be, level=25, down_ms=40, up_ms=80, step_ms=10)
    app = App(FakeVad(), det, d, hangover_ms=90, hold_s=hold_s, log=lambda m: None)
    t = 0.0
    import time
    for kind, secs in script:
        for _ in range(int(secs / 0.03)):
            app.handle_frame(SPEECH if kind == "S" else SILENCE, t)
            t += 0.03
        time.sleep(secs * 0.3)  # дать потоку ducker отработать
    return be, d


class Tests(unittest.TestCase):
    def test_hit_ducks_then_restores(self):
        det = ScriptedDetector({2: [Event("hit", "вася")]}, [Event("confirm", "вася", 0.9)])
        be, d = run(det, [("S", 0.3), ("_", 1.0), ("_", 1.5)])
        import time; time.sleep(0.4)
        self.assertEqual(min(be.calls), 20)          # 80 * 25%
        self.assertEqual(be.volume, 80)              # вернулась исходная
        self.assertFalse(d.ducked)
        d.close()

    def test_reject_restores_immediately(self):
        det = ScriptedDetector({2: [Event("hit", "вася")]}, [Event("reject")])
        be, d = run(det, [("S", 0.3), ("_", 0.4)], hold_s=60)
        import time; time.sleep(0.3)
        self.assertEqual(be.volume, 80)
        d.close()

    def test_no_event_no_change(self):
        be, d = run(ScriptedDetector(), [("S", 0.3), ("_", 0.5)])
        self.assertEqual(be.calls, [])
        d.close()

    def test_close_restores_volume(self):
        be = DryBackend(60)
        d = Ducker(be, level=10, down_ms=20, step_ms=5)
        d.duck()
        import time; time.sleep(0.2)
        self.assertLess(be.volume, 20)
        d.close()
        self.assertEqual(be.volume, 60)


if __name__ == "__main__":
    unittest.main()
