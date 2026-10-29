import json
import numpy as np
import pytest
from model import Store,brightness_packet,rgb_packet,screen_color,ease,audio_color,scale

def test_native_brightness_packets():
    assert brightness_packet(50,'MELK').hex()=='7e070132ffffff00ef'
    assert brightness_packet(50,'BLEDOB').hex()=='7e04013201ff0201ef'
    assert brightness_packet(50,'RGB only') is None

def test_pure_red_has_no_blue():
    assert rgb_packet((255,0,0)).hex()=='7e070503ff000010ef'
    assert scale((255,0,0),50)==(128,0,0)

@pytest.mark.parametrize('rgb',[(256,0,0),(-1,0,0),(1.5,0,0),(0,0)])
def test_invalid_packet(rgb):
    with pytest.raises(ValueError):rgb_packet(rgb)

def test_vivid_avoids_white_contamination():
    img=np.full((100,100,4),255,dtype=np.uint8);img[:,:60,:3]=(0,0,255)
    average=screen_color(img,vivid=False);vivid=screen_color(img,vivid=True)
    assert average[1]>90 and average[2]>90
    assert vivid==(255,0,0)

def test_dark_and_white_scenes():
    assert screen_color(np.zeros((10,10,4),dtype=np.uint8))==(0,0,0)
    assert screen_color(np.full((10,10,4),255,dtype=np.uint8))==(255,255,255)

def test_smoothing_time_invariant():
    a=ease((0,0,0),(255,0,0),.1,200)
    b=ease(ease((0,0,0),(255,0,0),.05,200),(255,0,0),.05,200)
    assert a==pytest.approx(b)

def test_settings_remember_disconnect(tmp_path):
    store=Store(tmp_path/'settings.json');store.data['devices']=[dict(id='a',kind='ble',address='x',name='Bars',enabled=False,verified=True)]
    store.data['brightness']=24;store.save();reloaded=Store(store.path)
    assert reloaded.data['devices'][0]['enabled'] is False
    assert reloaded.data['brightness']==24

def test_bad_settings_recover(tmp_path):
    path=tmp_path/'settings-v2.json';path.write_text('{')
    store=Store(path);assert store.warning;assert store.data['brightness']==60
    assert path.with_name('settings-v2.invalid.json').exists()

def test_audio_silence_and_bass():
    assert audio_color(np.zeros((2048,2)),48000,8)==(0,0,0)
    t=np.arange(4096)/48000;rgb=audio_color(.2*np.sin(2*np.pi*100*t),48000,8)
    assert rgb[0]>rgb[1]*10 and rgb[0]>rgb[2]*10
