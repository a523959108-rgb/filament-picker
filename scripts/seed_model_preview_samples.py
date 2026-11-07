"""Generate fake gallery data only; never open or scan source model files."""

import argparse
from pathlib import Path

from filament_picker.model_samples import seed_samples
from filament_picker.models import models_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=models_root())
    args = parser.parse_args()
    count = seed_samples(args.root)
    print(f"samples={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
