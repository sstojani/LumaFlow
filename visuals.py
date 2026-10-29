"""Code-native brand mark and previews, driven by requested device output."""
import math
from PySide6.QtCore import Qt,QRectF,QPointF
from PySide6.QtGui import QColor,QPainter,QPixmap,QLinearGradient,QRadialGradient,QPen,QPainterPath,QFont,QIcon
from PySide6.QtWidgets import QWidget


def logo(size=256):
    pix=QPixmap(size,size);pix.fill(Qt.transparent)
    p=QPainter(pix);p.setRenderHint(QPainter.Antialiasing);p.scale(size/256,size/256)
    g=QLinearGradient(15,20,236,240);g.setColorAt(0,QColor('#1d2445'));g.setColorAt(1,QColor('#0d1020'))
    p.setPen(Qt.NoPen);p.setBrush(g);p.drawRoundedRect(0,0,256,256,65,65)
    for offset,color in [(-25,'#75f8d1'),(25,'#b3a0ff')]:
        path=QPainterPath();path.moveTo(45,147+offset);path.cubicTo(93,147+offset,80,77+offset,128,77+offset)
        path.cubicTo(177,77+offset,165,147+offset,211,147+offset)
        p.setPen(QPen(QColor(color),19,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin));p.drawPath(path)
    p.end();return pix


def icon():
    result=QIcon()
    for size in [16,24,32,48,64,128,256]:result.addPixmap(logo(size))
    return result

class LivePreview(QWidget):
    def __init__(self):
        super().__init__();self.rgb=(0,0,0);self.mode='Paused';self.bars=(0.,)*32
        self.phase=0.;self.effect='Rainbow flow';self.animate=True;self.level=0
        self.setMinimumHeight(240)
    def advance(self,rgb,mode,bars=(),level=0,effect='',animate=True,dt=.033):
        self.rgb=rgb;self.mode=mode;self.bars=bars or (0.,)*32;self.level=level;self.effect=effect;self.animate=animate
        if animate:self.phase+=dt
        self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);w=self.width();h=self.height();c=QColor(*self.rgb)
        g=QLinearGradient(0,0,w,h);g.setColorAt(0,QColor('#1b2540'));g.setColorAt(1,QColor('#111625'))
        p.setBrush(g);p.setPen(Qt.NoPen);p.drawRoundedRect(self.rect(),18,18)
        if self.mode=='Screen':self.screen(p,w,h,c)
        elif self.mode=='Music':self.music(p,w,h,c)
        elif self.mode=='Atmosphere':self.flow(p,w,h,c)
        elif self.mode=='Solid':self.solid(p,w,h,c)
        else:
            p.drawPixmap(int(w/2-36),60,72,72,logo(144));self.text(p,w,155,'Take a breath. Your lights are holding their last color.')
        captions={'Screen':'SCREEN MIRROR  /  SHARED COLOR','Music':'LIVE AUDIO SPECTRUM',
                  'Solid':'SOLID COLOR  /  '+QColor(*self.rgb).name().upper(),'Atmosphere':self.effect.upper(),'Paused':'PAUSED'}
        self.text(p,w,h-27,captions[self.mode],small=True)
    def text(self,p,w,y,text,small=False):
        p.setPen(QColor('#9cabcb'));p.setFont(QFont('Segoe UI',9 if small else 11))
        p.drawText(QRectF(0,y,w,22),Qt.AlignCenter,text)
    def glow(self,p,x,y,r,c):
        if max(self.rgb)==0:return
        g=QRadialGradient(QPointF(x,y),r);v=QColor(c);v.setAlpha(100);g.setColorAt(0,v);v.setAlpha(0);g.setColorAt(1,v)
        p.setPen(Qt.NoPen);p.setBrush(g);p.drawEllipse(QPointF(x,y),r,r)
    def screen(self,p,w,h,c):
        mw=min(330,w*.52);x=(w-mw)/2;y=32
        self.glow(p,w/2,95,mw*.8,c)
        p.setPen(QColor('#52617a'));p.setBrush(QColor('#0b111c'));p.drawRoundedRect(QRectF(x,y,mw,125),10,10)
        g=QLinearGradient(x,y,x+mw,y+125);g.setColorAt(0,c.darker(160));g.setColorAt(1,c.darker(350))
        p.setPen(Qt.NoPen);p.setBrush(g);p.drawRoundedRect(QRectF(x+7,y+7,mw-14,111),6,6)
        p.setBrush(QColor('#45536c'));p.drawRoundedRect(QRectF(w/2-4,157,8,16),3,3);p.drawRoundedRect(QRectF(w/2-40,173,80,5),2,2)
        for bx in (x-45,x+mw+29):
            p.setBrush(c.darker(250));p.drawRoundedRect(QRectF(bx-6,45,28,119),12,12)
            p.setBrush(c);p.drawRoundedRect(QRectF(bx,52,16,105),8,8)
    def solid(self,p,w,h,c):
        t=self.phase if self.animate else 0
        r=57+2*math.sin(t*.8)
        self.glow(p,w/2,105,150,c)
        for radius in [82,100]:
            cc=QColor(c);cc.setAlpha(50);p.setPen(QPen(cc,1));p.setBrush(Qt.NoBrush);p.drawEllipse(QPointF(w/2,105),radius,radius)
        g=QRadialGradient(QPointF(w/2-15,80),r*1.8);g.setColorAt(0,c.lighter(140));g.setColorAt(1,c.darker(180))
        p.setPen(Qt.NoPen);p.setBrush(g);p.drawEllipse(QPointF(w/2,105),r,r)
    def music(self,p,w,h,c):
        # Height data comes only from captured FFT bands. No fabricated idle rhythm.
        left=35;area=w-70;count=len(self.bars);gap=5;bw=max(3,area/count-gap)
        self.glow(p,w/2,130,140,c)
        for i,amp in enumerate(self.bars):
            bh=max(3,min(1,amp)*145);x=left+i*area/count;y=178-bh
            g=QLinearGradient(0,y,0,180);g.setColorAt(0,c.lighter(145));g.setColorAt(1,c.darker(170))
            p.setPen(Qt.NoPen);p.setBrush(g if amp>.001 else QColor('#2b344a'));p.drawRoundedRect(QRectF(x,y,bw,bh),min(4,bw/2),min(4,bw/2))
    def flow(self,p,w,h,c):
        t=self.phase if self.animate else 0
        self.glow(p,w/2,110,180,c)
        for j in range(7):
            path=QPainterPath()
            for i in range(121):
                x=20+(w-40)*i/120
                y=105+math.sin(i/120*math.tau*1.5-t*.7+j*.32)*(24+j*5)
                if i==0:path.moveTo(x,y)
                else:path.lineTo(x,y)
            cc=QColor(c);cc.setAlpha(65+j*25);p.setPen(QPen(cc,2+j*.6,Qt.SolidLine,Qt.RoundCap));p.setBrush(Qt.NoBrush);p.drawPath(path)
