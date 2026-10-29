"""Latest-frame synchronization. Each device has its own cancellable worker."""
import asyncio
import copy
import queue
import threading
import time
import sys
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
        try:
            while not self.stop_event.is_set():
                start=time.monotonic();dt=start-last;last=start
                with self.lock:s=self.settings.copy()
                mode=s.get('mode','Paused');key=(mode,s.get('audio'),s.get('monitor'))
                try:
                    if mode!='Screen' and screen:screen.close();screen=None
                    if (mode!='Music' or audio_key!=s.get('audio')) and stream:
                        stream.stop_stream();stream.close();stream=None;pa.terminate();pa=None
                        audio_frame=(0,None)
                    if mode=='Paused':
                        failed_key=None;self.stop_event.wait(.05);continue
                    if mode!=last_mode:phase=0;was_dark=False;last_mode=mode
                    bars=();measured=0.
                    if key==failed_key:self.stop_event.wait(.1);continue
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
                        if stream is None:
                            import pyaudiowpatch as p
                            import numpy as np
                            pa=p.PyAudio();audio_key=s['audio']
                            d=pa.get_default_wasapi_loopback() if audio_key=='Speakers' else pa.get_default_input_device_info()
                            rate=int(d['defaultSampleRate']);channels=int(d['maxInputChannels'])
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
                    failed_key=None
                except Exception as e:
                    failed_key=key
                    self.emit('source_error',str(e))
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
    def submit(self,action,value=None):self.commands.put((action,copy.deepcopy(value)))
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
                if not self.settings.get('reconnect',True):
                    self.device_status(id,'Offline · click Connect to retry');break
                delay=min(30,2**min(attempt,5))
                self.device_status(id,f'Retrying in {delay}s · {str(e)[:80]}')
            finally:
                try:await adapter.close()
                except Exception:pass
            if self.running:await asyncio.sleep(min(30,2**min(attempt,5)))
    async def reconcile(self,settings):
        old_reconnect=self.settings.get('reconnect',True)
        self.settings=settings
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
                    elif action=='scan' and (self.scan_task is None or self.scan_task.done()):self.scan_task=asyncio.create_task(self.scan())
                    elif action=='test':
                        id,rgb=value;v=self.test_versions.get(id,0)+1;self.test_versions[id]=v;self.tests[id]=(v,tuple(rgb))
                except queue.Empty:pass
                except Exception as e:self.emit('error',str(e))
                await asyncio.sleep(.015)
        except Exception as e:self.emit('error',f'Engine stopped: {e}')
        finally:
            tasks=list(self.tasks.values())+([self.scan_task] if self.scan_task else [])
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if self.capture:self.capture.close()
            self.emit('closed',None)
