import copy
import math
import numpy as np
import pytest
from signals import screen_signal,audio_signal,Response,cap_for
from effects import EFFECTS,effect_frame
from model import DEFAULTS,Store

def frame(rgb,h=100,w=160):
    img=np.zeros((h,w,4),dtype=np.uint8);img[:,:,:3]=rgb[::-1];return img

@pytest.mark.parametrize('rgb',[(255,0,0),(0,255,0),(0,0,255)])
def test_screen_primaries_preserve_hue(rgb):
    out,level,_=screen_signal(frame(rgb),DEFAULTS)
    assert out==rgb and level==1

def test_dim_red_dims_brightness_without_becoming_pink():
    out,level,_=screen_signal(frame((50,0,0)),DEFAULTS)
    assert out==(255,0,0) and 0<level<.2

def test_black_and_near_black_exact_off():
    for value in [0,1,3,7]:
        rgb,level,_=screen_signal(frame((value,value,value)),DEFAULTS)
        assert rgb==(0,0,0) and level==0

def test_cursor_does_not_keep_black_screen_on():
    img=frame((0,0,0));img[50:52,80:82,:3]=255
    assert screen_signal(img,DEFAULTS)[1]==0

def test_black_gate_survives_disabled_auto_brightness():
    s={**DEFAULTS,'auto_brightness':False}
    assert screen_signal(frame((0,0,0)),s)[1]==0
    assert screen_signal(frame((90,0,0)),s)[1]==1

def test_brightness_scales_monotonically():
    levels=[screen_signal(frame((v,0,0)),DEFAULTS)[1] for v in [0,10,40,100,180,255]]
    assert levels==sorted(levels) and levels[0]==0 and levels[-1]==1

def test_letterbox_crop():
    img=frame((0,0,0));img[20:80,:,:3]=(0,0,255)
    assert screen_signal(img,DEFAULTS)[1]==1
    assert screen_signal(img,{**DEFAULTS,'ignore_bars':False})[1]<.65

def test_colorful_red_with_white_stays_red():
    img=frame((255,255,255));img[:,:90,:3]=(0,0,255)
    assert screen_signal(img,DEFAULTS)[0]==(255,0,0)

def test_black_bypasses_smoothing_and_restores():
    r=Response();r.apply((255,0,0),1,.1,600,300,'Screen')
    assert r.apply((0,0,0),0,.001,600,300,'Screen')==((0,0,0),0)
    rgb,level=r.apply((0,0,255),1,.1,600,0,'Screen')
    assert rgb==(0,0,255) and level==1

def test_audio_intensity_and_spectrum():
    t=np.arange(4096)/48000
    quiet=audio_signal(.02*np.sin(2*np.pi*100*t),48000)
    loud=audio_signal(.08*np.sin(2*np.pi*100*t),48000)
    assert 0<quiet[1]<loud[1]<=1
    assert loud[0][0]>loud[0][1] and max(loud[2])>0
    assert len(loud[2])==32
    silent=audio_signal(np.zeros(4096),48000)
    assert silent[1]==0 and max(silent[2])==0

def test_per_mode_brightness():
    s={**DEFAULTS,'solid_brightness':12,'screen_brightness':90,'mode':'Solid'}
    assert cap_for(s)==12
    s['mode']='Screen';assert cap_for(s)==90

@pytest.mark.parametrize('effect',EFFECTS)
def test_effects_have_bounded_changing_output(effect):
    frames=[effect_frame(effect,t/30) for t in range(300)]
    assert len(set(frames))>1
    assert all(len(rgb)==3 and all(0<=v<=255 for v in rgb) and 0<=level<=1 for rgb,level in frames)

def test_v2_migration_retains_device_and_caps(tmp_path,monkeypatch):
    import json
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    old=tmp_path/'NBBUFF Sync';old.mkdir()
    original={'version':2,'brightness':42,'devices':[{'id':'one','kind':'ble','name':'Bars','address':'xx','enabled':False,'verified':True}]}
    (old/'settings-v2.json').write_text(json.dumps(original))
    s=Store();assert s.data['screen_brightness']==42 and not s.data['devices'][0]['enabled']
    s.save();assert Store().data['devices']==original['devices']
    assert json.loads((old/'settings-v2.json').read_text())==original
