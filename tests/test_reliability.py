import asyncio
import copy
import json
import time
import numpy as np
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app import Window
from controls import BrightnessSlider
from diagnostics import export_payload
from engine import Engine
from model import Store,DEFAULTS,SCHEMA_VERSION
from signals import audio_signal
from version import APP_VERSION,build_info,source_digest


@pytest.mark.parametrize('kind',['opposite','one-channel','same'])
def test_stereo_music_does_not_cancel(kind):
    wave=.08*np.sin(2*np.pi*100*np.arange(4096)/48000)
    right={'opposite':-wave,'one-channel':np.zeros_like(wave),'same':wave}[kind]
    rgb,level,bars=audio_signal(np.column_stack([wave,right]),48000)
    assert level>.2 and max(bars)>.1 and rgb[0]>rgb[1]
    assert audio_signal(np.zeros((4096,2)),48000)[1]==0


def test_settings_recover_fields_and_preserve_explicit_optouts(tmp_path):
    raw={**DEFAULTS,'version':3,'resume':'false','reconnect':'false','gain':None,
        'screen_brightness':82,'devices':[
            dict(id='one',kind='ble',name='Bars',address='AA:BB:CC:DD:EE:01',enabled='false',verified='false',profile='MELK'),
            dict(id='bad',kind='ble',name=None,address=None,enabled=True,verified=True)]}
    path=tmp_path/'settings.json';path.write_text(json.dumps(raw))
    store=Store(path)
    assert store.warning and not store.data['resume'] and not store.data['reconnect']
    assert store.data['screen_brightness']==82 and store.data['gain']==DEFAULTS['gain']
    assert len(store.data['devices'])==1
    assert store.data['devices'][0]['enabled'] is False and store.data['devices'][0]['verified'] is False
    assert json.loads(path.with_name('settings-v2.invalid.json').read_text())==raw
    store.save();assert Store(path).data['version']==SCHEMA_VERSION


def test_recovery_keeps_multiple_backups(tmp_path):
    path=tmp_path/'settings.json'
    for value in ['{','[']:
        path.write_text(value);Store(path)
    backups=list(tmp_path.glob('*.invalid.json'))
    assert len(backups)==2 and {p.read_text() for p in backups}=={'{','['}


def test_upgrade_keeps_original_settings_for_rollback(tmp_path):
    path=tmp_path/'settings.json';original={'version':3,'color':[0,0,255],'mode':'Solid'}
    path.write_text(json.dumps(original));store=Store(path);store.data['mode']='Off';store.save()
    assert json.loads((tmp_path/'settings-v3.before-v4.json').read_text())==original
    assert Store(path).data['mode']=='Off'


def test_future_settings_are_never_overwritten(tmp_path):
    path=tmp_path/'settings.json';original=json.dumps({'version':999,'future':True});path.write_text(original)
    store=Store(path)
    with pytest.raises(RuntimeError):store.save()
    assert path.read_text()==original


@pytest.mark.parametrize('value',['true',1,{},[]])
def test_malformed_settings_cannot_enable_capture_or_verification(tmp_path,value):
    path=tmp_path/'settings.json';path.write_text(json.dumps({'resume':value,'version':4,
        'devices':[dict(id='one',name='Bars',address='AA:BB:CC:DD:EE:01',kind='ble',enabled=value,verified=value)]}))
    store=Store(path)
    assert store.data['resume'] is False
    assert not store.data['devices'][0]['enabled'] and not store.data['devices'][0]['verified']


class Fake:
    interval=.01
    instances=[]
    failures=0
    def __init__(self,config):self.sent=[];self.config=config;self.instances.append(self)
    async def connect(self):
        if self.failures:
            type(self).failures-=1;raise ConnectionError('temporary failure')
    async def send(self,rgb,brightness):self.sent.append((tuple(rgb),brightness))
    async def close(self):pass


def settings(mode='Solid',verified=True):
    s=copy.deepcopy(DEFAULTS);s['mode']=mode
    s['devices']=[dict(id='one',kind='wled',name='One',address='local',enabled=True,verified=verified)]
    return s


async def stop(engine):
    engine.running=False
    for task in engine.tasks.values():task.cancel()
    await asyncio.gather(*engine.tasks.values(),return_exceptions=True)


def test_off_sends_zero_even_before_verification_and_on_reconnect():
    async def work():
        Fake.instances=[];e=Engine(False,{'wled':Fake});s=settings('Off',False)
        try:
            await e.reconcile(s);await asyncio.sleep(.06)
            assert Fake.instances[0].sent==[((0,0,0),0)]
            await e.retry_device('one');await asyncio.sleep(.06)
            assert Fake.instances[1].sent==[((0,0,0),0)]
            assert not s['devices'][0]['verified']
        finally:await stop(e)
    asyncio.run(work())


def test_off_does_not_reenable_manually_disconnected_device():
    async def work():
        Fake.instances=[];e=Engine(False,{'wled':Fake});s=settings('Off');s['devices'][0]['enabled']=False
        try:
            await e.reconcile(s);await asyncio.sleep(.03)
            assert not e.tasks and not Fake.instances
        finally:await stop(e)
    asyncio.run(work())


def test_retry_restarts_failed_device_without_enabling_automatic_reconnect():
    async def work():
        Fake.instances=[];Fake.failures=1;e=Engine(False,{'wled':Fake});s=settings();s['reconnect']=False
        try:
            await e.reconcile(s);await asyncio.sleep(.03)
            assert e.tasks['one'].done() and e.status['one']=='Offline · click Retry'
            await e.retry_device('one');await asyncio.sleep(.03)
            assert len(Fake.instances)==2 and Fake.instances[-1].sent
            assert e.settings['reconnect'] is False
        finally:await stop(e)
    asyncio.run(work())


def test_controls_use_bounded_latest_value_and_do_not_overwrite_pause():
    async def work():
        e=Engine(False);await e.reconcile({**DEFAULTS,'mode':'Paused'})
        for value in range(1000):e.submit('controls',{**DEFAULTS,'mode':'Solid','solid_brightness':value%101})
        assert e.commands.empty()
        controls=e.take_controls();e.apply_controls(controls)
        assert e.settings['solid_brightness']==999%101 and e.settings['mode']=='Paused'
        assert e.take_controls() is None
        for value in range(1000):e.submit('controls',{'gain':value})
        e.submit('quit')
        start=time.monotonic();await e.run()
        assert time.monotonic()-start<.5
    asyncio.run(work())


@pytest.fixture
def window(tmp_path):
    app=QApplication.instance() or QApplication([])
    w=Window(Store(tmp_path/'settings.json'),Engine(False));w.show();app.processEvents()
    yield w
    w.save_timer.stop();w.timer.stop();w.tray.hide();w.hide();w.deleteLater();app.processEvents()


def test_power_pause_and_resume_preserve_brightness(window):
    w=window;w.set_mode('Solid');w.brightness_slider.setValue(37)
    w.pause_button.click();assert w.s['mode']=='Paused' and w.pause_button.symbol=='play'
    w.pause_button.click();assert w.s['mode']=='Solid'
    w.power_button.click();assert w.s['mode']=='Off' and not w.pause_button.isEnabled()
    w.power_button.click();assert w.s['mode']=='Solid' and w.s['solid_brightness']==37
    assert w.power_button.accessibleName()=='Turn lights off'


def test_off_is_retained_at_launch_without_capture_resume(tmp_path):
    app=QApplication.instance() or QApplication([]);store=Store(tmp_path/'settings.json')
    store.data.update(mode='Off',resume=False);store.save()
    w=Window(Store(store.path),Engine(False))
    try:assert w.s['mode']=='Off'
    finally:w.save_timer.stop();w.timer.stop();w.tray.hide();w.deleteLater();app.processEvents()


def test_slider_debounces_disk_and_flushes_final_value_on_quit(window):
    w=window;calls=[];save=w.store.save
    def record():calls.append(1);save()
    w.store.save=record
    for value in range(101):w.brightness_slider.setValue(value)
    assert not calls and w.engine.pending_controls['solid_brightness']==100
    QTest.qWait(330)
    assert len(calls)==1 and Store(w.store.path).data['solid_brightness']==100
    w.brightness_slider.setValue(17);w.quit()
    assert len(calls)==2 and Store(w.store.path).data['solid_brightness']==17


def test_vertical_slider_mouse_and_keyboard_input(window):
    slider=window.brightness_slider;window.set_mode('Solid');QApplication.processEvents()
    QTest.mouseClick(slider,Qt.LeftButton,pos=QPoint(44,4));assert slider.value()==100
    QTest.mouseClick(slider,Qt.LeftButton,pos=QPoint(44,162));assert slider.value()==0
    QTest.keyClick(slider,Qt.Key_Up);assert slider.value()==1
    QTest.keyClick(slider,Qt.Key_End);assert slider.value()==100
    assert slider.orientation()==Qt.Vertical


def test_diagnostics_redaction_does_not_modify_original():
    s=settings();s['devices'][0].update(address='192.168.50.99',name='MyPrivateLight',id='private-id')
    exported=export_payload(s,{'private-id':'Connected'},{},['MyPrivateLight at 192.168.50.99'],build_info())
    encoded=json.dumps(exported)
    assert '192.168.50.99' not in encoded and 'MyPrivateLight' not in encoded and 'private-id' not in encoded
    assert s['devices'][0]['address']=='192.168.50.99'
    assert export_payload(s,{}, {},[],build_info(),False)['settings']==s


def test_build_identity_changes_with_source(tmp_path):
    path=tmp_path/'app.py';path.write_text('print(1)\n');first=source_digest(tmp_path)
    path.write_bytes(b'print(1)\r\n');assert source_digest(tmp_path)==first
    path.write_text('print(2)\n');assert source_digest(tmp_path)!=first
    assert APP_VERSION in build_info()['build_id']
