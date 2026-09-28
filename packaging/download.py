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
import time
import os
from urllib.parse import urlsplit
url=item['url']
if urlsplit(url).scheme!='https' or not urlsplit(url).hostname:
    raise SystemExit('Only valid HTTPS URLs are allowed')
partial=path.with_name(path.name+'.part')
for attempt in range(1,5):
    print(f'Downloading {name}, attempt {attempt}/4: {url}',flush=True)
    try:
        digest=hashlib.sha256()
        with urllib.request.urlopen(url,timeout=120) as source,partial.open('wb') as target:
            if urlsplit(source.geturl()).scheme!='https':raise ValueError('Non-HTTPS redirect rejected')
            while block := source.read(1024*1024):
                target.write(block);digest.update(block)
        actual=digest.hexdigest()
        if actual!=item['sha256']:raise ValueError(f'SHA256 mismatch: {name}')
        os.replace(partial,path)
        print(f'Verified {name}: {actual}',flush=True)
        break
    except ValueError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as exc:
        partial.unlink(missing_ok=True)
        print(f'Download failed on {urlsplit(url).hostname}: {exc}',flush=True)
        if attempt==4:raise
        time.sleep(3*attempt)
