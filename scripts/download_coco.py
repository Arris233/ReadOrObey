"""Download and verify COCO 2017 validation images and instance annotations.

Usage: python scripts/download_coco.py
"""
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1] / "data/raw/coco"
FILES = (
    ("http://images.cocodataset.org/zips/val2017.zip", "val2017.zip", 815585330),
    ("http://images.cocodataset.org/annotations/annotations_trainval2017.zip",
     "annotations_trainval2017.zip", 252907541),
)


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for url, name, expected_size in FILES:
        path = ROOT / name
        if not path.is_file() or path.stat().st_size != expected_size:
            partial = ROOT / (name + ".download")
            subprocess.run(["curl.exe", "-fL", "--retry", "5", "-C", "-",
                            "-o", str(partial), url], check=True)
            if partial.stat().st_size != expected_size:
                raise ValueError(f"Unexpected byte count: {name}")
            partial.replace(path)
        with zipfile.ZipFile(path) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise ValueError(f"Corrupt ZIP member: {corrupt}")
            archive.extractall(ROOT)
        print(f"Verified and extracted {name}")
    images = list((ROOT / "val2017").glob("*.jpg"))
    labels = ROOT / "annotations/instances_val2017.json"
    if len(images) != 5000 or not labels.is_file():
        raise ValueError("Incomplete COCO 2017 validation dataset")
    print("Ready: 5000 images and instance annotations")


if __name__ == "__main__":
    main()
