"""Opt-in current-user startup, no elevation or background service."""
import sys
import subprocess
from pathlib import Path

NAME='NBBUFFSync'
KEY=r'Software\Microsoft\Windows\CurrentVersion\Run'

def startup_command():
    if getattr(sys,'frozen',False):parts=[sys.executable,'--startup']
    else:
        executable=Path(sys.executable)
        windowed=executable.with_name('pythonw.exe')
        parts=[str(windowed if windowed.exists() else executable),str(Path(__file__).with_name('app.py')),'--startup']
    return subprocess.list2cmdline(parts)

def startup_enabled():
    if sys.platform!='win32':return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY) as key:
            value,_=winreg.QueryValueEx(key,NAME)
        return value==startup_command()
    except FileNotFoundError:return False

def set_startup(enabled):
    if sys.platform!='win32':raise RuntimeError('Launch at sign-in is available on Windows only.')
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,KEY) as key:
        if enabled:winreg.SetValueEx(key,NAME,0,winreg.REG_SZ,startup_command())
        else:
            try:winreg.DeleteValue(key,NAME)
            except FileNotFoundError:pass
