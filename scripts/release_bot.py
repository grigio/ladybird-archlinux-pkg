#!/usr/bin/env python3
"""Build an Arch Linux package of every new Ladybird tag release, entirely in GitHub Actions.

Responsibilities:
  1. Find Ladybird tag releases that have not been packaged in this repository yet.
  2. For each one, generate release notes by diffing against the previous tag
     (commit list + descriptions, stats and contributors).
  3. Build the package with makepkg inside the Arch Linux CI container.
  4. Create/update a GitHub release here and attach the built .pkg.tar.zst.

Nothing is compiled locally: this script is only ever executed from the workflow in
.github/workflows/package-releases.yml.
"""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlencode

LADYBIRD_REPO = os.environ.get("LADYBIRD_REPO", "LadybirdBrowser/ladybird")
THIS_REPO = os.environ.get("GITHUB_REPOSITORY", "")
INPUT_TAG = (os.environ.get("INPUT_TAG") or "").strip()
MAX_COMMITS_SHOWN = 200


def log(*parts: object) -> None:
    print("[release-bot]", *parts, flush=True)


def gh(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def api(path: str, params: dict[str, str] | None = None, *, paginate: bool = False):
    """Call the GitHub REST API through `gh api` and return parsed JSON."""
    if params:
        path = f"{path}?{urlencode(params)}"
    args = ["api", "--method", "GET", path]
    if paginate:
        args.append("--paginate")
    result = gh(args)
    text = result.stdout.strip()
    if not text:
        return [] if paginate else None
    if not paginate:
        return json.loads(text)

    decoder = json.JSONDecoder()
    docs: list = []
    idx = 0
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        obj, end = decoder.raw_decode(text, idx)
        docs.append(obj)
        idx = end
    # --paginate of a single page yields a list doc, of multiple pages yields N docs.
    if len(docs) == 1 and isinstance(docs[0], list):
        return docs[0]
    merged: list = []
    for doc in docs:
        merged.extend(doc if isinstance(doc, list) else [doc])
    return merged


def upstream_releases() -> list[str]:
    """Return Ladybird release tags, newest first."""
    releases = api(f"repos/{LADYBIRD_REPO}/releases", {"per_page": "100"})
    tags = [r["tag_name"] for r in releases if r.get("tag_name")]
    if tags:
        log(f"found {len(tags)} upstream releases: {', '.join(tags[:5])}...")
        return tags

    log("no upstream releases found, falling back to tags")
    tags = [t["name"] for t in api(f"repos/{LADYBIRD_REPO}/tags", {"per_page": "100"})]
    return tags


def packaged_tags() -> set[str]:
    if not THIS_REPO:
        return set()
    releases = api(f"repos/{THIS_REPO}/releases", {"per_page": "100"})
    tags = {r["tag_name"] for r in releases if r.get("tag_name")}
    log(f"{len(tags)} tags already packaged in {THIS_REPO}")
    return tags


def vcpkg_baseline(tag: str) -> str:
    """Read the vcpkg builtin-baseline pinned by the tag's vcpkg.json."""
    content = api(
        f"repos/{LADYBIRD_REPO}/contents/vcpkg.json",
        {"ref": tag},
    )
    import base64

    raw = base64.b64decode(content["content"]).decode("utf-8")
    match = re.search(r'"builtin-baseline"\s*:\s*"([0-9a-f]+)"', raw)
    if not match:
        raise RuntimeError(f"Could not find vcpkg builtin-baseline in {tag}/vcpkg.json")
    log(f"vcpkg baseline for {tag}: {match.group(1)}")
    return match.group(1)


def first_line(body: str) -> str:
    """Condense a commit body into a one-line description."""
    lines = [ln.strip() for ln in (body or "").splitlines() if ln.strip()]
    text = " ".join(lines[:2])
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 240:
        text = text[:237].rstrip() + "..."
    return text


def commits_for(tag: str, previous: str | None) -> tuple[list[dict], dict]:
    """Return (commits, stats) for tag relative to previous (or the tag's own history)."""
    if previous:
        compare = api(
            f"repos/{LADYBIRD_REPO}/compare/{previous}...{tag}",
            {"per_page": "250"},
        )
        commits = compare.get("commits", [])
        files = compare.get("files", [])
        stats = {
            "total_commits": compare.get("total_commits", len(commits)),
            "additions": sum(f.get("additions", 0) for f in files),
            "deletions": sum(f.get("deletions", 0) for f in files),
            "files_changed": len(files),
            "compare_url": compare.get("html_url")
            or f"https://github.com/{LADYBIRD_REPO}/compare/{previous}...{tag}",
            "initial": False,
        }
        # GitHub's compare API caps files at 300; note when it is truncated.
        stats["files_truncated"] = len(files) >= 300
        return commits, stats

    commits = api(
        f"repos/{LADYBIRD_REPO}/commits",
        {"sha": tag, "per_page": "100"},
    )
    return commits[:MAX_COMMITS_SHOWN], {
        "total_commits": len(commits),
        "additions": 0,
        "deletions": 0,
        "files_changed": 0,
        "compare_url": f"https://github.com/{LADYBIRD_REPO}/commits/{tag}",
        "initial": True,
    }


def render_notes(tag: str, previous: str | None, commits: list[dict], stats: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Ladybird {tag} — Arch Linux package")
    lines.append("")
    lines.append(
        f"Prebuilt Arch Linux package (`x86_64`) for upstream tag "
        f"[`{tag}`](https://github.com/{LADYBIRD_REPO}/releases/tag/{tag})."
    )
    if previous:
        lines.append(
            f"Changes are diffed against the previous release **{previous}**: "
            f"[full diff]({stats['compare_url']})."
        )
    else:
        lines.append(
            "This is the first packaged release, so there is no previous tag to diff against. "
            f"The most recent commits leading up to this tag are listed below "
            f"([full history]({stats['compare_url']}))."
        )
    lines.append("")

    authors: dict[str, int] = {}
    for c in commits:
        name = (c.get("author") or {}).get("login") or c["commit"]["author"]["name"]
        authors[name] = authors.get(name, 0) + 1

    if stats["initial"]:
        lines.append(f"**{len(commits)} commits shown** from {len(authors)} contributor(s).")
    else:
        lines.append(
            f"**{stats['total_commits']} new commits** from {len(authors)} contributor(s), "
            f"{stats['files_changed']} files changed"
            + ("" if stats.get("files_truncated") else "")
            + f", **+{stats['additions']:,} / -{stats['deletions']:,}**."
        )
    lines.append("")

    if authors:
        lines.append("Contributors: " + ", ".join(sorted(authors, key=str.lower)) + ".")
        lines.append("")

    shown = commits[:MAX_COMMITS_SHOWN]
    if stats["total_commits"] > len(shown):
        lines.append(
            f"> Showing the {len(shown)} most recent commits of {stats['total_commits']}. "
            f"See the [full diff]({stats['compare_url']}) for the complete list."
        )
        lines.append("")

    lines.append("### Included commits")
    lines.append("")
    for c in shown:
        sha = c["sha"][:7]
        url = c.get("html_url") or f"https://github.com/{LADYBIRD_REPO}/commit/{c['sha']}"
        title = c["commit"]["message"].splitlines()[0].strip()
        login = (c.get("author") or {}).get("login")
        name = login or c["commit"]["author"]["name"]
        who = f"@{login}" if login else name
        desc = first_line(c["commit"]["message"].partition("\n")[2])
        entry = f"- [`{sha}`]({url}) {title} — {who}"
        lines.append(entry)
        if desc:
            lines.append(f"  - {desc}")

    lines.append("")
    lines.append("---")
    lines.append(
        "Package metadata and build recipe: see `PKGBUILD` in this repository. "
        "Built with GitHub Actions; not published to the AUR."
    )
    lines.append("")
    return "\n".join(lines)


def build_package(tag: str, baseline: str, repo_root: Path) -> Path:
    workdir = Path(tempfile.mkdtemp(prefix="ladybird-pkg-"))
    log(f"building {tag} in {workdir}")
    for name in ("PKGBUILD", "patches/hb-fc-whole-archive.patch", "patches/gcc-build.patch"):
        src = repo_root / name
        dst = workdir / Path(name).name
        shutil.copy2(src, dst)

    # The PKGBUILD declares arch=(x86_64_v3), so makepkg must be told to use that
    # CARCH instead of the container's generic x86_64. Later assignments in a
    # makepkg.conf override earlier ones, so append the v3 settings.
    makepkg_conf = workdir / "makepkg-v3.conf"
    makepkg_conf.write_text(
        Path("/etc/makepkg.conf").read_text(encoding="utf-8")
        + '\n# --- x86-64-v3 overrides added by release_bot.py ---\n'
        + 'CARCH="x86_64_v3"\n'
        + 'CFLAGS="-march=x86-64-v3 -O2 -pipe -fno-plt -fexceptions"\n'
        + 'CXXFLAGS="$CFLAGS -Wp,-D_GLIBCXX_ASSERTIONS"\n',
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "LADYBIRD_VERSION": tag,
            "VCPKG_COMMIT": baseline,
            "MAKEFLAGS": "-j2",
            "CMAKE_BUILD_PARALLEL_LEVEL": "2",
            "VCPKG_DOWNLOADS": str(Path(env.get("HOME", "/home/builder")) / ".cache/vcpkg/downloads"),
            # Apply v3 to the third-party libraries vcpkg builds too.
            "VCPKG_C_FLAGS": "-march=x86-64-v3",
            "VCPKG_CXX_FLAGS": "-march=x86-64-v3",
            # And to Ladybird's Rust components.
            "RUSTFLAGS": "-C target-cpu=x86-64-v3",
        }
    )
    subprocess.run(
        ["makepkg", "--config", str(makepkg_conf), "--syncdeps", "--noconfirm", "--clean"],
        cwd=workdir,
        env=env,
        check=True,
    )
    packages = glob.glob(str(workdir / "*.pkg.tar.zst"))
    if len(packages) != 1:
        raise RuntimeError(f"Expected exactly one package in {workdir}, got {packages}")
    return Path(packages[0])


def publish(tag: str, package: Path, notes_file: Path) -> None:
    title = f"Ladybird {tag} — Arch Linux package"
    view = gh(["release", "view", tag, "--repo", THIS_REPO], check=False)
    if view.returncode == 0:
        log(f"release {tag} exists, uploading/replacing asset")
        gh(
            [
                "release",
                "upload",
                tag,
                str(package),
                "--repo",
                THIS_REPO,
                "--clobber",
            ]
        )
        gh(
            [
                "release",
                "edit",
                tag,
                "--repo",
                THIS_REPO,
                "--title",
                title,
                "--notes-file",
                str(notes_file),
            ]
        )
    else:
        log(f"creating release {tag}")
        gh(
            [
                "release",
                "create",
                tag,
                str(package),
                "--repo",
                THIS_REPO,
                "--title",
                title,
                "--notes-file",
                str(notes_file),
            ]
        )


def main() -> int:
    if not THIS_REPO:
        raise RuntimeError("GITHUB_REPOSITORY is not set")

    repo_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    ordered = upstream_releases()
    existing = packaged_tags()

    if INPUT_TAG:
        targets = [INPUT_TAG]
        log(f"manual build requested for {INPUT_TAG}")
    else:
        targets = [t for t in reversed(ordered) if t not in existing]
        log(f"tags to package: {targets or 'none (up to date)'}")

    for tag in targets:
        if tag in existing and not INPUT_TAG:
            log(f"skipping already packaged {tag}")
            continue
        try:
            index = ordered.index(tag)
            previous = ordered[index + 1] if index + 1 < len(ordered) else None
        except ValueError:
            previous = None
        log(f"previous tag for {tag}: {previous}")

        commits, stats = commits_for(tag, previous)
        notes = render_notes(tag, previous, commits, stats)

        notes_dir = Path(tempfile.mkdtemp(prefix="ladybird-notes-"))
        notes_file = notes_dir / f"{tag}.md"
        notes_file.write_text(notes, encoding="utf-8")

        baseline = vcpkg_baseline(tag)
        package = build_package(tag, baseline, repo_root)
        publish(tag, package, notes_file)
        log(f"published {package.name} for {tag}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"[release-bot] command failed: {exc.cmd}\n{exc.stderr}", file=sys.stderr)
        raise
