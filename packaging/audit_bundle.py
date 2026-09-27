"""Reject native components that would knowingly prevent target-OS support."""
from pathlib import Path
import json
import os
import re
import subprocess
import sys

app = Path(sys.argv[1]).resolve()
arch = os.environ['APP_ARCH']
minimum = tuple(map(int,os.environ['MACOSX_DEPLOYMENT_TARGET'].split('.')))
minimum = (minimum+(0,0))[:3]
seen, records, errors = set(), [], []
for path in app.rglob('*'):
    if not path.is_file():
        continue
    real = path.resolve()
    if real in seen:
        continue
    seen.add(real)
    if not real.is_relative_to(app):
        errors.append(f'External symlink: {path} -> {real}')
        continue
    kind = subprocess.check_output(['/usr/bin/file','-b',str(real)],text=True)
    if 'Mach-O' not in kind:
        continue
    archs = subprocess.check_output(['/usr/bin/lipo','-archs',str(real)],text=True).split()
    if arch not in archs:
        errors.append(f'Missing {arch}: {path}')
        continue
    text = subprocess.check_output(['/usr/bin/otool','-arch',arch,'-l',str(real)],text=True)
    versions = re.findall(r'\bminos\s+(\d+(?:\.\d+)*)',text)
    versions += re.findall(r'cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version (\d+(?:\.\d+)*)',text)
    if not versions:
        errors.append(f'No minimum macOS version found: {path}')
    for version in versions:
        value = (tuple(map(int,version.split('.')))+(0,0))[:3]
        if value > minimum:
            errors.append(f'{path}: needs macOS {version}, target {minimum}')
    deps = subprocess.check_output(['/usr/bin/otool','-arch',arch,'-L',str(real)],text=True)
    for line in deps.splitlines():
        if not line.startswith('\t'):
            continue
        dep = line.strip().split(' (')[0]
        if dep.startswith('/') and not dep.startswith(('/System/Library/', '/usr/lib/')):
            errors.append(f'External library dependency: {path}: {dep}')
    records.append({'path':str(real.relative_to(app)), 'architectures':archs, 'minimums':versions})
Path('build/bundle-audit.json').write_text(json.dumps({'components':records,'errors':errors},indent=2))
if errors:
    raise SystemExit('\n'.join(errors))
print(f'Audited {len(records)} Mach-O files: {arch}, target {minimum}')
