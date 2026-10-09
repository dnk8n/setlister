#!/usr/bin/env python3
"""Refuse rich media (audio, video, images) anywhere except docs/.

Used by pre-commit (on staged files) and CI (on the whole tree). Exit code 1 lists offenders.
Usage: check_no_media.py [FILE ...]   (no args = every file tracked by git)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import PurePosixPath

MEDIA = {
    # audio
    ".wav",
    ".aif",
    ".aiff",
    ".flac",
    ".mp3",
    ".m4a",
    ".aac",
    ".ogg",
    ".opus",
    ".wma",
    ".alac",
    # video
    ".mp4",
    ".mkv",
    ".mov",
    ".webm",
    ".avi",
    ".m4v",
    ".flv",
    # images
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".svg",
    ".ico",
}
ALLOWED_PREFIX = "docs/"


def offenders(paths: list[str]) -> list[str]:
    return [
        p
        for p in paths
        if PurePosixPath(p).suffix.lower() in MEDIA and not p.startswith(ALLOWED_PREFIX)
    ]


def main(argv: list[str]) -> int:
    paths = (
        argv
        or subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=True
        ).stdout.splitlines()
    )
    bad = offenders(paths)
    for p in bad:
        print(f"rich media outside {ALLOWED_PREFIX}: {p}", file=sys.stderr)
    if bad:
        print(
            "Media belongs on your disk (media/ is gitignored) or, for documentation, in docs/.",
            file=sys.stderr,
        )
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
