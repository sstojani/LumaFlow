"""Pure configuration, frames and color math. No hardware or GUI imports."""
import copy
import json
import math
import os
from pathlib import Path
import numpy as np

DEFAULTS = dict(version=3, brightness=60, color=[255,80,35], mode='Solid',
    region='Whole screen', monitor=1, smoothing=100, vivid=True, gain=8,
    audio='Speakers', reconnect=True, resume=False, tray=True, start_hidden=False, devices=[],
    solid_brightness=60,screen_brightness=100,music_brightness=100,atmosphere_brightness=60,
    saturation=150,black_threshold=3,exposure=100,screen_gamma=100,auto_brightness=True,ignore_bars=True,
    screen_response=80,music_response=55,music_smoothing=35,noise_gate=15,
    effect='Rainbow flow',cycle_seconds=12,animations=True)

def data_dir():
    p=Path(os.environ.get('LOCALAPPDATA',str(Path.home()))) / 'LumaFlow'
    p.mkdir(parents=True,exist_ok=True)
    return p

class Store:
    def __init__(self,path=None):
        self.path=Path(path) if path else data_dir()/'settings.json'
        self.data=copy.deepcopy(DEFAULTS)
        self.warning=''
        source=self.path
        legacy=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'NBBUFF Sync'/'settings-v2.json'
        if path is None and not source.exists() and legacy.exists():source=legacy
        if source.exists():
            try:
                raw=json.loads(source.read_text(encoding='utf-8'))
                if isinstance(raw,dict) and raw.get('version',2)<3:
                    for mode in ['solid','screen','music','atmosphere']:raw.setdefault(mode+'_brightness',raw.get('brightness',60))
                if not isinstance(raw,dict): raise ValueError('Expected settings object')
                self.data.update({k:v for k,v in raw.items() if k in DEFAULTS})
                self.data['brightness']=max(0,min(100,int(self.data['brightness'])))
                self.data['smoothing']=max(0,min(600,int(self.data['smoothing'])))
                self.data['gain']=max(1,min(30,int(self.data['gain'])))
                self.data['monitor']=max(1,int(self.data['monitor']))
                for key,low,high in [('solid_brightness',0,100),('screen_brightness',0,100),('music_brightness',0,100),('atmosphere_brightness',0,100),('saturation',0,250),('black_threshold',0,12),('exposure',25,200),('screen_gamma',50,200),('screen_response',0,300),('music_response',0,300),('music_smoothing',0,300),('noise_gate',0,60),('cycle_seconds',2,60)]:
                    self.data[key]=max(low,min(high,int(self.data[key])))
                from effects import EFFECTS
                if self.data['effect'] not in EFFECTS:self.data['effect']=EFFECTS[0]
                rgb_packet(self.data['color'])
                if self.data['mode'] not in ['Solid','Screen','Music','Atmosphere','Paused']: raise ValueError('Unknown mode')
                if not isinstance(self.data['devices'],list): raise ValueError('Invalid devices')
                ids=set()
                for d in self.data['devices']:
                    if d['kind'] not in ['ble','wled','openrgb'] or d['id'] in ids: raise ValueError('Invalid device')
                    ids.add(d['id'])
                    str(d['address']); str(d['name'])
            except Exception as e:
                self.warning=f'Settings could not be loaded ({e}). Original file kept as settings-v2.invalid.json.'
                if source==self.path:self.path.replace(self.path.with_name('settings-v2.invalid.json'))
                self.data=copy.deepcopy(DEFAULTS)
    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data['version']=3
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data,indent=2),encoding='utf-8')
        os.replace(tmp,self.path)

def rgb_packet(rgb):
    if len(rgb)!=3 or any(type(v) is not int or not 0<=v<=255 for v in rgb):
        raise ValueError('Expected 3 integer RGB channels from 0 to 255')
    return bytes([0x7e,7,5,3,*rgb,0x10,0xef])

def brightness_packet(level,profile):
    level=max(0,min(100,round(level)))
    if profile=='MELK': return bytes([0x7e,7,1,level,255,255,255,0,0xef])
    if profile=='BLEDOB': return bytes([0x7e,4,1,level,1,255,2,1,0xef])
    return None

def scale(rgb,brightness): return tuple(round(max(0,min(255,float(v)))*brightness/100) for v in rgb)

def ease(previous,target,dt,milliseconds):
    a=1 if milliseconds<=0 else 1-math.exp(-max(0,dt)/(milliseconds/1000))
    return tuple(p+(t-p)*a for p,t in zip(previous,target))

def screen_color(frame,region='Whole screen',vivid=True):
    h,w=frame.shape[:2]
    if region=='Left edge': frame=frame[:,:max(1,w//5)]
    elif region=='Right edge': frame=frame[:,4*w//5:]
    elif region=='Top edge': frame=frame[:max(1,h//5)]
    pixels=frame[::max(1,frame.shape[0]//72),::max(1,frame.shape[1]//128),:3][...,::-1].reshape(-1,3).astype(float)
    if not vivid: return tuple(pixels.mean(axis=0))
    high=pixels.max(axis=1); low=pixels.min(axis=1)
    sat=(high-low)/np.maximum(high,1)
    useful=(high>18)&(sat>.22)
    # Only prefer colored pixels if they occupy a meaningful part of the image.
    if useful.mean()<.08: return tuple(pixels.mean(axis=0))
    p=pixels[useful]; s=sat[useful]
    # Dominant quantized color avoids averaging opposing hues into pale white.
    bins=(p//64).astype(int); keys=bins[:,0]*16+bins[:,1]*4+bins[:,2]
    winner=np.bincount(keys,weights=s,minlength=64).argmax()
    chosen=p[keys==winner]
    color=chosen.mean(axis=0)
    # Modest saturation boost, while preserving near-black scenes.
    lo=color.min(); color=np.maximum(0,color-lo*.25)
    return tuple(color)

def audio_color(samples,rate,gain):
    if samples is None or samples.size==0:return (0,0,0)
    x=samples.mean(axis=1) if samples.ndim==2 else samples
    x=np.nan_to_num(x); rms=float(np.sqrt(np.mean(x*x)))
    if rms<.001:return (0,0,0)
    f=np.fft.rfftfreq(len(x),1/rate); power=np.abs(np.fft.rfft(x*np.hanning(len(x))))
    bands=[float(power[(f>=lo)&(f<hi)].sum()) for lo,hi in [(30,250),(250,2000),(2000,16000)]]
    peak=max(bands) or 1
    return tuple(255*min(1,rms*gain)*b/peak for b in bands)
