import asyncio
import copy
import unittest
from unittest.mock import AsyncMock
from engine import Engine
from model import DEFAULTS
from adapters import BLE,WLED

class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_brightness_change_resends_without_color_change(self):
        a=BLE({'profile':'MELK'});a.write=AsyncMock();a.client=type('C',(),{'is_connected':True})()
        await a.send((255,0,0),60);a.write.reset_mock()
        await a.send((255,0,0),20)
        a.write.assert_awaited_once_with(bytes.fromhex('7e070114ffffff00ef'))
    async def test_rgb_fallback_scales_and_deduplicates(self):
        a=BLE({'profile':'RGB only'});a.write=AsyncMock();a.client=type('C',(),{'is_connected':True})()
        await a.send((255,0,0),100);await a.send((255,0,0),50);await a.send((255,0,0),50)
        assert a.write.await_count==2
        assert a.write.await_args.args[0]==bytes.fromhex('7e07050380000010ef')
    async def test_wled_payload_controls_all_active_segments(self):
        a=WLED({'address':'127.0.0.1'});calls=[]
        a.segment_ids=[0,2];a.request=lambda p,v:calls.append((p,v)) or {'success':True}
        await a.send((255,0,0),50)
        payload=calls[0][1];assert payload['bri']==128
        assert [s['id'] for s in payload['seg']]==[0,2]
        await a.send((255,0,0),0);assert calls[-1][1]['on'] is False

class Fake:
    interval=.02
    instances=[]
    def __init__(self,c):self.config=c;self.closed=False;self.sent=[];self.instances.append(self)
    async def connect(self):pass
    async def send(self,rgb,brightness):self.sent.append((rgb,brightness))
    async def close(self):self.closed=True

class EngineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        Fake.instances=[];self.e=Engine(False,{'wled':Fake});self.s=copy.deepcopy(DEFAULTS)
        self.s['mode']='Solid';self.s['devices']=[dict(id='one',name='One',kind='wled',address='x',enabled=True,verified=True)]
    async def asyncTearDown(self):
        self.e.running=False
        for t in self.e.tasks.values():t.cancel()
        await asyncio.gather(*self.e.tasks.values(),return_exceptions=True)
    async def test_manual_disconnect_stays_off(self):
        await self.e.reconcile(self.s);await asyncio.sleep(.03)
        updated=copy.deepcopy(self.s);updated['devices'][0]['enabled']=False
        await self.e.reconcile(updated);await asyncio.sleep(.03)
        assert not self.e.tasks;assert Fake.instances[0].closed
        await self.e.reconcile(updated);assert len(Fake.instances)==1
    async def test_latest_frame_and_live_brightness(self):
        await self.e.reconcile(self.s);await asyncio.sleep(.03)
        self.e.target=(0,0,255)
        updated=copy.deepcopy(self.s);updated['solid_brightness']=12
        await self.e.reconcile(updated);await asyncio.sleep(.04)
        assert Fake.instances[0].sent[-1]==((0,0,255),12)
        assert len(Fake.instances)==1
    async def test_unverified_device_sends_no_automatic_colors(self):
        self.s['devices'][0]['verified']=False
        await self.e.reconcile(self.s);await asyncio.sleep(.05)
        assert Fake.instances[0].sent==[]
    async def test_slow_device_does_not_stall_other_device(self):
        class Slow(Fake):
            async def send(self,rgb,b):await asyncio.sleep(.3);await super().send(rgb,b)
        self.e.factories['slow']=Slow
        self.s['devices'].append(dict(id='slow',name='Slow',kind='slow',address='y',enabled=True,verified=True))
        await self.e.reconcile(self.s);await asyncio.sleep(.04)
        fast=next(a for a in Fake.instances if a.config['id']=='one')
        assert fast.sent
        self.e.target=(1,2,3);await asyncio.sleep(.04)
        assert fast.sent[-1][0]==(1,2,3)
    async def test_reconnect_on_transient_failure(self):
        class Flaky(Fake):
            async def connect(self):
                if len(Fake.instances)==1:raise ConnectionError('temporary loss')
        self.e.factories['wled']=Flaky
        await self.e.reconcile(self.s);await asyncio.sleep(2.15)
        assert len(Fake.instances)==2 and Fake.instances[-1].sent
    async def test_reconnect_disabled_does_not_retry_on_slider_change(self):
        class Broken(Fake):
            async def connect(self):raise ConnectionError('offline')
        self.e.factories['wled']=Broken;self.s['reconnect']=False
        await self.e.reconcile(self.s);await asyncio.sleep(.03)
        updated=copy.deepcopy(self.s);updated['solid_brightness']=10
        await self.e.reconcile(updated);await asyncio.sleep(.03)
        assert len(Fake.instances)==1
    async def test_pause_retains_connection_without_sending(self):
        self.s['mode']='Paused';await self.e.reconcile(self.s);await asyncio.sleep(.03)
        assert len(Fake.instances)==1 and not Fake.instances[0].closed and not Fake.instances[0].sent

class BlackoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_blackout_and_wake_packets(self):
        a=BLE({'profile':'MELK'});a.write=AsyncMock();a.client=type('C',(),{'is_connected':True})()
        await a.send((255,0,0),80);a.write.reset_mock()
        await a.send((0,0,0),0)
        assert a.write.await_args_list[0].args[0]==bytes.fromhex('7e070100ffffff00ef')
        assert a.write.await_args_list[1].args[0]==bytes.fromhex('7e07050300000010ef')
        a.write.reset_mock();await a.send((0,0,255),80)
        assert a.write.await_args_list[0].args[0]==bytes.fromhex('7e070150ffffff00ef')
