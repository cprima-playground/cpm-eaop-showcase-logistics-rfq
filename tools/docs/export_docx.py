#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Combine Markdown files into .docx via pandoc, per data/publishing/manifests.yaml.

The same source file may appear in multiple combined documents (manifests.yaml
handles that, this script just follows it). Mermaid ```mermaid code blocks
render to images via the `mermaid-filter` pandoc filter before pandoc builds
the .docx. Author/copyright/license metadata comes from
data/publishing/publishing-metadata.yaml and is applied to every generated file.

Meant to run inside the publishing container (infra/publishing/Dockerfile),
which pins pandoc + mermaid-filter + uv so output doesn't depend on whatever
happens to be installed on the host:

    docker build -t eaop-publishing -f infra/publishing/Dockerfile .
    docker run --rm -v "${PWD}:/repo" -w /repo eaop-publishing [document-key ...]

No document-key args = export every document in the manifest.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "data" / "publishing" / "manifests.yaml"
METADATA_PATH = REPO_ROOT / "data" / "publishing" / "publishing-metadata.yaml"
OUT_DIR = REPO_ROOT / "data" / "publishing" / "docx"
DEFAULT_TARGET_DIR = REPO_ROOT / "web" / "downloads"


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def export_document(key: str, doc: dict, metadata: dict) -> None:
    files = [REPO_ROOT / f for f in doc["files"]]
    missing = [f for f in files if not f.exists()]
    if missing:
        raise FileNotFoundError(f"{key}: missing source file(s): {missing}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"{key}.docx"

    title = doc.get("title", key)
    rights = f"{metadata['copyright']} ({metadata['license']}, {metadata['license_url']})"
    cmd = [
        "pandoc",
        *(str(f) for f in files),
        "--from=markdown+yaml_metadata_block",
        "--to=docx",
        f"--output={out_file}",
        "--filter=mermaid-filter",
        f"--metadata=title:{title}",
        f"--metadata=author:{metadata['author']}",
        f"--metadata=rights:{rights}",
    ]
    print(f"[{key}] {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, cwd=REPO_ROOT)
    print(f"[{key}] -> {out_file}")

    target_dir = REPO_ROOT / doc["target"] if "target" in doc else DEFAULT_TARGET_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / out_file.name
    shutil.copy2(out_file, target_file)
    print(f"[{key}] -> {target_file}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keys", nargs="*", help="document keys to export (default: all)")
    args = parser.parse_args()

    manifest = load_yaml(MANIFEST_PATH)["documents"]
    metadata = load_yaml(METADATA_PATH)

    keys = args.keys or list(manifest.keys())
    for key in keys:
        if key not in manifest:
            print(f"unknown document key: {key!r} (known: {list(manifest.keys())})", file=sys.stderr)
            return 1
        export_document(key, manifest[key], metadata)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
