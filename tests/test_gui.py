import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from app import Window
from engine import Engine
from model import Store

def test_live_controls_and_pages(tmp_path):
    app=QApplication.instance() or QApplication([])
    engine=Engine(autostart=False);store=Store(tmp_path/'settings.json')
    w=Window(store,engine);w.show();app.processEvents()
    w.brightness_slider.setValue(23)
    assert Store(store.path).data['solid_brightness']==23
    commands=[]
    while not engine.commands.empty():commands.append(engine.commands.get_nowait())
    assert commands[-1][1]['solid_brightness']==23
    w.pick_hex('#ff0000');assert w.s['color']==[255,0,0];assert w.s['mode']=='Solid'
    for n in range(4):w.navigate(n);app.processEvents();assert w.stack.currentIndex()==n
    w.navigate(0);app.processEvents()
    for mode in ['Solid','Screen','Music','Atmosphere','Paused']:
        w.set_mode(mode);app.processEvents()
        assert all(panel.isVisible()==(name==mode) for name,panel in w.mode_panels.items())
    assert w.minimumWidth()>=900
    w.timer.stop();w.tray.hide();w.hide();w.deleteLater();app.processEvents()
