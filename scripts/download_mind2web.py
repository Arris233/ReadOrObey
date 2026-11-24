"""Download the two official human-checked Mind2Web evaluation splits.

Usage: python scripts/download_mind2web.py [--split test_task|test_website]
Raw parquet is intentionally kept outside git by .gitignore.
"""

from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

REPO = "osunlp/Multimodal-Mind2Web"
ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "mind2web"
TIMEOUT = (20, 120)


def metadata() -> tuple[str, list[dict]]:
    info = requests.get(f"https://huggingface.co/api/datasets/{REPO}", timeout=TIMEOUT)
    info.raise_for_status()
    revision = info.json()["sha"]
    listing = requests.get(
        f"https://huggingface.co/api/datasets/{REPO}/tree/{revision}/data",
        params={"recursive": "true"}, timeout=TIMEOUT,
    )
    listing.raise_for_status()
    return revision, listing.json()


def download(item: dict, revision: str) -> str:
    path = item["path"]
    expected = item["size"]
    destination = ROOT / Path(path).name
    partial = destination.with_suffix(destination.suffix + ".part")
    if destination.exists() and destination.stat().st_size == expected:
        if partial.exists():
            partial.unlink()  # stale bytes from an earlier interrupted downloader
        return f"OK {destination.name} ({expected} bytes)"
    if destination.exists():
        destination.rename(partial)
    url = f"https://huggingface.co/datasets/{REPO}/resolve/{revision}/{path}"
    for attempt in range(5):
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        try:
            with requests.get(url, headers=headers, stream=True, timeout=TIMEOUT) as response:
                response.raise_for_status()
                if offset and response.status_code != 206:
                    # A server ignored Range: discard the partial before writing a fresh file.
                    offset = 0
                if offset and response.headers.get("Content-Range", "").split("/")[-1] != str(expected):
                    raise ValueError(f"unexpected Content-Range for {path}")
                with partial.open("ab" if offset else "wb") as output:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            output.write(chunk)
            if partial.stat().st_size != expected:
                raise ValueError(f"size {partial.stat().st_size} != {expected}")
            os.replace(partial, destination)
            return f"DOWNLOADED {destination.name} ({expected} bytes)"
        except (requests.RequestException, ValueError, OSError) as error:
            if attempt == 4:
                raise RuntimeError(f"{path}: {error}") from error
    raise AssertionError("unreachable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["test_task", "test_website"], action="append")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    splits = set(args.split or ["test_task", "test_website"])
    ROOT.mkdir(parents=True, exist_ok=True)
    revision, files = metadata()
    (ROOT / "revision.txt").write_text(revision + "\n", encoding="utf-8")
    selected = [item for item in files if Path(item["path"]).name.startswith(tuple(s + "-" for s in splits)) and item["path"].endswith(".parquet")]
    if not selected:
        raise RuntimeError("No parquet files for the requested splits")
    print(f"revision={revision} files={len(selected)} total_GB={sum(x['size'] for x in selected)/1e9:.2f}", flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(download, item, revision) for item in selected]
        for future in as_completed(futures):
            print(future.result(), flush=True)
    manifest = [{"path": item["path"], "size": item["size"], "revision": revision} for item in selected]
    (ROOT / "download_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
