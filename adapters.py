"""Explicit device adapters. No undocumented auto-probing or vendor cloud access."""
import asyncio
import json
import time
import re
import urllib.request
from model import rgb_packet,brightness_packet,scale

FFF0='0000fff0-0000-1000-8000-00805f9b34fb'
FFF3='0000fff3-0000-1000-8000-00805f9b34fb'

class BLE:
    interval=.10
    def __init__(self,config):
        self.config=config; self.client=None; self.last_brightness=None; self.last_color=None; self.last_write=0
    async def connect(self):
        from bleak import BleakClient
        self.client=BleakClient(self.config['address'],timeout=12)
        await asyncio.wait_for(self.client.connect(),16)
        chars=[c for s in self.client.services if s.uuid.lower()==FFF0 for c in s.characteristics
               if c.uuid.lower()==FFF3 and ('write' in c.properties or 'write-without-response' in c.properties)]
        if len(chars)!=1:raise RuntimeError('Unsupported GATT layout. Export diagnostics; no commands sent.')
        self.char=chars[0]; self.response='write-without-response' not in self.char.properties
        self.gatt=[{'service':s.uuid,'characteristics':[{'uuid':c.uuid,'properties':c.properties} for c in s.characteristics]} for s in self.client.services]
    async def write(self,packet):
        if not self.client or not self.client.is_connected:raise ConnectionError('Bluetooth disconnected')
        await asyncio.sleep(max(0,self.interval-(time.monotonic()-self.last_write)))
        await asyncio.wait_for(self.client.write_gatt_char(self.char,packet,response=self.response),3)
        self.last_write=time.monotonic()
    async def send(self,rgb,brightness):
        profile=self.config.get('profile','RGB only')
        packet=brightness_packet(brightness,profile)
        color=tuple(rgb) if packet else scale(rgb,brightness)
        # Real brightness command is independent of RGB. Send it on each change only.
        if packet and brightness!=self.last_brightness:
            await self.write(packet); self.last_brightness=brightness
        if color!=self.last_color:
            await self.write(rgb_packet(color)); self.last_color=color
        if not self.client.is_connected:raise ConnectionError('Bluetooth disconnected')
    async def close(self):
        if self.client:
            try:await asyncio.wait_for(self.client.disconnect(),4)
            except Exception:pass


def host(value):
    value=value.strip()
    if not re.fullmatch(r'[a-zA-Z0-9.-]+(?::[0-9]{1,5})?',value):
        raise ValueError('Enter an IP address or hostname, optionally :port; no URL or path.')
    return value

class WLED:
    interval=.10
    def __init__(self,config):
        self.config=config; self.base='http://'+host(config['address']); self.segment_ids=[]
    def request(self,path,payload=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(payload).encode() if payload is not None else None,
                                   headers={'Content-Type':'application/json'})
        # Do not route LAN device control through system HTTP proxies.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=3) as r:
            return json.loads(r.read(1024*1024))
    async def connect(self):
        result=await asyncio.to_thread(self.request,'/json')
        if not isinstance(result,dict) or 'info' not in result or 'state' not in result:
            raise ValueError('This address did not return a WLED JSON response.')
        self.segment_ids=[s.get('id',i) for i,s in enumerate(result['state'].get('seg',[])) if s.get('stop',1)>s.get('start',0)]
        if not self.segment_ids:raise ValueError('WLED has no active segments.')
    async def send(self,rgb,brightness):
        payload={'on':brightness>0,'bri':max(1,round(brightness*255/100)),'transition':0,
                 'seg':[{'id':i,'on':True,'bri':255,'fx':0,'col':[list(rgb)]} for i in self.segment_ids]}
        result=await asyncio.to_thread(self.request,'/json/state',payload)
        if result.get('success') is False:raise RuntimeError('WLED rejected the color update.')
    async def close(self):pass

class OpenRGB:
    interval=.05
    def __init__(self,config):self.config=config;self.process=None
    async def request(self,data,timeout=4):
        self.process.stdin.write((json.dumps(data)+'\n').encode())
        await self.process.stdin.drain()
        line=await asyncio.wait_for(self.process.stdout.readline(),timeout)
        if not line:raise ConnectionError('OpenRGB helper stopped')
        result=json.loads(line)
        if 'error' in result:raise RuntimeError(result['error'])
    async def connect(self):
        import sys
        from pathlib import Path
        command=[sys.executable,'--openrgb-worker'] if getattr(sys,'frozen',False) else [sys.executable,str(Path(__file__).with_name('orgb_worker.py'))]
        kwargs={'creationflags':0x08000000} if sys.platform=='win32' else {}
        self.process=await asyncio.create_subprocess_exec(*command,stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,**kwargs)
        await self.request({'op':'connect','name':self.config['address']},15)
    async def send(self,rgb,brightness):
        await self.request({'op':'color','rgb':scale(rgb,brightness)})
    async def close(self):
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:await asyncio.wait_for(self.process.wait(),2)
            except asyncio.TimeoutError:self.process.kill();await self.process.wait()

FACTORIES={'ble':BLE,'wled':WLED,'openrgb':OpenRGB}
