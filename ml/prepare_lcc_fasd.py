"""Arrange the LCC-FASD dataset into train/test live/spoof folders.

LCC-FASD ships as one flat image folder plus four protocol files that name
the official, subject-independent split::

    CLIENT_TRAIN.txt   / CLIENT_TEST.txt     -> live  (genuine faces)
    IMPOSTER_TRAIN.txt / IMPOSTER_TEST.txt   -> spoof (print / replay)

Each protocol line is a ``/kaggle/...`` path; only its basename matters.
This links every listed image into ``data/antispoof/{train,test}/{live,
spoof}`` so ml/train_antispoof.py can consume it. Reusing the official
split keeps a subject out of both train and test.

Run from the repo root::

    python ml/prepare_lcc_fasd.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Protocol file -> (split, class subfolder).
_PROTOCOLS = {
    "CLIENT_TRAIN.txt": ("train", "live"),
    "CLIENT_TEST.txt": ("test", "live"),
    "IMPOSTER_TRAIN.txt": ("train", "spoof"),
    "IMPOSTER_TEST.txt": ("test", "spoof"),
}


def _clear_links(directory: Path) -> None:
    """Remove existing symlinks so the arrangement is idempotent."""
    for entry in directory.iterdir():
        if entry.is_symlink():
            entry.unlink()


def arrange(source: Path, dest: Path) -> dict[tuple[str, str], int]:
    """Link images into ``dest`` per the LCC-FASD protocol files.

    Args:
        source: The flat LCC-FASD image folder holding the protocol files.
        dest: The ``data/antispoof`` root receiving the split folders.

    Returns:
        A ``{(split, class): linked_count}`` summary.

    Raises:
        FileNotFoundError: If a protocol file is missing.
    """
    for split in ("train", "test"):
        for cls in ("live", "spoof"):
            target = dest / split / cls
            target.mkdir(parents=True, exist_ok=True)
            _clear_links(target)

    counts: dict[tuple[str, str], int] = {}
    for protocol, (split, cls) in _PROTOCOLS.items():
        listing = source / protocol
        if not listing.exists():
            raise FileNotFoundError(f"Missing protocol file: {listing}")
        target = dest / split / cls
        linked = 0
        for line in listing.read_text().splitlines():
            name = line.strip().rsplit("/", 1)[-1]
            if not name:
                continue
            image = source / name
            if not image.exists():
                continue
            (target / name).symlink_to(image.resolve())
            linked += 1
        counts[(split, cls)] = linked
    return counts


def main() -> None:
    """Parse arguments and arrange the dataset."""
    default_source = Path("data/antispoof/LCC_FASD - AntiSpoofing")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=default_source,
        help="Flat LCC-FASD folder (with the CLIENT/IMPOSTER .txt files).",
    )
    parser.add_argument(
        "--dest", type=Path, default=Path("data/antispoof"),
        help="Destination antispoof root.",
    )
    args = parser.parse_args()

    counts = arrange(args.source, args.dest)
    for (split, cls), count in sorted(counts.items()):
        print(f"{split}/{cls}: {count} images")


if __name__ == "__main__":
    main()
