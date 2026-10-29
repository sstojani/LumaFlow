"""One application version and a content ID for every source or packaged build."""
import hashlib
import json
from pathlib import Path
import sys

APP_VERSION='0.4.0-rc.2'


def source_digest(root=None):
    root=Path(root) if root else Path(__file__).parent
    digest=hashlib.sha256()
    for path in sorted(root.glob('*.py')):
        digest.update(path.name.encode());digest.update(path.read_bytes().replace(b'\r\n',b'\n'))
    return digest.hexdigest()[:12]


def build_info():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    manifest=root/'build-info.json'
    if getattr(sys,'frozen',False) and manifest.exists():return json.loads(manifest.read_text(encoding='utf-8'))
    return {'version':APP_VERSION,'build_id':f'{APP_VERSION}+source.{source_digest()}',
            'python':sys.version.split()[0],'packaged':False}
