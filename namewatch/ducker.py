"""Плавное изменение громкости. Бэкенд pactl работает и с PulseAudio, и с PipeWire."""
from __future__ import annotations

import re
import subprocess
import threading
from typing import Protocol


class Backend(Protocol):
    def get(self) -> int: ...
    def set(self, percent: int) -> None: ...


class PactlBackend:
    SINK = "@DEFAULT_SINK@"

    def get(self) -> int:
        out = subprocess.run(["pactl", "get-sink-volume", self.SINK], capture_output=True, text=True, check=True).stdout
        m = re.search(r"(\d+)%", out)
        if not m:
            raise RuntimeError(f"Не разобрал вывод pactl: {out!r}")
        return int(m.group(1))

    def set(self, percent: int) -> None:
        subprocess.run(["pactl", "set-sink-volume", self.SINK, f"{max(0, percent)}%"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class DryBackend:
    """Ничего не трогает; для проверки на wav-файлах."""

    def __init__(self, volume: int = 100):
        self.volume = volume
        self.calls: list[int] = []

    def get(self) -> int:
        return self.volume

    def set(self, percent: int) -> None:
        self.volume = percent
        self.calls.append(percent)


class Ducker:
    def __init__(self, backend: Backend, level: int = 15, down_ms: int = 150, up_ms: int = 1200, step_ms: int = 40):
        self.backend = backend
        self.level = level
        self.down_ms, self.up_ms, self.step_ms = down_ms, up_ms, step_ms
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = False
        self._orig: int | None = None
        self._cur = 0.0
        self._target = 0.0
        self.ducked = False
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def duck(self) -> None:
        with self._lock:
            if not self.ducked:
                self._orig = self.backend.get()
                self._cur = float(self._orig)
                self.ducked = True
            self._target = self._orig * self.level / 100.0
        self._wake.set()

    def release(self) -> None:
        with self._lock:
            if not self.ducked:
                return
            self._target = float(self._orig)
        self._wake.set()

    def close(self) -> None:
        """Вернуть исходную громкость и остановиться."""
        self._stop = True
        self._wake.set()
        self._t.join(timeout=2)
        with self._lock:
            if self.ducked and self._orig is not None:
                self.backend.set(self._orig)
                self.ducked = False

    def _run(self) -> None:
        while not self._stop:
            self._wake.wait()
            self._wake.clear()
            while not self._stop:
                with self._lock:
                    if not self.ducked:
                        break
                    span = max(1.0, self._orig * (100 - self.level) / 100.0)
                    ms = self.down_ms if self._target < self._cur else self.up_ms
                    step = span * self.step_ms / max(ms, 1)
                    if abs(self._target - self._cur) <= step:
                        self._cur = self._target
                    else:
                        self._cur += step if self._target > self._cur else -step
                    value, done = round(self._cur), self._cur == self._target
                    if done and self._target == self._orig:
                        self.ducked = False
                try:
                    self.backend.set(value)
                except Exception as e:  # не роняем поток из-за сбоя pactl
                    print(f"[namewatch] не смог поставить громкость: {e}")
                if done:
                    break
                self._wake.wait(self.step_ms / 1000)
                self._wake.clear()
