"""Isolate third-party blocking SDK calls so disconnect/quit remains bounded."""
import json
import sys

def run():
    # A PyInstaller windowed executable has no Python stdio objects. Rebind the
    # explicitly inherited anonymous pipes created by the parent process.
    if sys.platform=='win32' and (sys.stdin is None or sys.stdout is None):
        import ctypes,msvcrt,os
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetStdHandle.argtypes=[ctypes.c_ulong];kernel.GetStdHandle.restype=ctypes.c_void_p
        if sys.stdin is None:
            handle=kernel.GetStdHandle(ctypes.c_ulong(-10 & 0xffffffff))
            sys.stdin=os.fdopen(msvcrt.open_osfhandle(handle,os.O_RDONLY),'r',encoding='utf-8')
        if sys.stdout is None:
            handle=kernel.GetStdHandle(ctypes.c_ulong(-11 & 0xffffffff))
            sys.stdout=os.fdopen(msvcrt.open_osfhandle(handle,os.O_WRONLY),'w',encoding='utf-8',buffering=1)
    client=None;device=None
    try:
        for line in sys.stdin:
            try:
                cmd=json.loads(line)
                if cmd['op']=='connect':
                    from openrgb import OpenRGBClient
                    client=OpenRGBClient(address='127.0.0.1',port=6742,name='LumaFlow')
                    matches=[d for d in client.devices if d.name==cmd['name']]
                    if len(matches)!=1:raise ValueError('Device name missing or ambiguous in OpenRGB.')
                    device=matches[0]
                    direct=next((m.name for m in device.modes if m.name.lower()=='direct'),None)
                    if not direct:raise ValueError('Device has no Direct mode for synchronization.')
                    device.set_mode(direct)
                elif cmd['op']=='color':
                    from openrgb.utils import RGBColor
                    device.set_color(RGBColor(*cmd['rgb']),fast=True)
                print(json.dumps({'ok':True}),flush=True)
            except Exception as e:print(json.dumps({'error':str(e)}),flush=True)
    finally:
        if client:client.disconnect()

if __name__=='__main__':run()
