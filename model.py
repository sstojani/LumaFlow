"""Pure configuration, frames and color math. No hardware or GUI imports."""
import copy
import json
import math
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
import numpy as np

SCHEMA_VERSION = 4
ACTIVE_MODES = ('Solid','Screen','Music','Atmosphere')
MODES = (*ACTIVE_MODES,'Paused','Off')
DEFAULTS = dict(version=SCHEMA_VERSION, brightness=60, color=[255,80,35], mode='Solid',last_active_mode='Solid',
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
        self.warning='';self.read_only=False
        source=self.path
        legacy=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'NBBUFF Sync'/'settings-v2.json'
        if path is None and not source.exists() and legacy.exists():source=legacy
        if source.exists():
            try:
                raw=json.loads(source.read_text(encoding='utf-8'))
                if not isinstance(raw,dict): raise ValueError('Expected settings object')
                version=raw.get('version',2)
                if type(version) is int and version>SCHEMA_VERSION:self.read_only=True
                if type(version) is not int or version>SCHEMA_VERSION:raise ValueError('Unsupported settings version')
                if source==self.path and version<SCHEMA_VERSION:
                    rollback=self.path.with_name(f'settings-v{version}.before-v{SCHEMA_VERSION}.json')
                    if not rollback.exists():shutil.copy2(source,rollback)
                if version<3:
                    for mode in ACTIVE_MODES:raw.setdefault(mode.lower()+'_brightness',raw.get('brightness',60))
                self.data,problems=validate_settings(raw)
                if problems:
                    try:backup=self.backup(source)
                    except OSError:backup=source
                    self.warning=f'Recovered invalid settings ({", ".join(problems)}). Original kept at {backup}.'
            except Exception as e:
                try:backup=self.backup(source)
                except OSError:backup=source
                self.warning=f'Settings could not be loaded ({e}). Original kept at {backup}.'
                self.data=copy.deepcopy(DEFAULTS)
                # Never silently start capture after recovering damaged settings.
                self.data['mode']='Paused'
    @staticmethod
    def backup(source):
        backup=source.with_name('settings-v2.invalid.json')
        if backup.exists():backup=source.with_name('settings-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.invalid.json')
        shutil.copy2(source,backup)
        return backup
    def save(self):
        if self.read_only:raise RuntimeError('Settings belong to a newer LumaFlow version; they were left unchanged.')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data['version']=SCHEMA_VERSION
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data,indent=2),encoding='utf-8')
        os.replace(tmp,self.path)


def validate_settings(raw):
    """Recover fields independently; malformed opt-outs must never become opt-ins."""
    from effects import EFFECTS
    data=copy.deepcopy(DEFAULTS);problems=[]
    def boolean(key,value,default):
        if type(value) is bool:return value
        problems.append(key)
        if isinstance(value,str) and value.lower()=='false':return False
        return default
    ranges={'brightness':(0,100),'smoothing':(0,600),'gain':(1,30),'monitor':(1,64),
        'solid_brightness':(0,100),'screen_brightness':(0,100),'music_brightness':(0,100),
        'atmosphere_brightness':(0,100),'saturation':(0,250),'black_threshold':(0,12),
        'exposure':(25,200),'screen_gamma':(50,200),'screen_response':(0,300),
        'music_response':(0,300),'music_smoothing':(0,300),'noise_gate':(0,60),'cycle_seconds':(2,60)}
    enums={'mode':MODES,'last_active_mode':ACTIVE_MODES,'region':('Whole screen','Left edge','Right edge','Top edge'),
        'audio':('Speakers','Microphone'),'effect':EFFECTS}
    for key,default in DEFAULTS.items():
        if key not in raw or key in ('devices','version'):continue
        value=raw[key]
        if type(default) is bool:
            data[key]=boolean(key,value,False if key in ('resume','reconnect') else default)
        elif key in ranges:
            lo,hi=ranges[key]
            if type(value) is int:data[key]=max(lo,min(hi,value))
            if type(value) is not int or not lo<=value<=hi:problems.append(key)
        elif key in enums:
            if value in enums[key]:data[key]=value
            else:problems.append(key)
        elif key=='color':
            try:rgb_packet(value);data[key]=list(value)
            except (TypeError,ValueError):problems.append(key)
    if 'last_active_mode' not in raw and data['mode'] in ACTIVE_MODES:data['last_active_mode']=data['mode']
    devices=raw.get('devices',[]);ids=set();addresses=set()
    if not isinstance(devices,list):problems.append('devices');devices=[]
    for index,device in enumerate(devices):
        prefix=f'device {index+1}'
        if not isinstance(device,dict):problems.append(prefix);continue
        d={k:device.get(k) for k in ('id','kind','name','address')}
        if (d['kind'] not in ('ble','wled','openrgb') or
            any(not isinstance(d[k],str) or not d[k].strip() for k in ('id','name','address'))):
            problems.append(prefix);continue
        d={k:v.strip() for k,v in d.items()}
        address_key=(d['kind'],d['address'].lower())
        if d['id'] in ids or address_key in addresses:problems.append(prefix);continue
        if d['kind']=='ble' and not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',d['address']):
            problems.append(prefix+' address');continue
        if d['kind']=='wled' and not re.fullmatch(r'[a-zA-Z0-9.-]+(?::[0-9]{1,5})?',d['address']):
            problems.append(prefix+' address');continue
        d['enabled']=boolean(prefix+' enabled',device['enabled'],False) if 'enabled' in device else True
        d['verified']=boolean(prefix+' verified',device['verified'],False) if 'verified' in device else False
        d['profile']=device.get('profile','RGB only')
        if d['profile'] not in ('MELK','BLEDOB','RGB only'):
            d['profile']='RGB only';d['verified']=False;problems.append(prefix+' profile')
        ids.add(d['id']);addresses.add(address_key);data['devices'].append(d)
    return data,list(dict.fromkeys(problems))

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
