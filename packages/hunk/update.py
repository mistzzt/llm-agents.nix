#!/usr/bin/env nix
#! nix shell --inputs-from .# nixpkgs#python3 nixpkgs#bun nixpkgs#git --command python3

"""Update script for hunk package.

Custom updater needed because hunk uses bun2nix: after each version
bump the bun.nix lockfile must be regenerated from the upstream
bun.lock using the bun2nix CLI, then workspace package entries are
stripped (they resolve from the source tree at build time).
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from updater import (
    calculate_url_hash,
    clone_and_generate_bun_nix,
    fetch_github_latest_release,
    load_hashes,
    save_hashes,
    should_update,
)
from updater.nix import run_command

PKG_DIR = Path(__file__).parent
FLAKE_ROOT = PKG_DIR.parent.parent
HASHES_FILE = PKG_DIR / "hashes.json"
BUN_NIX = PKG_DIR / "bun.nix"

OWNER = "modem-dev"
REPO = "hunk"


def strip_workspace_entries(bun_nix: Path) -> None:
    """Remove workspace copyPathToStore entries from bun.nix.

    Workspace packages are local source, not npm dependencies.
    bun2nix emits ``copyPathToStore`` entries for them, but these
    paths are relative and don't exist in the Nix store at eval time.
    """
    text = bun_nix.read_text()
    text = re.sub(r"  copyPathToStore,\n", "", text)
    text = re.sub(
        r'  "@hunk/[^"]*"\s*=\s*copyPathToStore\s+[^;]+;\n',
        "",
        text,
    )
    text = text.replace(
        "}:\n{",
        "}:\n{\n  # Workspace packages are in the source tree, resolved at build time",
    )
    bun_nix.write_text(text)
    run_command(["nix", "fmt", "--", str(bun_nix)], cwd=FLAKE_ROOT)


def main() -> None:
    """Update the hunk package."""
    data = load_hashes(HASHES_FILE)
    current = data["version"]
    latest = fetch_github_latest_release(OWNER, REPO)

    print(f"Current: {current}, Latest: {latest}")

    if not should_update(current, latest):
        print("Already up to date")
        return

    print(f"Updating hunk from {current} to {latest}")

    # Step 1: Calculate new source hash
    print("Calculating source hash...")
    url = f"https://github.com/{OWNER}/{REPO}/archive/refs/tags/v{latest}.tar.gz"
    source_hash = calculate_url_hash(url, unpack=True)

    # Step 2: Update hashes.json
    save_hashes(HASHES_FILE, {"version": latest, "hash": source_hash})
    print("Updated hashes.json")

    # Step 3: Regenerate bun.nix from upstream bun.lock
    clone_and_generate_bun_nix(
        OWNER,
        REPO,
        latest,
        BUN_NIX,
        FLAKE_ROOT,
        pkg_dir=PKG_DIR,
        ref_prefix="v",
    )
    strip_workspace_entries(BUN_NIX)

    print(f"Updated hunk to {latest}")


if __name__ == "__main__":
    main()
