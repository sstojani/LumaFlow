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
