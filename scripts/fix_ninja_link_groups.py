#!/usr/bin/env python3
"""Wrap static archives in linker groups in CMake's generated build.ninja.

Ladybird has a C++ <-> Rust static-link cycle: LibGfx uses libgfx_rust, while
the Rust crate calls back into LibGfx's extern "C" functions. With
BUILD_SHARED_LIBS=OFF, GNU ld cannot resolve that cycle from a single pass over
the archives and reports undefined `ladybird_gfx_*` references. Wrapping the
library list in --start-group/--end-group makes ld rescan it until resolved.
"""

from __future__ import annotations

import sys
from pathlib import Path

PREFIX = "  LINK_LIBRARIES = "


def main() -> int:
    ninja = Path(sys.argv[1] if len(sys.argv) > 1 else "build/build.ninja")
    lines = ninja.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    wrapped = 0
    for line in lines:
        if line.startswith(PREFIX):
            value = line[len(PREFIX) :].rstrip("\n")
            if ".a" in value and "--start-group" not in value:
                line = f"{PREFIX}-Wl,--start-group {value} -Wl,--end-group\n"
                wrapped += 1
        out.append(line)
    if wrapped == 0:
        print(
            f"[fix-ninja] ERROR: no LINK_LIBRARIES lines wrapped in {ninja}; "
            "the CMake/Ninja format may have changed",
            file=sys.stderr,
        )
        return 1
    ninja.write_text("".join(out), encoding="utf-8")
    print(f"[fix-ninja] wrapped {wrapped} link lines in linker groups")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
