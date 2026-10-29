"""LumaFlow — native Qt desktop app."""
import copy
import json
import sys
import time
import uuid
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QLockFile
from PySide6.QtGui import QColor,QIcon,QPainter,QPixmap,QLinearGradient,QFont
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QFrame,QVBoxLayout,QHBoxLayout,
    QLabel,QPushButton,QStackedWidget,QSlider,QComboBox,QColorDialog,QListWidget,QListWidgetItem,
    QDialog,QDialogButtonBox,QLineEdit,QFormLayout,QMessageBox,QSystemTrayIcon,QMenu,
    QFileDialog,QPlainTextEdit,QScrollArea,QSpinBox,QAbstractButton,QGridLayout)
from model import Store,data_dir,scale,ACTIVE_MODES
from signals import cap_for
from visuals import LivePreview,icon,logo
from effects import EFFECTS
from engine import Engine
from windows import startup_enabled,set_startup
from theme import STYLE
from controls import BrightnessSlider,IconButton
from version import APP_VERSION,build_info
from diagnostics import export_payload,configure_logging
import logging

class Toggle(QAbstractButton):
    def __init__(self,checked=False,callback=None):
        super().__init__();self.setCheckable(True);self.setChecked(checked);self.setFixedSize(48,28)
        self.setCursor(Qt.PointingHandCursor);self.setAccessibleName('Toggle setting')
        if callback:self.toggled.connect(callback)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.setPen(Qt.NoPen)
        p.setBrush(QColor('#b7f781' if self.isChecked() else '#3a455a'));p.drawRoundedRect(0,1,48,26,13,13)
        p.setBrush(QColor('#15230e' if self.isChecked() else '#dce4f4'));p.drawEllipse(26 if self.isChecked() else 4,5,18,18)


def label(text,object_name=None):
    x=QLabel(text);x.setWordWrap(True)
    if object_name:x.setObjectName(object_name)
    return x

def button(text,fn,primary=False):
    b=QPushButton(text);b.clicked.connect(fn);b.setCursor(Qt.PointingHandCursor)
    if primary:b.setObjectName('primary')
    return b

def card():
    f=QFrame();f.setObjectName('card');v=QVBoxLayout(f);v.setContentsMargins(22,20,22,20);v.setSpacing(14)
    return f,v

class AddDialog(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('Add a light');self.resize(650,540)
        self.parent=parent;self.result_device=None
        v=QVBoxLayout(self);v.setContentsMargins(24,24,24,24);v.setSpacing(14)
        v.addWidget(label('Add a light','title'))
        v.addWidget(label('Choose an integration. Devices stay on your local network.','subtitle'))
        self.kind=QComboBox();self.kind.addItems(['Bluetooth · ELK / MELK','Wi-Fi · WLED','Wired / PC · OpenRGB'])
        v.addWidget(self.kind)
        self.hint=label('Turn on your bars and close their phone app. Scan, then select your controller.','subtitle');v.addWidget(self.hint)
        self.scan_btn=button('Scan nearby Bluetooth lights',self.scan);v.addWidget(self.scan_btn)
        self.list=QListWidget();v.addWidget(self.list)
        form=QFormLayout();v.addLayout(form)
        self.name=QLineEdit();self.name.setPlaceholderText('e.g. Desk light bars');form.addRow('Name',self.name)
        self.address=QLineEdit();self.address.setPlaceholderText('Select a Bluetooth result above');form.addRow('Address / device name',self.address)
        self.profile=QComboBox();self.profile.addItems(['MELK','BLEDOB','RGB only']);form.addRow('Bluetooth profile',self.profile)
        self.note=label('MELK uses native brightness. Use RGB only if the brightness command is not supported.','subtitle');v.addWidget(self.note)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);v.addWidget(buttons)
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject)
        self.kind.currentIndexChanged.connect(self.change);self.list.itemSelectionChanged.connect(self.select)
    def change(self,index):
        ble=index==0
        self.list.setVisible(ble);self.scan_btn.setVisible(ble);self.profile.setEnabled(ble);self.note.setVisible(ble)
        self.address.clear()
        self.hint.setText(['Turn on your bars and close their phone app. Scan, then select your controller.',
            'For lights already running WLED. Enter their local IP address or hostname. All active segments will match.',
            'Start OpenRGB and its SDK server on port 6742 first. Enter the exact, unique device name shown in OpenRGB. Requires Direct mode.'][index])
        self.address.setPlaceholderText(['Select a Bluetooth result above','192.168.1.50 or wled.local','Exact device name in OpenRGB'][index])
    def scan(self):self.scan_btn.setEnabled(False);self.scan_btn.setText('Scanning…');self.parent.engine.submit('scan')
    def results(self,rows):
        self.list.clear()
        for d in rows:
            item=QListWidgetItem(f'{d["name"]}    ·    {d["rssi"]} dBm');item.setData(Qt.UserRole,d);self.list.addItem(item)
        if not rows:self.hint.setText('No BLE advertisements found. Check Bluetooth and power; close the phone app and retry.')
    def select(self):
        item=self.list.currentItem()
        if item:
            d=item.data(Qt.UserRole);self.address.setText(d['address']);self.name.setText(d['name'])
            self.profile.setCurrentText('MELK' if d['name'].startswith('MELK') else 'BLEDOB' if 'BLEDOB' in d['name'] else 'RGB only')
    def save(self):
        address=self.address.text().strip();name=self.name.text().strip() or address
        kind=['ble','wled','openrgb'][self.kind.currentIndex()]
        if not address:QMessageBox.information(self,'Missing device','Choose or enter a device first.');return
        if kind=='ble':
            import re
            if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}',address):
                QMessageBox.information(self,'Bluetooth address','Choose a device from Scan.');return
        if kind=='wled':
            from adapters import host
            try:host(address)
            except ValueError as e:QMessageBox.information(self,'Address',str(e));return
        if any(d['kind']==kind and d['address'].lower()==address.lower() for d in self.parent.s['devices']):
            QMessageBox.information(self,'Already added','This device is already saved.');return
        self.result_device=dict(id=uuid.uuid4().hex,name=name,address=address,kind=kind,
            profile=self.profile.currentText(),verified=kind!='ble',enabled=True)
        self.accept()

class Window(QMainWindow):
    def __init__(self,store=None,engine=None):
        super().__init__();self.store=store or Store();self.s=self.store.data;self.engine=engine or Engine()
        self.statuses={};self.rates={};self.tested={};self.logs=[];self.closing=False;self.dialog=None
        self.build=build_info();self.off_sent=set();self.source_failed=False
        self.save_timer=QTimer(self);self.save_timer.setSingleShot(True);self.save_timer.setInterval(250)
        self.save_timer.timeout.connect(self.persist)
        self.setWindowTitle(f'LumaFlow {APP_VERSION}');self.resize(1130,870);self.setMinimumSize(900,620)
        self.setStyleSheet(STYLE)
        self.icon=icon();self.setWindowIcon(self.icon)
        root=QWidget();self.setCentralWidget(root);layout=QHBoxLayout(root);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        side=QFrame();side.setObjectName('sidebar');side.setFixedWidth(190);sv=QVBoxLayout(side);sv.setContentsMargins(22,30,20,24);sv.setSpacing(12)
        sv.addWidget(label('LumaFlow','brand'));sv.addWidget(label(f'LIGHTING / {APP_VERSION}','eyebrow'));sv.addSpacing(24)
        build_label=label('Build '+self.build['build_id'].split('.')[-1],'subtitle');build_label.setToolTip(self.build['build_id']);sv.insertWidget(2,build_label)
        self.stack=QStackedWidget();self.nav=[]
        for i,name in enumerate(['Studio','Devices','Settings','Diagnostics']):
            b=button(name,lambda checked=False,n=i:self.navigate(n));b.setObjectName('nav');b.setCheckable(True);self.nav.append(b);sv.addWidget(b)
        sv.addStretch();sv.addWidget(label('Your space.\nOne atmosphere.','section'));sv.addWidget(label('Local control\nBluetooth · Wi-Fi · PC','subtitle'))
        layout.addWidget(side)
        stage=QVBoxLayout();stage.setContentsMargins(0,0,0,0);stage.setSpacing(0)
        top=QHBoxLayout();top.setContentsMargins(32,14,32,0);top.addWidget(label('LIGHTING STUDIO','eyebrow'));top.addStretch()
        self.control_state=label('Paused','subtitle');top.addWidget(self.control_state);top.addSpacing(8)
        self.pause_button=IconButton('pause','Pause lighting',self.toggle_pause)
        self.power_button=IconButton('power','Turn lights off',self.toggle_power)
        self.power_button.setObjectName('powerButton')
        top.addWidget(self.pause_button);top.addWidget(self.power_button);stage.addLayout(top);stage.addWidget(self.stack,1)
        layout.addLayout(stage,1)
        self.build_studio();self.build_devices();self.build_settings();self.build_diagnostics();self.navigate(0)
        self.tray=QSystemTrayIcon(self.icon,self);menu=QMenu()
        menu.addAction('Open LumaFlow',self.reveal);menu.addAction('Pause sync',lambda:self.set_mode('Paused'))
        menu.addAction('Turn lights off',lambda:self.set_mode('Off'))
        menu.addAction('Quit',self.quit);self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason:self.reveal() if reason==QSystemTrayIcon.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
        if not self.s.get('resume') and self.s['mode']!='Off':self.s['mode']='Paused'
        self.sync_mode_buttons();self.render_devices()
        self.engine.submit('settings',self.s)
        self.engine.submit('list_displays')
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(33)
        if self.store.warning:self.log(self.store.warning)
    def page(self,eyebrow,title,subtitle):
        page=QWidget();outer=QVBoxLayout(page);outer.setContentsMargins(0,0,0,0)
        scroll=QScrollArea();scroll.setWidgetResizable(True);outer.addWidget(scroll)
        content=QWidget();scroll.setWidget(content);v=QVBoxLayout(content);v.setContentsMargins(32,30,32,24);v.setSpacing(18)
        v.addWidget(label(eyebrow,'eyebrow'));v.addWidget(label(title,'title'));v.addWidget(label(subtitle,'subtitle'))
        self.stack.addWidget(page);return v
    def build_studio(self):
        v=self.page('YOUR ROOM, IN SYNC','Let your room feel it.','Color, sound and motion. One shared atmosphere for your lights.')
        f,c=card();v.addWidget(f)
        head=QHBoxLayout();head.addWidget(label('Live atmosphere','section'));head.addStretch()
        self.connection=label('No lights connected','subtitle');head.addWidget(self.connection);c.addLayout(head)
        preview_row=QHBoxLayout();preview_row.setSpacing(20)
        self.preview=LivePreview();preview_row.addWidget(self.preview,1)
        self.brightness_stack=QStackedWidget();self.brightness_stack.setFixedWidth(112)
        self.brightness_stack.setStyleSheet('QStackedWidget { background: transparent; }')
        preview_row.addWidget(self.brightness_stack,0,Qt.AlignVCenter);c.addLayout(preview_row)
        self.mode_buttons={};row=QHBoxLayout()
        for mode,text in [('Solid','Solid color'),('Screen','Screen mirror'),('Music','Music sync'),('Atmosphere','Atmosphere')]:
            b=button(text,lambda checked=False,m=mode:self.set_mode(m));b.setCheckable(True);row.addWidget(b);self.mode_buttons[mode]=b
        c.addLayout(row)
        self.mode_hint=label('','subtitle');c.addWidget(self.mode_hint)
        self.output_info=label('Requested output · waiting for a source','eyebrow');c.addWidget(self.output_info)
        self.source_notice=label('','subtitle');self.source_notice.hide();c.addWidget(self.source_notice)
        self.source_retry=button('Retry source now',lambda:self.engine.submit('retry_source'));self.source_retry.hide();c.addWidget(self.source_retry)
        self.mode_panels={};self.brightness_sliders={}
        for mode in ['Solid','Screen','Music','Atmosphere']:
            panel,layout=card();self.mode_panels[mode]=panel;v.addWidget(panel)
            layout.addWidget(label({'Solid':'Your color, exactly.','Screen':'Screen mirror studio','Music':'Follow the music','Atmosphere':'An atmosphere for every moment'}[mode],'section'))
            brightness_box=QWidget();brightness_box.setObjectName('brightnessBox');brightness_layout=QVBoxLayout(brightness_box)
            brightness_layout.setContentsMargins(12,8,12,12);brightness_layout.setAlignment(Qt.AlignHCenter)
            number=label(str(self.s[mode.lower()+'_brightness'])+'%','brightnessValue');number.setAlignment(Qt.AlignCenter)
            brightness_layout.addWidget(number)
            slider=BrightnessSlider(self.s[mode.lower()+'_brightness'],lambda value,m=mode:self.change(m.lower()+'_brightness',value))
            slider.setAccessibleName(f'{mode} maximum brightness');slider.valueChanged.connect(lambda value,n=number:n.setText(f'{value}%'))
            brightness_layout.addWidget(slider,0,Qt.AlignHCenter)
            caption=label('Brightness','subtitle');caption.setAlignment(Qt.AlignCenter);brightness_layout.addWidget(caption)
            self.brightness_stack.addWidget(brightness_box);self.brightness_sliders[mode]=slider
            if mode=='Solid':self.brightness_slider=slider
            if mode=='Solid':
                colorrow=QHBoxLayout();palette=QGridLayout();palette.setSpacing(10);colorrow.addLayout(palette)
                for index,color in enumerate(['#ff0000','#ff7a24','#ffd966','#00ff00','#0000ff','#a77bff','#ff63b4','#ffffff']):
                    btn=button('',lambda checked=False,h=color:self.pick_hex(h));btn.setFixedSize(34,34)
                    btn.setStyleSheet(f'background:{color};border-radius:17px;border:2px solid #52617b;padding:0;');btn.setToolTip(color);btn.setAccessibleName(color);palette.addWidget(btn,index//4,index%4)
                colorrow.addStretch();colorrow.addWidget(button('Custom color…',self.choose_color));layout.addLayout(colorrow)
                layout.addWidget(label('A steady light. The preview orb gently moves; your LEDs keep a constant color.','subtitle'))
            elif mode=='Screen':
                row=QHBoxLayout();row.addWidget(label('Sample from','subtitle'));self.region=QComboBox();self.region.addItems(['Whole screen','Left edge','Right edge','Top edge']);self.region.setCurrentText(self.s['region']);self.region.currentTextChanged.connect(lambda x:self.change('region',x));row.addWidget(self.region,1)
                layout.addLayout(row)
                displays=QHBoxLayout();displays.addWidget(label('Display','subtitle'));self.monitor=QComboBox()
                self.monitor.setAccessibleName('Screen capture display');self.monitor.addItem(f'Display {self.s["monitor"]}',self.s['monitor'])
                self.monitor.currentIndexChanged.connect(lambda index:self.change('monitor',self.monitor.itemData(index)) if index>=0 else None)
                displays.addWidget(self.monitor,1);displays.addWidget(button('Refresh',lambda:self.engine.submit('list_displays')));layout.addLayout(displays)
                self.toggle_row(layout,'Follow scene brightness','Dark scenes dim the room; brighter scenes raise the light up to your maximum.',self.s['auto_brightness'],lambda x:self.change('auto_brightness',x))
                self.toggle_row(layout,'Prefer rich colors','Chooses the dominant hue instead of mixing white into red, green or blue.',self.s['vivid'],lambda x:self.change('vivid',x))
                self.slider(layout,'Color saturation',self.s['saturation'],0,250,lambda x:self.change('saturation',x),'%')
                self.slider(layout,'Scene exposure',self.s['exposure'],25,200,lambda x:self.change('exposure',x),'%')
                self.slider(layout,'Dark-scene depth',self.s['screen_gamma'],50,200,lambda x:self.change('screen_gamma',x),'%')
                self.slider(layout,'Blackout below scene level',self.s['black_threshold'],0,12,lambda x:self.change('black_threshold',x),'%')
                layout.addWidget(label('Below the blackout threshold, LEDs receive zero brightness immediately, without a smoothing tail. A tiny bright cursor will not keep a dark scene lit.','subtitle'))
                self.toggle_row(layout,'Ignore movie black bars','Crops near-black borders before sampling. Interior shadows still dim the lights.',self.s['ignore_bars'],lambda x:self.change('ignore_bars',x))
                self.slider(layout,'Color transition softness',self.s['smoothing'],0,600,lambda x:self.change('smoothing',x),' ms')
                self.slider(layout,'Brightness response',self.s['screen_response'],0,300,lambda x:self.change('screen_response',x),' ms')
            elif mode=='Music':
                row=QHBoxLayout();row.addWidget(label('Listen to','subtitle'));combo=QComboBox();combo.addItems(['Speakers','Microphone']);combo.setCurrentText(self.s['audio']);combo.currentTextChanged.connect(lambda x:self.change('audio',x));row.addWidget(combo,1)
                row.addWidget(button('Refresh audio',lambda:self.engine.submit('retry_source')));layout.addLayout(row)
                self.slider(layout,'Music sensitivity',self.s['gain'],1,30,lambda x:self.change('gain',x),'×')
                self.slider(layout,'Silence cutoff',self.s['noise_gate'],0,60,lambda x:self.change('noise_gate',x),'')
                self.slider(layout,'Color transition softness',self.s['music_smoothing'],0,300,lambda x:self.change('music_smoothing',x),' ms')
                self.slider(layout,'Brightness response',self.s['music_response'],0,300,lambda x:self.change('music_response',x),' ms')
                layout.addWidget(label('The spectrum uses live audio. Louder passages brighten the lights; silence sends exact zero. Raise sensitivity for quiet music, or lower it if brightness stays at maximum.','subtitle'))
            else:
                row=QHBoxLayout();row.addWidget(label('Effect','subtitle'));self.effect=QComboBox();self.effect.addItems(EFFECTS);self.effect.setCurrentText(self.s['effect']);self.effect.currentTextChanged.connect(lambda x:self.change('effect',x));row.addWidget(self.effect,1);layout.addLayout(row)
                self.slider(layout,'Cycle duration · shorter is faster',self.s['cycle_seconds'],2,60,lambda x:self.change('cycle_seconds',x),' s')
                layout.addWidget(label('24 effects generated by LumaFlow. Rainbow, aurora, candlelight, breathing, police colors and more. Both bars share one evolving color.','subtitle'))
        self.banner=label('Add your light bars in Devices to get started.','subtitle');v.addWidget(self.banner);v.addStretch()
    def slider(self,layout,title,value,lo,hi,fn,suffix):
        row=QHBoxLayout();row.addWidget(label(title));row.addStretch();number=label(str(value)+suffix,'eyebrow');row.addWidget(number);layout.addLayout(row)
        slider=QSlider(Qt.Horizontal);slider.setRange(lo,hi);slider.setValue(value);slider.setAccessibleName(title)
        slider.valueChanged.connect(lambda n:(number.setText(str(n)+suffix),fn(n)));layout.addWidget(slider);return slider
    def toggle_row(self,layout,title,description,checked,fn):
        row=QHBoxLayout();words=QVBoxLayout();words.addWidget(label(title));words.addWidget(label(description,'subtitle'));row.addLayout(words,1)
        toggle=Toggle(checked,fn);toggle.setAccessibleName(title);row.addWidget(toggle);layout.addLayout(row);return toggle
    def build_devices(self):
        v=self.page('YOUR LIGHTS','Bring everything together.','Save compatible devices once. Connection status is shown for every light.')
        row=QHBoxLayout();row.addWidget(button('+ Add a light',self.add_device,True));row.addStretch();v.addLayout(row)
        self.device_list=QVBoxLayout();v.addLayout(self.device_list)
        v.addWidget(label('Supported integrations: MELK / ELK RGB over Bluetooth, WLED over Wi-Fi, and local OpenRGB devices with Direct mode. Other brands need an adapter.','subtitle'));v.addStretch()
    def build_settings(self):
        v=self.page('PREFERENCES','Make it yours.','Settings save automatically. No Apply button needed.')
        f,c=card();v.addWidget(f);c.addWidget(label('Startup & background','section'))
        self.start_toggle=self.toggle_row(c,'Launch when I sign in to Windows','Starts for your Windows account. Move the app first, then enable this.',startup_enabled(),self.startup)
        self.toggle_row(c,'Start in the system tray','On automatic startup, keep the main window out of the way.',self.s['start_hidden'],lambda x:self.change('start_hidden',x))
        self.toggle_row(c,'Keep running when I close the window','Closing hides the app in the tray. Use Quit to stop it.',self.s['tray'],lambda x:self.change('tray',x))
        self.toggle_row(c,'Resume the last lighting mode','Allows screen or audio capture to resume when the app starts.',self.s['resume'],lambda x:self.change('resume',x))
        f,c=card();v.addWidget(f);c.addWidget(label('Connections & privacy','section'))
        self.toggle_row(c,'Animate previews','Decorative motion in the Solid and Atmosphere previews. Audio bars always show live measurements.',self.s['animations'],lambda x:self.change('animations',x))
        self.toggle_row(c,'Reconnect after a signal drop','Retries temporarily unavailable devices. Manually disconnected devices stay off.',self.s['reconnect'],lambda x:self.change('reconnect',x))
        c.addWidget(label('Enabled devices reconnect at launch. Disconnect in Devices to stop remembering an active connection. Forget removes the saved device.','subtitle'))
        c.addWidget(label('Screen and audio are processed in memory. No recordings, cloud account or telemetry. Diagnostics can contain device names and local addresses.','subtitle'))
        c.addWidget(button('Open settings folder',self.open_folder));v.addStretch()
    def build_diagnostics(self):
        v=self.page('TROUBLESHOOTING','A little more detail.','For connection errors and compatibility checks. You can ignore this during normal use.')
        v.addWidget(button('Export diagnostics',self.export))
        self.redact_export=True
        self.toggle_row(v,'Hide device details in exports','Replaces saved names, addresses and device IDs before sharing.',True,lambda value:setattr(self,'redact_export',value))
        v.addWidget(label(f'Version {APP_VERSION}\nBuild ID: {self.build["build_id"]}','subtitle'))
        self.logbox=QPlainTextEdit();self.logbox.setReadOnly(True);self.logbox.setMinimumHeight(370);self.logbox.document().setMaximumBlockCount(400);v.addWidget(self.logbox)
        v.addWidget(label('The preview shows requested output, not feedback from the LEDs. Adapters are tested in software; actual timing and brightness depend on the device.','subtitle'));v.addStretch()
    def navigate(self,index):
        self.stack.setCurrentIndex(index)
        for i,b in enumerate(self.nav):b.setChecked(i==index)
    def change(self,key,value):
        self.s[key]=value
        if key in ('devices','mode','reconnect'):
            self.persist();self.engine.submit('settings',self.s)
        else:
            self.save_timer.start();self.engine.submit('controls',self.s)
    def persist(self):
        self.save_timer.stop()
        try:self.store.save()
        except Exception as e:self.log(f'Could not save settings: {e}');self.banner.setText('Settings could not be saved. Check the settings folder permissions.')
    def set_mode(self,mode):
        if mode in ACTIVE_MODES:self.s['last_active_mode']=mode
        if mode=='Off':self.off_sent.clear()
        self.source_failed=False;self.source_notice.hide();self.source_retry.hide()
        self.change('mode',mode);self.sync_mode_buttons()
    def toggle_pause(self):
        if self.s['mode']=='Off':return
        self.set_mode(self.s['last_active_mode'] if self.s['mode']=='Paused' else 'Paused')
    def toggle_power(self):
        self.set_mode(self.s['last_active_mode'] if self.s['mode']=='Off' else 'Off')
    def sync_mode_buttons(self):
        for m,b in self.mode_buttons.items():b.setChecked(m==self.s['mode'])
        for m,panel in self.mode_panels.items():panel.setVisible(m==self.s['mode'])
        mode=self.s['mode'];paused=mode=='Paused';off=mode=='Off'
        self.brightness_stack.setVisible(mode in ACTIVE_MODES)
        if mode in ACTIVE_MODES:self.brightness_stack.setCurrentIndex(ACTIVE_MODES.index(mode))
        self.pause_button.symbol='play' if paused else 'pause';self.pause_button.setChecked(paused)
        self.pause_button.setEnabled(not off)
        pause_name='Resume lighting' if paused else 'Pause lighting — hold the current color'
        self.pause_button.setAccessibleName(pause_name);self.pause_button.setToolTip(pause_name)
        self.power_button.setChecked(off)
        power_name='Turn lights on — resume '+self.s['last_active_mode'] if off else 'Turn lights off'
        self.power_button.setAccessibleName(power_name);self.power_button.setToolTip(power_name)
        self.control_state.setText('Lights off requested' if off else 'Paused' if paused else mode)
        self.mode_hint.setText({'Solid':'Pick a color below. Your LEDs stay steady.',
            'Screen':'Your screen sets the hue and intensity. Black scenes turn the lights off.',
            'Music':'Live sound sets the color and intensity. Silence turns the lights off.',
            'Atmosphere':'A moving palette for your room. Choose an effect below.',
            'Paused':'Capture and output are paused. Lights keep their last color.',
            'Off':'Zero output requested. The app stays connected. Press Power again to resume.'}[self.s['mode']])
    def pick_hex(self,h):
        color=QColor(h);self.s['color']=[color.red(),color.green(),color.blue()];self.set_mode('Solid')
    def choose_color(self):
        c=QColorDialog.getColor(QColor(*self.s['color']),self,'Choose a color')
        if c.isValid():self.pick_hex(c.name())
    def add_device(self):
        self.dialog=AddDialog(self)
        if self.dialog.exec()==QDialog.Accepted:
            self.s['devices'].append(self.dialog.result_device);self.change('devices',self.s['devices']);self.render_devices()
        self.dialog=None
    def device_action(self,id,action):
        d=next(d for d in self.s['devices'] if d['id']==id)
        if action=='retry':self.engine.submit('retry_device',id);return
        if action=='forget':
            if QMessageBox.question(self,'Forget device',f'Remove {d["name"]} from saved lights?')!=QMessageBox.Yes:return
            self.s['devices']=[d for d in self.s['devices'] if d['id']!=id]
        elif action=='toggle':d['enabled']=not d.get('enabled',True)
        elif action=='verify':
            if len(self.tested.get(id,set()))<3:
                QMessageBox.information(self,'Test colors first','Wait for this device to connect, then test red, green and blue.');return
            if QMessageBox.question(self,'Confirm colors','Did this device display the correct red, green and blue?')!=QMessageBox.Yes:return
            d['verified']=True
        self.change('devices',self.s['devices']);self.render_devices()
    def profile_changed(self,id,profile):
        d=next(d for d in self.s['devices'] if d['id']==id);d['profile']=profile;d['verified']=False;self.tested[id]=set()
        self.change('devices',self.s['devices']);QTimer.singleShot(0,self.render_devices)
    def render_devices(self):
        while self.device_list.count():
            item=self.device_list.takeAt(0)
            if item.widget():item.widget().deleteLater()
        self.device_labels={};self.retry_buttons={}
        if not self.s['devices']:
            f,c=card();c.addWidget(label('Your desk is ready for its first light.','section'));c.addWidget(label('Add your NBBUFF bars over Bluetooth, then check the three colors once.','subtitle'));self.device_list.addWidget(f)
        for d in self.s['devices']:
            id=d['id'];f,c=card();row=QHBoxLayout();row.addWidget(label(d['name'],'section'));row.addStretch()
            row.addWidget(button('Disconnect' if d.get('enabled',True) else 'Connect',lambda checked=False,i=id:self.device_action(i,'toggle')))
            retry=button('Retry',lambda checked=False,i=id:self.device_action(i,'retry'))
            retry.setVisible(d.get('enabled',True) and self.statuses.get(id,'').startswith(('Offline','Retrying')))
            self.retry_buttons[id]=retry;row.addWidget(retry)
            row.addWidget(button('Forget',lambda checked=False,i=id:self.device_action(i,'forget')));c.addLayout(row)
            text=label(self.statuses.get(id,'Connecting…' if d.get('enabled',True) else 'Disconnected'),'subtitle');self.device_labels[id]=text;c.addWidget(text)
            c.addWidget(label(f'{d["kind"].upper()}  ·  {d["address"]}','subtitle'))
            if d['kind']=='ble':
                row=QHBoxLayout();row.addWidget(label('Brightness control','subtitle'));p=QComboBox();p.addItems(['MELK','BLEDOB','RGB only']);p.setCurrentText(d.get('profile','RGB only'));p.currentTextChanged.connect(lambda x,i=id:self.profile_changed(i,x));row.addWidget(p,1);c.addLayout(row)
                if not d.get('verified'):
                    c.addWidget(label('One-time check: do these three colors match on the physical lights?','subtitle'))
                    row=QHBoxLayout()
                    for name,rgb in [('Red',(255,0,0)),('Green',(0,255,0)),('Blue',(0,0,255))]:
                        row.addWidget(button(name,lambda checked=False,i=id,r=rgb:self.engine.submit('test',(i,r))))
                    row.addWidget(button('Colors match',lambda checked=False,i=id:self.device_action(i,'verify'),True));c.addLayout(row)
            self.device_list.addWidget(f)
    def startup(self,enabled):
        try:set_startup(enabled)
        except Exception as e:
            self.start_toggle.blockSignals(True);self.start_toggle.setChecked(not enabled);self.start_toggle.blockSignals(False)
            QMessageBox.warning(self,'Startup setting',str(e))
    def open_folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_dir())))
    def log(self,message):
        logging.getLogger('lumaflow').info(message)
        line=time.strftime('%H:%M:%S')+'  '+message;self.logs.append(line);self.logs=self.logs[-300:]
        self.logbox.appendPlainText(line)
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'Export diagnostics','lumaflow-diagnostics.json','JSON (*.json)')
        if path:
            try:
                payload=export_payload(self.s,self.statuses,self.engine.reports,self.logs,self.build,self.redact_export)
                Path(path).write_text(json.dumps(payload,indent=2),encoding='utf-8')
                self.banner.setText('Diagnostics exported.')
            except Exception as e:QMessageBox.warning(self,'Export failed',str(e))
    def reveal(self):self.showNormal();self.raise_();self.activateWindow()
    def closeEvent(self,event):
        if self.closing:event.ignore();return
        if self.s['tray'] and QSystemTrayIcon.isSystemTrayAvailable():self.hide();event.ignore()
        else:event.ignore();self.quit()
    def quit(self):
        if self.closing:return
        self.persist();self.closing=True;self.banner.setText('Closing connections…');self.engine.submit('quit')
        self.setEnabled(False)
    def poll(self):
        import queue
        for _ in range(100):
            try:kind,value=self.engine.events.get_nowait()
            except queue.Empty:break
            if kind=='closed':self.tray.hide();QApplication.instance().quit();return
            if kind=='device':
                id,text=value;self.statuses[id]=text
                if not text.startswith('Connected'):self.off_sent.discard(id)
                if id in self.device_labels:self.device_labels[id].setText(text)
                if id in self.retry_buttons:self.retry_buttons[id].setVisible(text.startswith(('Offline','Retrying')))
            elif kind=='rate':self.rates[value[0]]=value[1]
            elif kind=='scan' and self.dialog:self.dialog.results(value)
            elif kind=='scan_state' and self.dialog:
                self.dialog.scan_btn.setEnabled(not value);self.dialog.scan_btn.setText('Scanning…' if value else 'Scan nearby Bluetooth lights')
            elif kind=='tested':
                id,rgb=value;self.tested.setdefault(id,set()).add(tuple(rgb));self.log('Test color sent: '+str(rgb))
            elif kind=='off_sent':self.off_sent.add(value)
            elif kind=='displays':
                self.monitor.blockSignals(True);self.monitor.clear()
                for display in value:
                    self.monitor.addItem(f'Display {display["index"]} · {display["width"]} × {display["height"]}',display['index'])
                selected=self.monitor.findData(self.s['monitor'])
                if selected<0:self.monitor.addItem(f'Display {self.s["monitor"]} · unavailable',self.s['monitor']);selected=self.monitor.count()-1
                self.monitor.setCurrentIndex(selected);self.monitor.blockSignals(False)
            elif kind=='source_recovered':
                if value==self.s['mode']:
                    self.source_failed=False;self.source_notice.hide();self.source_retry.hide();self.log('Capture source recovered.')
                    self.banner.setText('Capture source recovered. Changes save automatically.')
            elif kind in ['error','log','source_error']:
                message=value['message'] if isinstance(value,dict) else value
                self.log(message)
                if kind!='log':self.banner.setText(message)
                if kind=='source_error' and self.s['mode'] in ('Screen','Music'):
                    if isinstance(value,dict) and value['mode']!=self.s['mode']:continue
                    self.source_failed=True;self.source_notice.setText('Source unavailable. Output is zero while LumaFlow retries: '+message)
                    self.source_notice.show();self.source_retry.show()
        count=sum(self.statuses.get(d['id'],'').startswith('Connected') for d in self.s['devices'])
        self.connection.setText(f'{count} / {len(self.s["devices"])} connected')
        if self.isVisible() and self.stack.currentIndex()==0:
            out=self.engine.snapshot();effective=round(cap_for(self.s)*out.level)
            if self.s['mode']=='Paused':effective=0;rgb=self.preview.rgb
            elif self.s['mode']=='Off' or out.mode!=self.s['mode']:effective=0;rgb=(0,0,0)
            else:rgb=scale(out.rgb,effective)
            self.preview.advance(rgb,self.s['mode'],out.spectrum,effective/100,self.s['effect'],self.s['animations'])
            mode=self.s['mode']
            if mode=='Off':
                enabled=[d['id'] for d in self.s['devices'] if d.get('enabled',True)]
                sent=sum(id in self.off_sent and self.statuses.get(id,'').startswith('Connected') for id in enabled)
                self.output_info.setText(f'ZERO OUTPUT SENT TO {sent} / {len(enabled)} ENABLED LIGHTS')
                self.control_state.setText('Lights off requested')
            else:self.output_info.setText('OUTPUT PAUSED — HOLDING LAST COLOR' if mode=='Paused' else f'Requested brightness  {effective}%  /  maximum {cap_for(self.s)}%')
        if self.s['devices'] and self.banner.text()=='Add your light bars in Devices to get started.':
            active=sum(d.get('enabled',True) and d.get('verified',False) for d in self.s['devices'])
            self.banner.setText(f'{active} lights enabled for sync · Changes save automatically · Bluetooth capped at 10 commands/s')

def main():
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('LumaFlow.Desktop')
    app=QApplication(sys.argv);app.setApplicationName('LumaFlow');app.setApplicationVersion(APP_VERSION);app.setQuitOnLastWindowClosed(False)
    import os
    legacy=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'NBBUFF Sync'
    legacy.mkdir(parents=True,exist_ok=True)
    lock=QLockFile(str(legacy/'instance.lock'));lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None,'Already running','LumaFlow is already running. Open it from the system tray.');return
    logger=configure_logging(data_dir()/'logs');logger.info('Starting %s',build_info()['build_id'])
    window=Window()
    hidden='--startup' in sys.argv and window.s['start_hidden'] and QSystemTrayIcon.isSystemTrayAvailable()
    if not hidden:window.show()
    code=app.exec();lock.unlock();sys.exit(code)

if __name__=='__main__':
    if '--openrgb-worker' in sys.argv:
        from orgb_worker import run
        run()
    elif '--smoke-test' in sys.argv:
        from smoke import run
        run(Path(sys.argv[sys.argv.index('--smoke-test')+1]))
    else:main()
