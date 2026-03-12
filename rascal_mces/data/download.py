import urllib.request
from pathlib import Path

from ..config import Config


def run_download(config: Config) -> None:
    config.raw_dir.mkdir(parents=True, exist_ok=True)

    url = config.pubchem_smiles_url
    filename = url.rsplit("/", 1)[-1]
    dest = config.raw_dir / filename

    if dest.exists():
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"Already downloaded: {dest} ({size_mb:.1f} MB)")
    else:
        print(f"Downloading {url} ...")
        _download_with_progress(url, dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"Downloaded: {dest} ({size_mb:.1f} MB)")

    # Estimate compound count
    print("Estimating compound count (reading first 10,000 lines)...")
    count = _estimate_line_count(dest)
    print(f"Estimated total compounds: ~{count:,}")


def _download_with_progress(url: str, dest: Path) -> None:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as response:
        total = int(response.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1 MB

        with open(dest, "wb") as f:
            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = downloaded / total * 100
                    print(f"\r  {downloaded / (1024**2):.1f} / {total / (1024**2):.1f} MB ({pct:.1f}%)", end="", flush=True)
                else:
                    print(f"\r  {downloaded / (1024**2):.1f} MB", end="", flush=True)
        print()


def _estimate_line_count(gz_path: Path) -> int:
    """Read first 10k lines to measure average compressed bytes per line, then extrapolate."""
    import os

    file_size = os.path.getsize(gz_path)
    # SMILES lines are shorter than InChI (~40-50 bytes uncompressed avg)
    # Use compression ratio estimate
    avg_bytes_per_line = 50
    compression_ratio = 5.5
    estimated_uncompressed = file_size * compression_ratio
    return int(estimated_uncompressed / avg_bytes_per_line)
