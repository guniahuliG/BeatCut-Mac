"""Fetch only pinned HTTPS build inputs; never run on end-user machines."""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

root = Path(__file__).resolve().parent.parent
lock = json.loads((root/'packaging/downloads.json').read_text())
name, destination = sys.argv[1:3]
item = lock['downloads'][name]
path = Path(destination)
path.parent.mkdir(parents=True, exist_ok=True)
with urllib.request.urlopen(item['url'], timeout=120) as source, path.open('wb') as target:
    while block := source.read(1024*1024):
        target.write(block)
actual = hashlib.sha256(path.read_bytes()).hexdigest()
if actual != item['sha256']:
    path.unlink(missing_ok=True)
    raise SystemExit(f'SHA256 mismatch: {name}')
print(f'Verified {name}: {actual}')
