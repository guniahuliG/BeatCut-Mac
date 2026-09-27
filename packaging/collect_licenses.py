from pathlib import Path
import importlib.metadata
import shutil

root = Path(__file__).resolve().parent.parent
out = root/'vendor/licenses'
out.mkdir(parents=True, exist_ok=True)
for path in (root/'packaging/licenses').glob('*'):
    shutil.copy2(path,out/path.name)
for name in ('numpy','scipy','pyinstaller','pyinstaller-hooks-contrib','altgraph','macholib','packaging'):
    distribution = importlib.metadata.distribution(name)
    for path in distribution.files or []:
        if any(token in path.name.lower() for token in ('license','copying','notice')):
            source = Path(distribution.locate_file(path))
            if source.is_file():
                target = out/name/str(path).replace('..','_')
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
print('Collected third-party notices')
