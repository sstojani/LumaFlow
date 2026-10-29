"""Test, stamp, package, and smoke-test a uniquely identified Windows build."""
from datetime import datetime,timezone
import json
import os
import re
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
    release_dir=ROOT/'dist'/APP_VERSION
    if release_dir.resolve().parent!=(ROOT/'dist').resolve():raise RuntimeError('Invalid release output directory')
    # A broad developer PATH can make PyInstaller bundle an unrelated ICU DLL from
    # another tool (e.g. Poppler), shadowing Windows' ICU and breaking QtCore at startup.
    windows=Path(os.environ.get('WINDIR','C:/Windows'))
    build_env={**env,'PATH':os.pathsep.join([str(Path(sys.executable).parent),str(Path(sys.base_prefix)),str(windows/'System32'),str(windows)])}
    for key in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QML2_IMPORT_PATH'):
        build_env.pop(key,None)
    run_env={**build_env,'PATH':os.pathsep.join([str(windows/'System32'),str(windows)])}
    resource=ROOT/'build'/'windows-version.txt'
    version_match=re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?',APP_VERSION)
    if not version_match:raise RuntimeError('Expected a semantic version, optionally followed by -rc.N')
    version_tuple=tuple(int(value or 0) for value in version_match.groups())
    fixed=f'filevers={version_tuple!r},prodvers={version_tuple!r},mask=0x3f,flags={2 if "-rc." in APP_VERSION else 0}'
    resource.write_text("VSVersionInfo(ffi=FixedFileInfo("+fixed+",OS=0x40004,fileType=1,subtype=0,date=(0,0)),kids=[StringFileInfo([StringTable('040904B0',[StringStruct('FileDescription','LumaFlow lighting studio'),StringStruct('FileVersion',"+repr(APP_VERSION)+"),StringStruct('ProductName','LumaFlow'),StringStruct('ProductVersion',"+repr(APP_VERSION)+"),StringStruct('BuildID',"+repr(build_id)+")])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])",encoding='utf-8')
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name','LumaFlow','--icon','assets/lumaflow.ico','--hidden-import','orgb_worker',
        '--distpath',str(release_dir),
        '--version-file',str(resource),
        '--hidden-import','smoke','--add-data',str(manifest)+os.pathsep+'.',
        '--collect-all','bleak','--collect-all','pyaudiowpatch','--collect-all','openrgb',
        '--exclude-module','PySide6.QtWebEngineCore','app.py']
    subprocess.run(command,cwd=ROOT,env=build_env,check=True)
    bundle=release_dir/'LumaFlow';exe=bundle/'LumaFlow.exe'
    (bundle/'BUILD-ID.txt').write_text(build_id+'\nSource: '+commit+'\n',encoding='utf-8')
    for name in ('LICENSE','README.md','CHANGELOG.md','ACCEPTANCE.md','requirements-build.txt'):
        if (ROOT/name).exists():shutil.copy2(ROOT/name,bundle/name)
    check=ROOT/'review-output'/'packaged'
    subprocess.run([str(exe),'--smoke-test',str(check)],cwd=ROOT,env=run_env,check=True,timeout=60)
    result=json.loads((check/'smoke-result.json').read_text(encoding='utf-8'))
    if not result.get('ok') or result['build']['build_id']!=build_id:raise RuntimeError('Packaged GUI smoke check failed')
    # Verify anonymous stdio pipes in the windowed OpenRGB helper without a device/server.
    helper=subprocess.run([str(exe),'--openrgb-worker'],input='{"op":"ping"}\n',
        capture_output=True,text=True,timeout=20,creationflags=0x08000000,env=run_env)
    reply=json.loads(helper.stdout)
    if helper.returncode or not reply.get('ok') or reply['build']['build_id']!=build_id:
        raise RuntimeError('Packaged OpenRGB helper pipe smoke check failed')
    (check/'worker-result.json').write_text(json.dumps(reply,indent=2),encoding='utf-8')
    archive=shutil.make_archive(str(ROOT/'dist'/('LumaFlow-Windows-'+build_id)),'zip',root_dir=release_dir,base_dir='LumaFlow')
    print('Build ID:',build_id,flush=True);print('Package:',archive,flush=True)


if __name__=='__main__':run()
