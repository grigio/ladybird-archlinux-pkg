# Upstream technical feedback: static link cycle between LibGfx and libgfx_rust

## Status

Draft. This is technical feedback for Ladybird maintainers. It will be finalized
after the CI build that applies the workaround completes successfully.

## Submission route

Ladybird's `CONTRIBUTING.md` states that the project does not accept pull
requests from non-maintainers. Its issue policy explicitly excludes build
problems and support requests; those belong in the `#build-problems` channel on
the project Discord server. Consequently, this report is written as technical
feedback for that channel rather than as a pull request or a GitHub issue.

The text uses American English, ISO 8601 dates, and metric units, and avoids
contractions and idioms, in accordance with the Ladybird human language policy.

## Environment

- Upstream tag: `2026.47.7`
- Build configuration: `BUILD_SHARED_LIBS=OFF`, `LADYBIRD_VCPKG_TYPE=distribution`,
  GCC, link-time optimization disabled (the combination used by the Arch Linux
  AUR packaging recipe)
- Rust toolchain: `1.98.0`, as pinned by `rust-toolchain.toml`
- Linker: GNU ld 2.44

## Observed problem

The build fails while linking several executables, beginning with
`libexec/ImageDecoder`. The linker reports approximately one hundred undefined
references to `ladybird_gfx_*` symbols, for example:

```
/usr/bin/ld: cargo/build/x86_64-unknown-linux-gnu/release/liblibgfx_rust.a(...):
  undefined reference to `ladybird_gfx_font_contains_glyph'
```

The corresponding definitions are compiled into `liblagom-gfx.a` from C++ source
files such as `Libraries/LibGfx/Font/Font.cpp`.

## Root cause

`Libraries/LibGfx/CMakeLists.txt` links the C++ library against the Rust crate:

```cmake
import_rust_crate(... CRATE_NAME libgfx_rust ...)
target_link_libraries(LibGfx PRIVATE libgfx_rust)
```

The Rust crate declares the `ladybird_gfx_*` functions as `extern "C"` callbacks
and calls them from Rust code. This creates a circular static dependency:

```
liblagom-gfx.a  --->  liblibgfx_rust.a  --->  liblagom-gfx.a
```

`import_rust_crate()` creates an IMPORTED CMake target. CMake's static-library
cycle detection does not traverse the dependencies of IMPORTED targets in the
same way as it does for regular targets. As a result, the generated link line
places `liblagom-gfx.a` before `liblibgfx_rust.a` and does not repeat it. GNU ld
resolves static archives in a single forward pass, so the callbacks are never
extracted from `liblagom-gfx.a`.

The upstream `Distribution` preset does not expose this failure because it
enables link-time optimization, which resolves symbols across the entire link
unit. Builds with `BUILD_SHARED_LIBS=OFF` and link-time optimization disabled
are affected.

## Verified workaround

Wrap the library list of each link edge in linker group flags, which instruct
GNU ld to rescan the archives until no new undefined references appear:

```
-Wl,--start-group <all libraries> -Wl,--end-group
```

In this packaging repository, `scripts/fix_ninja_link_groups.py` applies that
transformation to every `LINK_LIBRARIES` line in the generated `build.ninja`
immediately before `cmake --build`. The transformation resolves the undefined
`ladybird_gfx_*` references.

## Proposed upstream fixes

Two options are offered for maintainer consideration.

### Option 1: Express the cycle in CMake

CMake 3.24 and later provide the `LINK_GROUP` generator expression and the
`RESCAN` link feature, which emit linker group flags portably for GNU ld and
lld. The affected link edges could express the cyclic dependency explicitly,
for example:

```cmake
target_link_libraries(<executable> PRIVATE
    "$<LINK_GROUP:RESCAN,lagom-gfx,libgfx_rust>"
)
```

This would require identifying every target that links the affected libraries,
or introducing a reusable interface target that carries the grouped link item.
The change is limited to build system files.

### Option 2: Remove the cycle

Move the `extern "C"` callback implementations out of `LibGfx` into a small
static library that both `LibGfx` and `libgfx_rust` link against. This removes
the circular dependency at its source and avoids the linker-group performance
cost, but requires moving code across several source files.

### Option 3: Document the supported configuration

If static builds without link-time optimization are not intended to be
supported, state this explicitly in `Documentation/BuildInstructionsLadybird.md`
or `Documentation/AdvancedBuildInstructions.md`. Distribution packagers should
then be directed to use the `Distribution` preset, which selects Clang and
link-time optimization and is known to link successfully.

## Reproduction

The failure reproduced consistently in GitHub Actions with the following
configure step:

```bash
cmake --preset Release -B build -S ladybird \
  -DBUILD_SHARED_LIBS=OFF \
  -DCMAKE_BUILD_TYPE=Release \
  -DLADYBIRD_VERSION=2026.47.7 \
  -DENABLE_LTO_FOR_RELEASE=OFF \
  -DLADYBIRD_VCPKG_TYPE=distribution \
  -DCMAKE_INSTALL_PREFIX=/opt/ladybird \
  -DCMAKE_TOOLCHAIN_FILE="$VCPKG_ROOT/scripts/buildsystems/vcpkg.cmake" \
  -DENABLE_INSTALL_HEADERS=OFF \
  -GNinja
cmake --build build
```

The same source and configuration link successfully after applying the linker
group transformation described above.
