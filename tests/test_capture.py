import sys
import time
import types
import numpy as np
from engine import Capture
from model import DEFAULTS

def test_capture_blackout_and_brightness_recovery(monkeypatch):
    frame=np.zeros((100,160,4),dtype=np.uint8);frame[:,:,2]=255
    class Screen:
        monitors=[{},{}]
        def grab(self,monitor):return frame.copy()
        def close(self):pass
    monkeypatch.setitem(sys.modules,'mss',types.SimpleNamespace(mss=Screen))
    events=[];capture=Capture(lambda k,v:events.append((k,v)))
    def wait_for(fn):
        end=time.monotonic()+2
        while not fn() and time.monotonic()<end:time.sleep(.01)
        assert fn(),events
    try:
        capture.update({**DEFAULTS,'mode':'Screen','screen_response':0,'smoothing':0})
        wait_for(lambda:capture.latest.level==1)
        assert capture.latest.rgb==(255,0,0)
        frame[:,:,:3]=0
        wait_for(lambda:capture.latest.mode=='Screen' and capture.latest.level==0)
        assert capture.latest.rgb==(0,0,0)
        frame[:,:,0]=100
        wait_for(lambda:0<capture.latest.level<.5)
        assert capture.latest.rgb==(0,0,255)
    finally:capture.close()
    assert not capture.thread.is_alive()


def test_source_failure_zeros_output_and_recovers_without_mode_change(monkeypatch):
    frame=np.zeros((100,160,4),dtype=np.uint8);frame[:,:,0]=255
    class Screen:
        monitors=[{},{}]
        attempts=0
        def grab(self,monitor):
            Screen.attempts+=1
            if Screen.attempts==1:raise OSError('temporary display failure')
            return frame.copy()
        def close(self):pass
    monkeypatch.setitem(sys.modules,'mss',types.SimpleNamespace(mss=Screen))
    events=[];capture=Capture(lambda kind,value:events.append((kind,value)))
    try:
        capture.update({**DEFAULTS,'mode':'Screen','smoothing':0,'screen_response':0})
        end=time.monotonic()+1
        while not any(k=='source_error' for k,v in events) and time.monotonic()<end:time.sleep(.01)
        assert any(k=='source_error' for k,v in events) and capture.latest.level==0
        # Manual Retry changes the source revision, bypassing the automatic backoff.
        capture.update({**DEFAULTS,'mode':'Screen','smoothing':0,'screen_response':0,'_source_revision':1})
        end=time.monotonic()+1
        while capture.latest.level==0 and time.monotonic()<end:time.sleep(.01)
        assert capture.latest.rgb==(0,0,255) and capture.latest.level==1
        assert any(k=='source_recovered' for k,v in events)
    finally:capture.close()


def test_default_audio_change_reopens_stream_and_off_releases_it(monkeypatch):
    device={'index':1};opened=[];instances=[]
    class Stream:
        def __init__(self):self.closed=False
        def is_active(self):return True
        def stop_stream(self):pass
        def close(self):self.closed=True
    class Audio:
        def __init__(self):self.terminated=False;instances.append(self)
        def get_default_wasapi_loopback(self):
            return dict(index=device['index'],defaultSampleRate=48000,maxInputChannels=2,name='Simulated output')
        def open(self,**kwargs):
            stream=Stream();opened.append((kwargs['input_device_index'],stream));return stream
        def terminate(self):self.terminated=True
    monkeypatch.setitem(sys.modules,'pyaudiowpatch',types.SimpleNamespace(PyAudio=Audio,paFloat32=1,paContinue=0))
    capture=Capture(lambda *args:None)
    def wait_for(condition,seconds=3.5):
        end=time.monotonic()+seconds
        while not condition() and time.monotonic()<end:time.sleep(.01)
        assert condition()
    try:
        capture.update({**DEFAULTS,'mode':'Music'})
        wait_for(lambda:len(opened)==1)
        device['index']=2;wait_for(lambda:len(opened)==2)
        assert opened[0][0]==1 and opened[0][1].closed and instances[0].terminated
        assert opened[1][0]==2
        capture.update({**DEFAULTS,'mode':'Off'})
        wait_for(lambda:capture.latest.mode=='Off')
        assert opened[1][1].closed and instances[1].terminated
        assert capture.latest.level==0
    finally:capture.close()
