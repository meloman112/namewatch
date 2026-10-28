from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

DEFAULT_PATH = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "namewatch" / "config.toml"


@dataclass
class Config:
    device: str = ""
    engine: str = "vosk"
    names: list[str] = field(default_factory=list)
    min_conf: float = 0.7
    vosk_model: str = "~/.local/share/namewatch/vosk-model-small-ru-0.22"
    oww_model: str = ""
    oww_threshold: float = 0.5
    vad_aggr: int = 2
    hangover_ms: int = 300
    backend: str = "pactl"
    level: int = 15
    down_ms: int = 150
    up_ms: int = 1200
    hold_s: float = 4.0
    max_hold_s: float = 30.0


def load(path: str | Path | None = None) -> Config:
    p = Path(path).expanduser() if path else DEFAULT_PATH
    if not p.exists():
        raise SystemExit(f"Нет конфига: {p}\nСкопируйте config.example.toml туда и поправьте имена.")
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    a, d, v, k = (raw.get(s, {}) for s in ("audio", "detector", "vad", "duck"))
    vosk, oww = d.get("vosk", {}), d.get("oww", {})
    c = Config(
        device=str(a.get("device", "")),
        engine=d.get("engine", "vosk"),
        names=[n.strip().lower() for n in d.get("names", []) if n.strip()],
        min_conf=float(d.get("min_conf", 0.7)),
        vosk_model=vosk.get("model_path", Config.vosk_model),
        oww_model=oww.get("model_path", ""),
        oww_threshold=float(oww.get("threshold", 0.5)),
        vad_aggr=int(v.get("aggressiveness", 2)),
        hangover_ms=int(v.get("hangover_ms", 300)),
        backend=k.get("backend", "pactl"),
        level=int(k.get("level", 15)),
        down_ms=int(k.get("down_ms", 150)),
        up_ms=int(k.get("up_ms", 1200)),
        hold_s=float(k.get("hold_s", 4.0)),
        max_hold_s=float(k.get("max_hold_s", 30.0)),
    )
    if c.engine == "vosk" and not c.names:
        raise SystemExit("В [detector] names пусто: укажите хотя бы одно имя.")
    return c
