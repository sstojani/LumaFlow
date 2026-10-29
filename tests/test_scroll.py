"""Exercise wheel dispatch through the real Qt window, not just event handlers."""
import copy
import os
from pathlib import Path
import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QScrollArea
from app import Window,AddDialog
from controls import ScrollSafeSlider,ScrollSafeComboBox
from engine import Engine
from model import Store


@pytest.fixture
def window(tmp_path):
    app=QApplication.instance() or QApplication([])
    font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'segoeui.ttf'
    if font.exists():QFontDatabase.addApplicationFont(str(font))
    w=Window(Store(tmp_path/'settings.json'),Engine(False));w.resize(1130,760)
    w.show();app.processEvents()
    yield w
    w.save_timer.stop();w.timer.stop();w.tray.hide();w.hide();w.deleteLater();app.processEvents()


def wheel_over(widget,delta=-120,pixels=False):
    window=widget.window();point=widget.mapTo(window,widget.rect().center())
    if pixels:
        QTest.wheelEvent(window.windowHandle(),point,QPoint(),pixelDelta=QPoint(0,-40))
    else:QTest.wheelEvent(window.windowHandle(),point,QPoint(0,delta))
    QApplication.processEvents()


@pytest.mark.parametrize('control',['vertical','horizontal','dropdown'])
@pytest.mark.parametrize('focused',[False,True])
@pytest.mark.parametrize('pixels',[False,True])
def test_page_scroll_over_controls_never_changes_settings(window,control,focused,pixels):
    w=window;w.set_mode('Screen');QApplication.processEvents()
    area=w.stack.currentWidget().findChild(QScrollArea)
    if control=='vertical':widget=w.brightness_sliders['Screen'];widget.setValue(50)
    elif control=='horizontal':widget=w.mode_panels['Screen'].findChildren(ScrollSafeSlider)[0];widget.setValue(125)
    else:widget=w.region;widget.setCurrentIndex(1)
    area.ensureWidgetVisible(widget,0,40);QApplication.processEvents()
    if focused:widget.setFocus(Qt.MouseFocusReason)
    else:w.pause_button.setFocus()
    before=copy.deepcopy(w.s);position=area.verticalScrollBar().value()
    wheel_over(widget,pixels=pixels)
    assert w.s==before,'Scrolling the page must not mutate any setting'
    assert area.verticalScrollBar().value()>position,'Wheel input must still scroll the page'


def test_dropdown_popup_scrolls_then_commits_only_explicit_selection(window):
    # Enough options to require popup scrolling, regardless of screen/font size.
    combo=ScrollSafeComboBox(window);combo.addItems([f'Choice {i}' for i in range(100)])
    combo.setMaxVisibleItems(6);combo.setGeometry(250,100,200,40);combo.show()
    QTest.mouseClick(combo,Qt.LeftButton);QApplication.processEvents()
    view=combo.view();assert view.isVisible()
    before=combo.currentIndex();bar=view.verticalScrollBar();assert bar.maximum()>0
    wheel_over(view.viewport())
    assert bar.value()>0 and combo.currentIndex()==before
    target=view.indexAt(view.viewport().rect().center());assert target.isValid() and target.row()!=before
    QTest.mouseMove(view.viewport(),view.visualRect(target).center());QTest.qWait(150)
    QTest.mouseClick(view.viewport(),Qt.LeftButton,pos=view.visualRect(target).center())
    QApplication.processEvents()
    assert combo.currentIndex()==target.row()
    # A closed dropdown still ignores the wheel after being explicitly used.
    selected=combo.currentIndex();wheel_over(combo)
    assert combo.currentIndex()==selected


def test_dropdown_and_slider_keep_explicit_keyboard_input(window):
    w=window;w.set_mode('Screen');QApplication.processEvents()
    slider=w.mode_panels['Screen'].findChildren(ScrollSafeSlider)[0];slider.setValue(100)
    slider.setFocus();QTest.keyClick(slider,Qt.Key_Right);assert slider.value()==101
    w.region.setFocus();w.region.setCurrentIndex(0)
    QTest.keyClick(w.region,Qt.Key_Down);assert w.region.currentIndex()==1


def test_add_device_dropdown_does_not_change_when_scrolled(window):
    dialog=AddDialog(window);dialog.show();QApplication.processEvents()
    try:
        for combo in (dialog.kind,dialog.profile):
            combo.setCurrentIndex(1);combo.setFocus();wheel_over(combo)
            assert combo.currentIndex()==1
    finally:dialog.hide();dialog.deleteLater();QApplication.processEvents()
