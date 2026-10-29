"""Color and intensity are independent. Black/silence is an exact zero gate."""
import colorsys
import math
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class Output:
    rgb: tuple=(0,0,0)
    level: float=0.
    spectrum: tuple=()
    mode: str='Paused'
    measured: float=0.


def cap_for(s):
    return s.get(s.get('mode','Solid').lower()+'_brightness',s.get('brightness',60))


def screen_pixels(frame,region,ignore_bars=True):
    # Downsample first; calculations are independent of display resolution.
    small=frame[::max(1,frame.shape[0]//100),::max(1,frame.shape[1]//160),:3][...,::-1].astype(float)
    if ignore_bars:
        # Crop only contiguous near-black borders. Never remove interior dark pixels.
        bright=small.max(axis=2)
        rows=np.flatnonzero((bright>8).mean(axis=1)>.02)
        cols=np.flatnonzero((bright>8).mean(axis=0)>.02)
        if len(rows)>small.shape[0]*.35 and len(cols)>small.shape[1]*.35:
            small=small[rows[0]:rows[-1]+1,cols[0]:cols[-1]+1]
    h,w=small.shape[:2]
    if region=='Left edge':small=small[:,:max(1,w//5)]
    elif region=='Right edge':small=small[:,4*w//5:]
    elif region=='Top edge':small=small[:max(1,h//5)]
    return small.reshape(-1,3)


def saturated(rgb,strength):
    peak=max(rgb)
    if peak<=0:return (0,0,0)
    h,s,v=colorsys.rgb_to_hsv(*(float(x)/peak for x in rgb))
    return tuple(round(x*255) for x in colorsys.hsv_to_rgb(h,min(1,s*strength),1))


def screen_signal(frame,s,was_dark=False):
    pixels=screen_pixels(frame,s.get('region','Whole screen'),s.get('ignore_bars',True))
    value=pixels.max(axis=1)/255
    average=float(value.mean())
    threshold=s.get('black_threshold',3)/100
    # Hysteresis requires a slightly brighter scene before waking from blackout.
    gate=threshold+(0.008 if was_dark else 0)
    if average<=gate:return (0,0,0),0.,average
    low=pixels.min(axis=1);high=pixels.max(axis=1);sat=(high-low)/np.maximum(high,1)
    useful=(sat>.18)&(high>10)
    if s.get('vivid',True) and useful.mean()>.03:
        p=pixels[useful];weights=sat[useful]*np.sqrt(high[useful]/255)
        # Hue bins avoid mixing white into red/green/blue and stay stable with brightness.
        maxc=p.max(axis=1);minc=p.min(axis=1);delta=np.maximum(maxc-minc,1e-6)
        index=p.argmax(axis=1);hue=np.zeros(len(p))
        hue[index==0]=((p[index==0,1]-p[index==0,2])/delta[index==0])%6
        hue[index==1]=(p[index==1,2]-p[index==1,0])/delta[index==1]+2
        hue[index==2]=(p[index==2,0]-p[index==2,1])/delta[index==2]+4
        bins=(np.round(hue/6*24).astype(int))%24
        winner=np.bincount(bins,weights=weights,minlength=24).argmax()
        color=np.average(p[bins==winner],axis=0,weights=weights[bins==winner])
    else:color=pixels.mean(axis=0)
    rgb=saturated(color,s.get('saturation',150)/100)
    # Energy is based on scene coverage, not the chosen color's strongest pixel.
    energy=max(0,min(1,(average-threshold)/max(.01,1-threshold)))
    level=min(1,energy**(s.get('screen_gamma',100)/100)*s.get('exposure',100)/100) if s.get('auto_brightness',True) else 1.
    return rgb,level,average


def audio_signal(samples,rate,gain=8,gate=.0015):
    if samples is None or samples.size==0:return (0,0,0),0.,(0.,)*32
    x=samples.mean(axis=1) if samples.ndim==2 else samples
    x=np.nan_to_num(x);rms=float(np.sqrt(np.mean(x*x)))
    if rms<=gate:return (0,0,0),0.,(0.,)*32
    f=np.fft.rfftfreq(len(x),1/rate)
    a=np.abs(np.fft.rfft(x*np.hanning(len(x))))*2/max(1,len(x))
    edges=np.geomspace(35,min(16000,rate/2),33)
    bars=tuple(min(1,float(a[(f>=lo)&(f<hi)].sum())*gain*2) for lo,hi in zip(edges[:-1],edges[1:]))
    bands=[float(a[(f>=lo)&(f<hi)].sum()) for lo,hi in [(30,250),(250,2000),(2000,16000)]]
    rgb=saturated(bands,1.2)
    return rgb,min(1,max(0,(rms-gate)*gain)),bars


class Response:
    def __init__(self):self.rgb=(0,0,0);self.level=0.;self.mode=None
    def apply(self,rgb,level,dt,color_ms,light_ms,mode):
        if self.mode!=mode:self.rgb=rgb;self.level=0.;self.mode=mode
        if level<=0:
            # Bypass smoothing entirely: no colored tail during a black frame/silence.
            self.rgb=(0,0,0);self.level=0.;return self.rgb,self.level
        if self.level==0:self.rgb=rgb
        a=1 if color_ms<=0 else 1-math.exp(-max(0,dt)/(color_ms/1000))
        self.rgb=tuple(p+(t-p)*a for p,t in zip(self.rgb,rgb))
        b=1 if light_ms<=0 else 1-math.exp(-max(0,dt)/(light_ms/1000))
        self.level+=(level-self.level)*b
        out=tuple(max(0,min(255,round(v))) for v in self.rgb)
        return out,max(0,min(1,self.level))
