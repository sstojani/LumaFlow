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
