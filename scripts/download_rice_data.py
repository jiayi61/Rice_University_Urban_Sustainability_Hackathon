"""Restore private release assets to their original folders and verify SHA-256."""
import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'raw-data')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'data/rice/manifest.json').read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    for i, entry in enumerate(manifest['files'], 1):
        target = args.output / entry['path']
        valid = target.is_file() and target.stat().st_size == entry['bytes'] and digest(target) == entry['sha256']
        if not valid:
            if args.verify_only:
                raise SystemExit('Missing or mismatched: ' + str(target))
            if target.exists():
                raise SystemExit('Existing file differs; move it aside before retrying: ' + str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=target.parent) as temp:
                subprocess.run(['gh', 'release', 'download', manifest['release_tag'], '--repo', manifest['repository'], '--pattern', entry['asset'], '--dir', temp], check=True)
                downloaded = Path(temp) / entry['asset']
                if downloaded.stat().st_size != entry['bytes'] or digest(downloaded) != entry['sha256']:
                    raise SystemExit('Download checksum mismatch: ' + entry['asset'])
                downloaded.replace(target)
        print(f"[{i}/{manifest['file_count']}] verified {entry['path']}", flush=True)

if __name__ == '__main__':
    main()
