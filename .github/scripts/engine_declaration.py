#!/usr/bin/env python3
"""engine_declaration.py -- read gitops/engine/kyverno.yaml, the engine this repository declares.

Hub ADR-0033 point 2, eco-system ticket 147. An adopter owns its Kyverno version, and
gitops/engine/kyverno.yaml is the one place it says which. Every reader in this repository goes
through this script, so the drift lane and the offline CLI read the same figures:

  .github/workflows/drift-sample.yml   downloads install_url, checks install_sha256, applies it
  .github/workflows/shift-left.yml     downloads cli_url, checks cli_sha256, and refuses a binary
                                       that reports another version

This script checks the file's SHAPE: an exact X.Y.Z version, the install.yaml URL and CLI
archive name of that exact release, and a 64-hex sha256 for each. It cannot tell whether a
sha256 is the right one. The hub check verify/adopter-engines does that: it holds every figure
to the platform engine table's row for the version, on platform origin/main. No workflow here
reads the table, because the platform tools tag this repository pins
(.github/platform-tools-pin.yaml) predates it.

Usage:
    engine_declaration.py outputs [FILE]   key=value lines, for $GITHUB_OUTPUT
    engine_declaration.py --selfcheck      planted declarations, each refused
Exit 0 read; 1 the file is missing or malformed, named.
"""
from __future__ import annotations

import copy
import re
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DECLARATION = ROOT / "gitops" / "engine" / "kyverno.yaml"
RELEASES = "https://github.com/kyverno/kyverno/releases/download"
KEYS = {"schema", "engine", "version", "install", "cli"}
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_SHA = re.compile(r"[0-9a-f]{64}")


class Malformed(ValueError):
    """The declaration does not have the shape every reader relies on."""


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise Malformed(msg)


def read(path: Path | None = None) -> dict[str, str]:
    """The declared engine, validated. Raises Malformed naming the first fault."""
    path = Path(path or DECLARATION)
    try:
        doc = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise Malformed(f"{path}: not readable: {exc}") from exc
    _need(isinstance(doc, dict), f"{path}: not a mapping")
    _need(set(doc) == KEYS, f"{path}: keys must be exactly {sorted(KEYS)}, not {sorted(doc)}")
    _need(doc["schema"] == 1, f"{path}: schema must be 1")
    _need(doc["engine"] == "kyverno", f"{path}: engine must be kyverno")
    version = doc["version"]
    _need(isinstance(version, str) and bool(_VERSION.fullmatch(version)),
          f"{path}: version {version!r} is not an exact X.Y.Z string")
    install = doc["install"] if isinstance(doc["install"], dict) else {}
    want = f"{RELEASES}/v{version}/install.yaml"
    _need(install.get("url") == want, f"{path}: install.url must be {want}")
    _need(isinstance(install.get("sha256"), str) and bool(_SHA.fullmatch(install["sha256"])),
          f"{path}: install.sha256 is not a quoted 64-hex sha256")
    cli = ((doc["cli"] if isinstance(doc["cli"], dict) else {}).get("linux_x86_64")) or {}
    archive = f"kyverno-cli_v{version}_linux_x86_64.tar.gz"
    _need(cli.get("file") == archive, f"{path}: cli.linux_x86_64.file must be {archive}")
    _need(isinstance(cli.get("sha256"), str) and bool(_SHA.fullmatch(cli["sha256"])),
          f"{path}: cli.linux_x86_64.sha256 is not a quoted 64-hex sha256")
    return {"version": version, "install_url": want, "install_sha256": install["sha256"],
            "cli_url": f"{RELEASES}/v{version}/{archive}", "cli_sha256": cli["sha256"]}


def selfcheck() -> int:
    good = yaml.safe_load(DECLARATION.read_text())
    read(DECLARATION)
    other = "9.9.9"
    plants = {
        "a range, not a version": lambda d: d.__setitem__("version", ">=1.18"),
        "a version YAML reads as a number": lambda d: d.__setitem__("version", 1.18),
        "an install.yaml of another release": lambda d: d["install"].__setitem__(
            "url", f"{RELEASES}/v{other}/install.yaml"),
        "a short install checksum": lambda d: d["install"].__setitem__("sha256", "3dcd43ea"),
        "a CLI archive of another release": lambda d: d["cli"]["linux_x86_64"].__setitem__(
            "file", f"kyverno-cli_v{other}_linux_x86_64.tar.gz"),
        "no CLI checksum": lambda d: d["cli"]["linux_x86_64"].pop("sha256"),
        "another engine": lambda d: d.__setitem__("engine", "gatekeeper"),
        "a field no reader reads": lambda d: d.__setitem__("chart", "3.8.2"),
    }
    bad = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, plant in plants.items():
            doc = copy.deepcopy(good)
            plant(doc)
            p = Path(tmp) / "kyverno.yaml"
            p.write_text(yaml.safe_dump(doc))
            try:
                read(p)
            except Malformed:
                continue
            bad.append(name)
        try:
            read(Path(tmp) / "absent.yaml")
            bad.append("a missing file")
        except Malformed:
            pass
    if bad:
        print("FAIL: the reader accepted: " + "; ".join(bad))
        return 1
    print(f"PASS: selfcheck: {DECLARATION.relative_to(ROOT)} reads, and each of "
          f"{len(plants) + 1} planted declarations is refused")
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:]
    if args == ["--selfcheck"]:
        return selfcheck()
    if args[:1] == ["outputs"] and len(args) <= 2:
        try:
            engine = read(Path(args[1]) if len(args) == 2 else None)
        except Malformed as exc:
            print(f"::error::the declared engine is not readable: {exc}", file=sys.stderr)
            return 1
        print("\n".join(f"{k}={v}" for k, v in engine.items()))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
