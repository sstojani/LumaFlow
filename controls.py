"""Native, keyboard-accessible controls with code-drawn icons."""
import math
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import QPushButton,QSlider,QComboBox,QScrollArea


class PageScrollArea(QScrollArea):
    """Preserve smooth touchpad scrolling when child controls ignore wheel input."""
    def wheelEvent(self,event):
        delta=event.pixelDelta()
        if delta.isNull():super().wheelEvent(event);return
        horizontal=self.horizontalScrollBar();vertical=self.verticalScrollBar()
        before=(horizontal.value(),vertical.value())
        horizontal.setValue(horizontal.value()-delta.x());vertical.setValue(vertical.value()-delta.y())
        event.setAccepted(before!=(horizontal.value(),vertical.value()))


class ScrollSafeSlider(QSlider):
    """Wheel gestures belong to the page; values require direct manipulation."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.setFocusPolicy(Qt.StrongFocus)
    def wheelEvent(self,event):event.ignore()


class ScrollSafeComboBox(QComboBox):
    """A closed dropdown must not change selection while the page scrolls."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.setFocusPolicy(Qt.StrongFocus)
    def wheelEvent(self,event):
        if self.view().isVisible():super().wheelEvent(event)
        else:event.ignore()


def draw_symbol(p,kind,rect,color):
    p.save();p.setRenderHint(QPainter.Antialiasing)
    p.translate(rect.center());size=min(rect.width(),rect.height());p.scale(size/24,size/24)
    p.setPen(QPen(QColor(color),2,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.setBrush(Qt.NoBrush)
    if kind=='power':
        p.drawArc(QRectF(-8,-8,16,16),135*16,270*16);p.drawLine(QPointF(0,-10),QPointF(0,-1))
    elif kind=='pause':
        p.drawLine(QPointF(-4,-7),QPointF(-4,7));p.drawLine(QPointF(4,-7),QPointF(4,7))
    elif kind=='play':
        path=QPainterPath();path.moveTo(-5,-8);path.lineTo(8,0);path.lineTo(-5,8);path.closeSubpath()
        p.setBrush(QColor(color));p.drawPath(path)
    elif kind=='sun':
        p.drawEllipse(QPointF(0,0),4,4)
        for i in range(8):
            a=i*math.pi/4
            p.drawLine(QPointF(math.cos(a)*7,math.sin(a)*7),QPointF(math.cos(a)*10,math.sin(a)*10))
    p.restore()


class IconButton(QPushButton):
    def __init__(self,symbol,name,callback):
        super().__init__();self.symbol=symbol;self.setObjectName('iconButton')
        self.setFixedSize(46,46);self.setCursor(Qt.PointingHandCursor);self.setCheckable(True)
        self.setAccessibleName(name);self.setToolTip(name);self.clicked.connect(callback)
    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self);color='#0d2b25' if self.isChecked() else '#dce8f8'
        if self.symbol=='power' and self.isChecked():color='#ffd4dc'
        if not self.isEnabled():color='#637088'
        draw_symbol(p,self.symbol,QRectF(12,12,22,22),color)


class BrightnessSlider(ScrollSafeSlider):
    """Vertical fill slider; native QSlider retains accessibility and keyboard support."""
    def __init__(self,value,callback):
        super().__init__(Qt.Vertical);self.setRange(0,100);self.setValue(value)
        self.setFixedSize(88,166);self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet('QSlider { min-height: 166px; max-height: 166px; min-width: 88px; max-width: 88px; background: transparent; }')
        self.setAccessibleName('Maximum brightness');self.setCursor(Qt.PointingHandCursor)
        self.setSingleStep(1);self.setPageStep(10);self.valueChanged.connect(callback)
        self.valueChanged.connect(lambda value:self.setToolTip(f'Brightness: {value}% — click, drag, or use arrow keys'))
        self.setToolTip(f'Brightness: {value}% — click, drag, or use arrow keys')
    def track_rect(self):return QRectF(4,4,self.width()-8,self.height()-8)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);rect=self.track_rect()
        p.setPen(Qt.NoPen);p.setBrush(QColor('#27344a'));p.drawRoundedRect(rect,24,24)
        clip=QPainterPath();clip.addRoundedRect(rect,24,24);p.save();p.setClipPath(clip)
        fill=rect.height()*self.value()/100
        p.fillRect(QRectF(rect.left(),rect.bottom()-fill,rect.width(),fill),QColor('#9af5d4'))
        p.restore();draw_symbol(p,'sun',QRectF(self.width()/2-13,self.height()-45,26,26),
            '#173c34' if self.value()>=27 else '#dce8f8')
        p.setPen(QPen(QColor('#89a8ff' if self.hasFocus() else '#3b4b65'),2 if self.hasFocus() else 1))
        p.setBrush(Qt.NoBrush);p.drawRoundedRect(rect,24,24)
    def set_from_position(self,position):
        rect=self.track_rect();fraction=(rect.bottom()-position.y())/rect.height()
        self.setValue(round(max(0,min(1,fraction))*100))
    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.setFocus();self.setSliderDown(True);self.set_from_position(event.position());event.accept()
        else:super().mousePressEvent(event)
    def mouseMoveEvent(self,event):
        if self.isSliderDown():self.set_from_position(event.position());event.accept()
        else:super().mouseMoveEvent(event)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.set_from_position(event.position());self.setSliderDown(False);event.accept()
        else:super().mouseReleaseEvent(event)
