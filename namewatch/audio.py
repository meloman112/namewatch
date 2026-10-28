from __future__ import annotations

import queue

from .vad import FRAME_SAMPLES, RATE


def list_devices() -> None:
    import sounddevice as sd

    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"{i:3d}  {d['name']}  (входов: {d['max_input_channels']})")


def _resolve(device: str):
    import sounddevice as sd

    if not device:
        return None
    if device.isdigit():
        return int(device)
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and device.lower() in d["name"].lower():
            return i
    raise SystemExit(f"Устройство «{device}» не найдено. Список: namewatch devices")


def frames(device: str = ""):
    """Бесконечный генератор кадров по 30 мс (int16, 16 кГц, моно)."""
    import sounddevice as sd

    q: queue.Queue[bytes] = queue.Queue(maxsize=200)

    def cb(indata, n, t, status):
        try:
            q.put_nowait(bytes(indata))
        except queue.Full:  # лучше потерять кадр, чем копить задержку
            pass

    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME_SAMPLES,
                           device=_resolve(device), callback=cb):
        while True:
            yield q.get()
