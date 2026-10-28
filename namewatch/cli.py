from __future__ import annotations

import argparse
import signal
import sys
import time
import wave

from . import config as cfgmod
from .app import App
from .detector import build
from .ducker import DryBackend, Ducker, PactlBackend
from .vad import FRAME_BYTES, FRAME_MS, Vad


def _make(cfg, dry: bool = False) -> tuple[App, Ducker]:
    backend = DryBackend() if dry else PactlBackend()
    ducker = Ducker(backend, cfg.level, cfg.down_ms, cfg.up_ms)
    app = App(Vad(cfg.vad_aggr), build(cfg), ducker, cfg.hangover_ms, cfg.hold_s, cfg.max_hold_s)
    return app, ducker


def cmd_run(a) -> None:
    from .audio import frames

    cfg = cfgmod.load(a.config)
    app, ducker = _make(cfg)
    print(f"namewatch: engine={cfg.engine} vad={app.vad.kind} names={cfg.names}. Ctrl+C для выхода.")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # чтобы finally вернул громкость
    try:
        for frame in frames(cfg.device):
            app.handle_frame(frame, time.monotonic())
    except KeyboardInterrupt:
        pass
    finally:
        ducker.close()


def cmd_wav(a) -> None:
    """Прогнать запись через ту же цепочку без микрофона и без изменения громкости."""
    cfg = cfgmod.load(a.config)
    app, ducker = _make(cfg, dry=True)
    with wave.open(a.file, "rb") as w:
        if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (16000, 1, 2):
            raise SystemExit("Нужен wav 16 кГц, моно, 16 бит: ffmpeg -i in.mp3 -ar 16000 -ac 1 out.wav")
        data = w.readframes(w.getnframes())
    t = 0.0
    for i in range(0, len(data) - FRAME_BYTES + 1, FRAME_BYTES):
        app.log = lambda m, t=t: print(f"{t:6.2f}s {m}")
        app.handle_frame(data[i:i + FRAME_BYTES], t)
        t += FRAME_MS / 1000
    time.sleep(0.2)
    ducker.close()


def cmd_test_duck(a) -> None:
    cfg = cfgmod.load(a.config) if a.config else cfgmod.Config()
    d = Ducker(PactlBackend(), cfg.level, cfg.down_ms, cfg.up_ms)
    try:
        print("Приглушаю на 3 секунды...")
        d.duck()
        time.sleep(3)
        d.release()
        time.sleep(cfg.up_ms / 1000 + 0.5)
    finally:
        d.close()
    print("Готово, громкость возвращена.")


def main() -> None:
    p = argparse.ArgumentParser(prog="namewatch")
    p.add_argument("-c", "--config", help="путь к config.toml")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run", help="слушать микрофон").set_defaults(fn=cmd_run)
    sub.add_parser("devices", help="список микрофонов").set_defaults(fn=lambda a: __import__("namewatch.audio", fromlist=["x"]).list_devices())
    sub.add_parser("test-duck", help="проверить приглушение").set_defaults(fn=cmd_test_duck)
    w = sub.add_parser("wav", help="проверить на записи")
    w.add_argument("file")
    w.set_defaults(fn=cmd_wav)
    a = p.parse_args()
    a.fn(a)
