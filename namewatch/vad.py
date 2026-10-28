"""Детектор речи: отсекает тишину, чтобы тяжёлая модель работала только на голосе."""
from __future__ import annotations

import array
import math

try:
    import webrtcvad
except ImportError:  # запасной вариант без зависимостей
    webrtcvad = None

RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = RATE * FRAME_MS // 1000  # 480
FRAME_BYTES = FRAME_SAMPLES * 2


class EnergyVad:
    """Порог по громкости с адаптивной оценкой шума."""

    def __init__(self, ratio: float = 3.0, min_rms: float = 250.0):
        self.floor = 200.0
        self.ratio = ratio
        self.min_rms = min_rms

    def is_speech(self, frame: bytes) -> bool:
        s = array.array("h", frame)
        rms = math.sqrt(sum(x * x for x in s) / len(s)) if s else 0.0
        speech = rms > max(self.floor * self.ratio, self.min_rms)
        if not speech:  # шум подстраиваем только по тишине
            self.floor = 0.95 * self.floor + 0.05 * rms
        return speech


class Vad:
    def __init__(self, aggressiveness: int = 2):
        self._impl = webrtcvad.Vad(aggressiveness) if webrtcvad else None
        self._energy = EnergyVad()

    @property
    def kind(self) -> str:
        return "webrtc" if self._impl else "energy"

    def is_speech(self, frame: bytes) -> bool:
        if self._impl:
            return self._impl.is_speech(frame, RATE)
        return self._energy.is_speech(frame)
