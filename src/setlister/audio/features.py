"""Decode audio with ffmpeg and compute light-weight spectral features.

Everything runs at a low sample rate (default 11 025 Hz, mono) so a two-hour set fits in a
few hundred MB of RAM and analyses in seconds on a laptop CPU.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

HOP = 512
N_MELS = 32


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def decode(
    path: str | Path, sr: int = 11025, *, start: float = 0.0, duration: float | None = None
) -> np.ndarray:
    """Decode any format ffmpeg understands to mono float32 at `sr`."""
    cmd = ["ffmpeg", "-nostdin", "-loglevel", "error"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(path)]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    out = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(out, dtype=np.float32).copy()


@dataclass
class Features:
    """Log-mel spectrogram, shape (N_MELS, frames)."""

    logmel: np.ndarray
    sr: int

    @property
    def fps(self) -> float:
        return self.sr / HOP

    @property
    def duration(self) -> float:
        return self.logmel.shape[1] / self.fps

    def save(self, path: Path) -> None:
        np.savez_compressed(path, logmel=self.logmel, sr=self.sr)

    @classmethod
    def load(cls, path: Path) -> Features:
        d = np.load(path)
        return cls(d["logmel"], int(d["sr"]))


def logmel(y: np.ndarray, sr: int) -> Features:
    S = librosa.feature.melspectrogram(
        y=y, sr=sr, n_fft=2048, hop_length=HOP, n_mels=N_MELS, fmax=min(5000, sr / 2)
    )
    return Features(np.log1p(1000 * S).astype(np.float32), sr)


def features_for(path: str | Path, sr: int = 11025, cache_dir: Path | None = None) -> Features:
    """Features for a file, cached by path + size + mtime."""
    p = Path(path)
    if cache_dir:
        st = p.stat()
        ident = f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}|{sr}".encode()
        key = hashlib.sha1(ident).hexdigest()[:16]
        cache = cache_dir / "features" / f"{key}.npz"
        if cache.exists():
            return Features.load(cache)
    f = logmel(decode(p, sr), sr)
    if cache_dir:
        cache.parent.mkdir(parents=True, exist_ok=True)
        f.save(cache)
    return f
