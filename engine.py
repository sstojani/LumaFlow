"""Latest-frame synchronization. Each device has its own cancellable worker."""
import asyncio
import copy
import queue
import threading
import time
import sys
import logging
from adapters import FACTORIES
from signals import Output,Response,screen_signal,audio_signal,cap_for
from effects import effect_frame

class Capture:
    def __init__(self,emit):
        self.emit=emit;self.settings={};self.lock=threading.Lock();self.latest=Output()
        self.stop_event=threading.Event();self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()
    def update(self,s):
        with self.lock:self.settings=copy.deepcopy(s)
    def run(self):
        screen=None;pa=None;stream=None;audio_key=None;audio_frame=(0,None);rate=48000
        last=time.monotonic();response=Response();failed_key=None;was_dark=False;phase=0.;last_mode=None
        retry_at=0.;failures=0;audio_index=None;audio_check=0.
        try:
            while not self.stop_event.is_set():
                start=time.monotonic();dt=start-last;last=start
                with self.lock:s=self.settings.copy()
                mode=s.get('mode','Paused');key=(mode,s.get('audio'),s.get('monitor'),s.get('_source_revision',0))
                try:
                    if mode!='Screen' and screen:screen.close();screen=None
                    if (mode!='Music' or audio_key!=s.get('audio')) and stream:
                        stream.stop_stream();stream.close();stream=None;pa.terminate();pa=None
                        audio_frame=(0,None)
                    if mode in ('Paused','Off'):
                        if mode=='Off':self.latest=Output(mode='Off')
                        failed_key=None;self.stop_event.wait(.05);continue
                    if mode!=last_mode:phase=0;was_dark=False;last_mode=mode
                    bars=();measured=0.
                    if key==failed_key and start<retry_at:self.stop_event.wait(.05);continue
                    if mode=='Solid':target=s['color'];level=1.;color_ms=0;light_ms=0
                    elif mode=='Atmosphere':
                        phase+=dt/max(2,s.get('cycle_seconds',12))
                        target,level=effect_frame(s.get('effect','Rainbow flow'),phase)
                        color_ms=0;light_ms=0
                    elif mode=='Screen':
                        import mss
                        import numpy as np
                        if screen is None:screen=mss.mss()
                        if s['monitor']>=len(screen.monitors):raise ValueError('Selected monitor is unavailable. Choose another display.')
                        frame=np.asarray(screen.grab(screen.monitors[s['monitor']]))
                        target,level,measured=screen_signal(frame,s,was_dark)
                        was_dark=level==0
                        color_ms=s.get('smoothing',80);light_ms=s.get('screen_response',80)
                    else:
                        if stream is not None and start>=audio_check:
                            audio_check=start+2
                            current=pa.get_default_wasapi_loopback() if audio_key=='Speakers' else pa.get_default_input_device_info()
                            if int(current['index'])!=audio_index or not stream.is_active():
                                stream.stop_stream();stream.close();stream=None;pa.terminate();pa=None
                                audio_frame=(0,None)
                        if stream is None:
                            import pyaudiowpatch as p
                            import numpy as np
                            pa=p.PyAudio();audio_key=s['audio']
                            d=pa.get_default_wasapi_loopback() if audio_key=='Speakers' else pa.get_default_input_device_info()
                            rate=int(d['defaultSampleRate']);channels=int(d['maxInputChannels'])
                            audio_index=int(d['index']);audio_check=start+2
                            if channels<1:raise ValueError('No audio input available')
                            def callback(data,count,timing,status):
                                nonlocal audio_frame
                                audio_frame=(time.monotonic(),np.frombuffer(data,dtype=np.float32).reshape(-1,channels).copy())
                                return (None,p.paContinue)
                            stream=pa.open(format=p.paFloat32,channels=channels,rate=rate,input=True,
                                input_device_index=d['index'],frames_per_buffer=2048,stream_callback=callback)
                            self.emit('log',f'Audio source: {d["name"]}')
                        stamp,samples=audio_frame
                        target,level,bars=audio_signal(samples if start-stamp<.4 else None,rate,s['gain'],s.get('noise_gate',15)/10000)
                        measured=level;color_ms=s.get('music_smoothing',35);light_ms=s.get('music_response',55)
                    rgb,level=response.apply(target,level,dt,color_ms,light_ms,mode)
                    self.latest=Output(rgb,level,bars,mode,measured)
                    if failed_key:self.emit('source_recovered',mode)
                    failed_key=None;failures=0
                except Exception as e:
                    self.latest=Output(mode=mode)
                    failed_key=key
                    failures+=1;retry_at=start+min(30,2**min(failures,5))
                    logging.getLogger('lumaflow').exception('Capture source failed: %s',mode)
                    self.emit('source_error',{'mode':mode,'message':str(e)})
                    if screen:
                        try:screen.close()
                        except Exception:pass
                        screen=None
                    if stream:
                        try:stream.close()
                        except Exception:pass
                        stream=None
                    if pa:
                        pa.terminate();pa=None
                self.stop_event.wait(max(.001,1/30-(time.monotonic()-start)))
        finally:
            if stream:
                try:stream.stop_stream();stream.close()
                except Exception:pass
            if pa:pa.terminate()
            if screen:screen.close()
    def close(self):self.stop_event.set();self.thread.join(2)

class Engine:
    def __init__(self,autostart=True,factories=None):
        self.events=queue.Queue(maxsize=300)
        self.commands=queue.Queue()
        self.command_lock=threading.Lock();self.pending_controls=None
        self.factories=factories or FACTORIES
        self.settings={};self.devices={};self.tasks={};self.status={};self.reports={}
        self.tests={};self.test_versions={};self.target=(255,80,35)
        self.capture=Capture(self.emit) if autostart else None
        self.running=True;self.scan_task=None
        self.thread=threading.Thread(target=lambda:asyncio.run(self.run()),daemon=True)
        if autostart:self.thread.start()
    def emit(self,kind,value):
        try:self.events.put_nowait((kind,value))
        except queue.Full:pass
    def submit(self,action,value=None):
        value=copy.deepcopy(value)
        with self.command_lock:
            # Continuous settings are a mailbox, not a history of obsolete slider values.
            if action=='controls':self.pending_controls=value;return
            if action=='settings':self.pending_controls=None
            self.commands.put((action,value))
    def take_controls(self):
        with self.command_lock:
            controls=self.pending_controls;self.pending_controls=None
        return controls
    def device_status(self,id,message):
        if self.status.get(id)!=message:
            self.status[id]=message;self.emit('device',(id,message))
    def snapshot(self):return self.capture.latest if self.capture else Output(self.target,1.,(),self.settings.get('mode','Solid'))
    def frame(self):return self.snapshot().rgb
    async def scan(self):
        try:
            from bleak import BleakScanner
            self.emit('scan_state',True)
            found=await asyncio.wait_for(BleakScanner.discover(timeout=7,return_adv=True),12)
            rows=[dict(address=d.address,name=a.local_name or d.name or 'Unnamed device',rssi=a.rssi,
                       services=a.service_uuids) for d,a in found.values()]
            rows.sort(key=lambda d:d['rssi'],reverse=True)
            self.emit('scan',rows)
        except Exception as e:self.emit('error',f'Bluetooth scan: {e}')
        finally:self.emit('scan_state',False)
    async def device_loop(self,id):
        attempt=0
        while id in self.devices and self.devices[id].get('enabled',True):
            config=self.devices[id];adapter=self.factories[config['kind']](config)
            try:
                self.device_status(id,'Connecting…')
                await adapter.connect()
                self.reports[id]=getattr(adapter,'gatt',{'adapter':config['kind']})
                self.device_status(id,'Connected' if config.get('verified') else 'Connected · test colors')
                last=None;last_test=-1;last_sent=time.monotonic();writes=0;rate_start=last_sent
                while self.running:
                    start=time.monotonic();config=self.devices[id]
                    if config['kind']=='ble' and not adapter.client.is_connected:raise ConnectionError('Bluetooth connection lost')
                    mode=self.settings.get('mode')
                    if mode=='Off':
                        if last!=((0,0,0),0) or (config['kind']!='ble' and start-last_sent>3):
                            await adapter.send((0,0,0),0);last=((0,0,0),0);last_sent=time.monotonic()
                            self.emit('off_sent',id)
                        await asyncio.sleep(.05);continue
                    if not config.get('verified'):
                        test=self.tests.get(id)
                        if test and test[0]!=last_test:
                            version,rgb=test
                            await adapter.send(rgb,60)
                            last_test=version
                            self.emit('tested',(id,rgb))
                        await asyncio.sleep(.05);continue
                    self.device_status(id,'Connected')
                    if self.settings.get('mode')=='Paused':
                        await asyncio.sleep(.05);continue
                    output=self.snapshot();rgb=output.rgb
                    if output.mode!=self.settings.get('mode'):await asyncio.sleep(.01);continue
                    brightness=round(cap_for(self.settings)*output.level)
                    if brightness==0:rgb=(0,0,0)
                    payload=(rgb,brightness)
                    # WLED/OpenRGB heartbeat checks the connection; BLE is_connected is checked above.
                    if payload!=last or (config['kind']!='ble' and start-last_sent>3):
                        await adapter.send(rgb,brightness)
                        last=payload;last_sent=time.monotonic();writes+=1
                        attempt=0
                    if start-rate_start>=2:
                        self.emit('rate',(id,round(writes/(start-rate_start),1)))
                        writes=0;rate_start=start
                    # Account for send duration, rather than adding a whole interval after the write.
                    await asyncio.sleep(max(.005,adapter.interval-(time.monotonic()-start)))
            except asyncio.CancelledError:raise
            except Exception as e:
                attempt+=1
                self.emit('log',f'{config["name"]}: {type(e).__name__}: {e}')
                logging.getLogger('lumaflow').exception('Device operation failed: %s',config['name'])
                if not self.settings.get('reconnect',True):
                    self.device_status(id,'Offline · click Retry');break
                delay=min(30,2**min(attempt,5))
                self.device_status(id,f'Retrying in {delay}s · {str(e)[:80]}')
            finally:
                try:await adapter.close()
                except Exception:pass
            if self.running:await asyncio.sleep(min(30,2**min(attempt,5)))
    async def reconcile(self,settings):
        old_reconnect=self.settings.get('reconnect',True)
        self.settings=settings
        if settings.get('mode')=='Off':self.tests.clear()
        if self.capture:self.capture.update(settings)
        new={d['id']:d for d in settings['devices']}
        for id,task in list(self.tasks.items()):
            before=self.devices.get(id);after=new.get(id)
            changed=after and any(before.get(k)!=after.get(k) for k in ['profile','address','kind'])
            if not after or not after.get('enabled',True) or changed or (task.done() and settings.get('reconnect') and not old_reconnect):
                task.cancel();await asyncio.gather(task,return_exceptions=True);self.tasks.pop(id,None)
                self.tests.pop(id,None)
                self.device_status(id,'Disconnected')
        self.devices=new
        for id,d in new.items():
            if d.get('enabled',True) and id not in self.tasks:
                self.tasks[id]=asyncio.create_task(self.device_loop(id))
            elif not d.get('enabled',True):self.device_status(id,'Disconnected')
    async def retry_device(self,id):
        if id not in self.devices or not self.devices[id].get('enabled',True):return
        task=self.tasks.pop(id,None)
        if task:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
        self.tasks[id]=asyncio.create_task(self.device_loop(id))
    def apply_controls(self,controls):
        # Device membership and mode transitions must go through reconcile, never this mailbox.
        ignored={'devices','mode','last_active_mode','reconnect'}
        self.settings.update({k:v for k,v in controls.items() if k not in ignored})
        if self.capture:self.capture.update(self.settings)
    async def list_displays(self):
        def read():
            import mss
            with mss.mss() as screen:return [dict(index=i,**monitor) for i,monitor in enumerate(screen.monitors) if i]
        try:self.emit('displays',await asyncio.to_thread(read))
        except Exception as e:self.emit('log',f'Display list unavailable: {e}')
    async def run(self):
        try:
            if sys.platform=='win32':
                from bleak.backends.winrt.util import uninitialize_sta
                uninitialize_sta()
            while self.running:
                try:
                    action,value=self.commands.get_nowait()
                    if action=='quit':self.running=False
                    elif action=='settings':await self.reconcile(value)
                    elif action=='retry_device':await self.retry_device(value)
                    elif action=='retry_source':
                        self.settings['_source_revision']=self.settings.get('_source_revision',0)+1
                        if self.capture:self.capture.update(self.settings)
                    elif action=='list_displays':asyncio.create_task(self.list_displays())
                    elif action=='scan' and (self.scan_task is None or self.scan_task.done()):self.scan_task=asyncio.create_task(self.scan())
                    elif action=='test':
                        id,rgb=value;v=self.test_versions.get(id,0)+1;self.test_versions[id]=v;self.tests[id]=(v,tuple(rgb))
                except queue.Empty:pass
                except Exception as e:self.emit('error',str(e))
                controls=self.take_controls()
                if controls is not None and self.running:self.apply_controls(controls)
                await asyncio.sleep(.015)
        except Exception as e:self.emit('error',f'Engine stopped: {e}')
        finally:
            tasks=list(self.tasks.values())+([self.scan_task] if self.scan_task else [])
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if self.capture:self.capture.close()
            self.emit('closed',None)
