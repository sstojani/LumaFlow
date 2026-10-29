"""Isolated source/frozen GUI smoke check. Never connects to physical devices."""
import json
from pathlib import Path
import tempfile
import traceback


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    result={'ok':False}
    try:
        from PySide6.QtWidgets import QApplication,QScrollArea
        from PySide6.QtGui import QFontDatabase
        import os
        from PySide6.QtTest import QTest
        from app import Window
        from engine import Engine
        from model import Store
        from version import build_info
        app=QApplication.instance() or QApplication([])
        # Qt's offscreen Windows plugin does not discover installed fonts itself.
        for name in ('segoeui.ttf','segoeuib.ttf','seguisb.ttf'):
            font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
            if font.exists():QFontDatabase.addApplicationFont(str(font))
        with tempfile.TemporaryDirectory(dir=output) as directory:
            w=Window(Store(Path(directory)/'settings.json'),Engine(False));w.show();w.resize(1130,870)
            app.processEvents()
            for mode in ['Solid','Screen','Music','Atmosphere','Paused','Off']:
                w.set_mode(mode);app.processEvents();w.poll();app.processEvents()
                assert w.grab().save(str(output/(mode.lower()+'.png')))
                assert all(panel.isVisible()==(key==mode) for key,panel in w.mode_panels.items())
            w.set_mode('Solid');w.brightness_slider.setValue(31);QTest.qWait(350)
            assert Store(w.store.path).data['solid_brightness']==31
            w.pause_button.click();assert w.s['mode']=='Paused'
            w.pause_button.click();assert w.s['mode']=='Solid'
            w.power_button.click();assert w.s['mode']=='Off'
            w.power_button.click();assert w.s['mode']=='Solid'
            w.resize(900,620);app.processEvents();w.grab().save(str(output/'small-window.png'))
            assert w.brightness_slider.height()==166
            area=w.stack.currentWidget().findChild(QScrollArea)
            assert area.horizontalScrollBar().maximum()==0,'Studio must fit the small window width'
            w.timer.stop();w.save_timer.stop();w.tray.hide();w.hide();w.deleteLater();app.processEvents()
        result={'ok':True,'build':build_info(),'checks':['six modes rendered','mode controls','debounced save','pause/resume','off/on','small window']}
    except Exception:
        result['error']=traceback.format_exc()
    (output/'smoke-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    if not result['ok']:raise SystemExit(1)


if __name__=='__main__':
    import sys
    run(sys.argv[1] if len(sys.argv)>1 else 'review-output')
