#!/usr/bin/env python3
"""Print compiled fast-path KVS JSON for a redirect config file."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from compiler import compile_text


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: compile_fastpath.py path/to/redirects.conf", file=sys.stderr)
        return 2
    result = compile_text(Path(sys.argv[1]).read_text())
    print(json.dumps(result.to_external_result(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
