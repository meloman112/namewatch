"""Ядро: кадры звука -> VAD -> детектор -> приглушение. Не зависит от микрофона, поэтому тестируется."""
from __future__ import annotations

from collections import deque

from .detector import Detector
from .ducker import Ducker
from .vad import FRAME_MS, Vad


class App:
    def __init__(self, vad: Vad, detector: Detector, ducker: Ducker, hangover_ms: int = 300,
                 hold_s: float = 4.0, max_hold_s: float = 30.0, preroll_frames: int = 10, log=print):
        self.vad, self.det, self.ducker = vad, detector, ducker
        self.hangover = max(1, hangover_ms // FRAME_MS)
        self.hold_s, self.max_hold_s = hold_s, max_hold_s
        self.log = log
        self._preroll: deque[bytes] = deque(maxlen=preroll_frames)  # хвост тишины перед фразой, чтобы не срезать начало
        self._in_speech = False
        self._silence = 0
        self._last_speech = 0.0
        self._last_hit = 0.0
        self._duck_start = 0.0

    def handle_frame(self, frame: bytes, now: float) -> None:
        events = []
        if self.vad.is_speech(frame):
            self._last_speech = now
            self._silence = 0
            if not self._in_speech:
                self._in_speech = True
                for f in self._preroll:
                    events += self.det.feed(f)
                self._preroll.clear()
            events += self.det.feed(frame)
        elif self._in_speech:
            events += self.det.feed(frame)
            self._silence += 1
            if self._silence >= self.hangover:
                events += self.det.flush()
                self._in_speech = False
        else:
            self._preroll.append(frame)
        for e in events:
            self._on_event(e, now)
        self.tick(now)

    def _on_event(self, e, now: float) -> None:
        if e.kind in ("hit", "confirm"):
            self._last_hit = now
            if not self.ducker.ducked:
                self._duck_start = now
                self.log(f"[{e.kind}] «{e.word}» conf={e.conf:.2f} -> приглушаю")
            self.ducker.duck()
        elif e.kind == "reject":
            self.log("[reject] ложная тревога -> возвращаю громкость")
            self.ducker.release()

    def tick(self, now: float) -> None:
        if not self.ducker.ducked:
            return
        last = max(self._last_hit, self._last_speech)  # пока вокруг говорят — держим приглушение
        if now - last > self.hold_s or now - self._duck_start > self.max_hold_s:
            self.log("тихо -> возвращаю громкость")
            self.ducker.release()
