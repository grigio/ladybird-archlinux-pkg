# ladybird-archlinux-pkg

Builds **two Arch Linux packages** (`x86_64_v3` and generic `x86_64`) of every upstream
[Ladybird](https://github.com/LadybirdBrowser/ladybird) tag release, entirely in
GitHub Actions, and attaches the resulting `.pkg.tar.zst` to a GitHub release in
this repository.

Nothing is compiled locally. The AUR is not involved — the package is only
published as a GitHub release asset here.

## Build targets

Every release carries two packages:

| Package | Target |
| --- | --- |
| `x86_64_v3` | Optimized for the **x86-64-v3** microarchitecture level (AVX2, BMI1/BMI2, FMA). Requires a v3-capable CPU; this is what CachyOS uses. |
| `x86_64` | Generic baseline x86-64, installable on any x86-64 Arch Linux system. |

The architecture flags are applied to Ladybird's own C/C++ code, to the libraries
built by vcpkg, and to the Rust components (`target-cpu=x86-64-v3` /
`target-cpu=x86-64`).

## How it works

[`.github/workflows/package-releases.yml`](.github/workflows/package-releases.yml)
runs on a schedule (every 6 hours) and can also be triggered manually. In an
`archlinux:base-devel` container it:

1. Lists Ladybird tag releases and compares them to the releases already present
   in this repository.
2. For every new tag:
   - diffs it against the previous tag using the GitHub compare API and writes
     release notes containing the **new commits, their descriptions, stats and
     contributors** (see [`scripts/release_bot.py`](scripts/release_bot.py));
   - reads the exact `vcpkg` baseline pinned by that tag's `vcpkg.json`;
   - runs `makepkg` using [`PKGBUILD`](PKGBUILD) and the two patches in
     [`patches/`](patches/) to build the package;
   - creates a release named after the tag (e.g. `2026.47.7`) and uploads the
     package to it.

## Manual trigger

In the GitHub web UI: **Actions → Package Ladybird releases for Arch Linux →
Run workflow**. Leave the tag input blank to package all missing tags, or enter a
specific tag (e.g. `2026.47.7`) to rebuild just that one.

With the GitHub CLI:

```bash
gh workflow run package-releases.yml -f tag=2026.47.7
```

## Install a released package

```bash
gh release download <tag> --repo <owner>/<this-repo> --pattern '*.pkg.tar.zst'
sudo pacman -U ./*.pkg.tar.zst
```

## Layout

| Path | Purpose |
| --- | --- |
| `.github/workflows/package-releases.yml` | CI workflow (schedule + manual trigger) |
| `PKGBUILD` | Arch build recipe, parameterised by `LADYBIRD_VERSION` and `VCPKG_COMMIT` |
| `patches/` | Small build fixes applied to the Ladybird source |
| `scripts/release_bot.py` | Planning, diff/release notes, build orchestration, publishing |
