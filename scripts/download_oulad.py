"""Download OULAD into data/raw/. Standard library only.

Skips the download if the 7 CSVs already exist. Tries each URL in order,
checks that the response is a zip, and extracts nested zips until the CSVs exist.
"""

import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

URLS = (
    "https://analyse.kmi.open.ac.uk/open_dataset/download",
    "https://archive.ics.uci.edu/static/public/349/open+university+learning+analytics+dataset.zip",
)
CSV_NAMES = (
    "courses.csv",
    "assessments.csv",
    "vle.csv",
    "studentInfo.csv",
    "studentRegistration.csv",
    "studentAssessment.csv",
    "studentVle.csv",
)
RAW_DIR = Path("data/raw")
WORK_DIR = Path("data/tmp/oulad_download")
CHUNK_BYTES = 1 << 20
TIMEOUT_SECONDS = 120


def have_all_csvs(folder: Path) -> bool:
    return all((folder / name).is_file() for name in CSV_NAMES)


def fetch(url: str, target: Path) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "liftpath-download/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            with target.open("wb") as out:
                shutil.copyfileobj(response, out, CHUNK_BYTES)
    except OSError as error:
        print(f"download failed: {url}: {error}")
        return False
    if not zipfile.is_zipfile(target):
        print(f"not a zip: {url}")
        return False
    print(f"downloaded {target.stat().st_size / 1e6:.1f} MB from {url}")
    return True


def safe_extract(archive: Path, target: Path) -> None:
    """Extract a zip, but skip members that point outside the target folder."""
    root = target.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            dest = (target / member.filename).resolve()
            if not dest.is_relative_to(root):
                print(f"skipped unsafe member: {member.filename}")
                continue
            zf.extract(member, target)


def extract_recursively(archive: Path, target: Path) -> None:
    safe_extract(archive, target)
    done = {archive.resolve()}
    while True:
        nested = [p for p in target.rglob("*.zip") if p.resolve() not in done]
        if not nested:
            return
        for inner in nested:
            done.add(inner.resolve())
            safe_extract(inner, inner.parent / inner.stem)


def collect_csvs(source: Path, target: Path) -> bool:
    target.mkdir(parents=True, exist_ok=True)
    for name in CSV_NAMES:
        matches = sorted(source.rglob(name))
        if not matches:
            print(f"missing after extract: {name}")
            return False
        shutil.copy2(matches[0], target / name)
    return True


def main() -> int:
    if have_all_csvs(RAW_DIR):
        print(f"skip: the 7 CSVs exist in {RAW_DIR}")
        return 0
    for index, url in enumerate(URLS):
        attempt_dir = WORK_DIR / f"attempt_{index}"
        shutil.rmtree(attempt_dir, ignore_errors=True)
        attempt_dir.mkdir(parents=True)
        archive = attempt_dir / "download.zip"
        if not fetch(url, archive):
            continue
        extract_dir = attempt_dir / "extract"
        extract_recursively(archive, extract_dir)
        if collect_csvs(extract_dir, RAW_DIR):
            shutil.rmtree(WORK_DIR, ignore_errors=True)
            print(f"ok: the 7 CSVs are in {RAW_DIR}")
            return 0
    print("Both URLs failed. Put the OULAD zip or the 7 CSVs in data/raw/.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
