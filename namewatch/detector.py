"""Детекторы имени. Все принимают int16 PCM 16 кГц моно и возвращают события."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Event:
    kind: str          # "hit" — похоже на имя (быстро), "confirm" — подтверждено, "reject" — ложная тревога
    word: str = ""
    conf: float = 1.0


class Detector(Protocol):
    def feed(self, pcm: bytes) -> list[Event]: ...
    def flush(self) -> list[Event]: ...


class VoskDetector:
    """Потоковый ASR, ограниченный грамматикой из имён + [unk].

    Работает с любым именем без обучения. Приглушаем уже по частичному результату
    (низкая задержка), а итог с уверенностью подтверждает или отменяет приглушение.
    """

    def __init__(self, names: list[str], model_path: str, min_conf: float = 0.7):
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        path = Path(model_path).expanduser()
        if not path.exists():
            raise SystemExit(f"Нет модели Vosk: {path}\nЗапустите scripts/download-model.sh")
        self._warn_unknown(path, names)
        self.names = set(names)
        self.min_conf = min_conf
        self._rec = KaldiRecognizer(Model(str(path)), 16000, json.dumps(names + ["[unk]"], ensure_ascii=False))
        self._rec.SetWords(True)
        self._hit = False

    @staticmethod
    def _warn_unknown(path: Path, names: list[str]) -> None:
        words = path / "graph" / "words.txt"
        if not words.exists():
            return
        vocab = {line.split()[0] for line in words.read_text(encoding="utf-8").splitlines() if line.strip()}
        missing = [n for n in names if n not in vocab]
        if missing:
            print(f"[namewatch] ВНИМАНИЕ: нет в словаре модели и не будут слышны: {missing}")

    def feed(self, pcm: bytes) -> list[Event]:
        if self._rec.AcceptWaveform(pcm):
            return self._final(json.loads(self._rec.Result()))
        if self._hit:
            return []
        for w in json.loads(self._rec.PartialResult()).get("partial", "").split():
            if w in self.names:
                self._hit = True
                return [Event("hit", w)]
        return []

    def flush(self) -> list[Event]:
        return self._final(json.loads(self._rec.FinalResult()))

    def _final(self, res: dict) -> list[Event]:
        found = [w for w in res.get("result", []) if w.get("word") in self.names]
        out: list[Event] = []
        if found:
            best = max(found, key=lambda w: w.get("conf", 0))
            if best.get("conf", 0) >= self.min_conf:
                if not self._hit:
                    out.append(Event("hit", best["word"], best["conf"]))
                out.append(Event("confirm", best["word"], best["conf"]))
            elif self._hit:
                out.append(Event("reject", best["word"], best.get("conf", 0)))
        elif self._hit:
            out.append(Event("reject"))
        self._hit = False
        return out


class OwwDetector:
    """openWakeWord: своя обученная модель слова. Быстрее и легче Vosk, но нужна модель (.onnx)."""

    CHUNK = 1280  # 80 мс — размер кадра openWakeWord

    def __init__(self, model_path: str, threshold: float = 0.5):
        import numpy as np
        from openwakeword.model import Model

        self._np = np
        self._model = Model(wakeword_models=[str(Path(model_path).expanduser())], inference_framework="onnx")
        self.threshold = threshold
        self._buf = b""
        self._hit = False

    def feed(self, pcm: bytes) -> list[Event]:
        self._buf += pcm
        out: list[Event] = []
        step = self.CHUNK * 2
        while len(self._buf) >= step:
            chunk, self._buf = self._buf[:step], self._buf[step:]
            scores = self._model.predict(self._np.frombuffer(chunk, dtype=self._np.int16))
            top = max(scores.values(), default=0.0)
            if top >= self.threshold and not self._hit:
                self._hit = True
                out += [Event("hit", "oww", top), Event("confirm", "oww", top)]
        return out

    def flush(self) -> list[Event]:
        self._buf = b""
        self._hit = False
        self._model.reset()
        return []


def build(cfg) -> Detector:
    if cfg.engine == "vosk":
        return VoskDetector(cfg.names, cfg.vosk_model, cfg.min_conf)
    if cfg.engine == "oww":
        if not cfg.oww_model:
            raise SystemExit("engine = 'oww', но [detector.oww] model_path пуст")
        return OwwDetector(cfg.oww_model, cfg.oww_threshold)
    raise SystemExit(f"Неизвестный engine: {cfg.engine}")
