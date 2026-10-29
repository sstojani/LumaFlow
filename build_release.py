"""Test, stamp, package, and smoke-test a uniquely identified Windows build."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from version import APP_VERSION,source_digest

ROOT=Path(__file__).resolve().parent


def run():
    if sys.platform!='win32':raise SystemExit('Build this Windows package on Windows.')
    for folder in ('build','dist','review-output'):
        if (ROOT/folder).resolve().parent!=ROOT:raise SystemExit('Build output must remain inside the project.')
    env={**os.environ,'QT_QPA_PLATFORM':'offscreen'}
    subprocess.run([sys.executable,'-m','pytest','tests','-q'],cwd=ROOT,env=env,check=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    digest=source_digest(ROOT);build_id=f'{APP_VERSION}+{stamp}.{digest}'
    try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
    except (OSError,subprocess.CalledProcessError):commit='unavailable'
    info={'version':APP_VERSION,'build_id':build_id,'source_digest':digest,'commit':commit,
        'python':sys.version.split()[0],'built_utc':stamp,'packaged':True}
    manifest=ROOT/'build'/'build-info.json';manifest.parent.mkdir(exist_ok=True)
    manifest.write_text(json.dumps(info,indent=2),encoding='utf-8')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--onedir','--windowed',
        '--name','LumaFlow','--icon','assets/lumaflow.ico','--hidden-import','orgb_worker',
        '--hidden-import','smoke','--add-data',str(manifest)+os.pathsep+'.',
        '--collect-all','bleak','--collect-all','pyaudiowpatch','--collect-all','openrgb',
        '--exclude-module','PySide6.QtWebEngineCore','app.py']
    subprocess.run(command,cwd=ROOT,check=True)
    bundle=ROOT/'dist'/'LumaFlow';exe=bundle/'LumaFlow.exe'
    (bundle/'BUILD-ID.txt').write_text(build_id+'\nSource: '+commit+'\n',encoding='utf-8')
    for name in ('LICENSE','README.md','CHANGELOG.md','ACCEPTANCE.md','requirements-build.txt'):
        if (ROOT/name).exists():shutil.copy2(ROOT/name,bundle/name)
    check=ROOT/'review-output'/'packaged'
    subprocess.run([str(exe),'--smoke-test',str(check)],cwd=ROOT,env=env,check=True,timeout=60)
    result=json.loads((check/'smoke-result.json').read_text(encoding='utf-8'))
    if not result.get('ok') or result['build']['build_id']!=build_id:raise RuntimeError('Packaged GUI smoke check failed')
    # Verify anonymous stdio pipes in the windowed OpenRGB helper without a device/server.
    helper=subprocess.run([str(exe),'--openrgb-worker'],input='{"op":"ping"}\n',
        capture_output=True,text=True,timeout=20,creationflags=0x08000000)
    reply=json.loads(helper.stdout)
    if helper.returncode or not reply.get('ok') or reply['build']['build_id']!=build_id:
        raise RuntimeError('Packaged OpenRGB helper pipe smoke check failed')
    (check/'worker-result.json').write_text(json.dumps(reply,indent=2),encoding='utf-8')
    archive=shutil.make_archive(str(ROOT/'dist'/('LumaFlow-Windows-'+build_id)),'zip',root_dir=ROOT/'dist',base_dir='LumaFlow')
    print('Build ID:',build_id,flush=True);print('Package:',archive,flush=True)


if __name__=='__main__':run()
