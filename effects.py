"""Portable whole-light effects, generated on the PC (not firmware presets)."""
import colorsys
import math

EFFECTS=['Rainbow flow','Aurora','Ocean drift','Sunset','Neon dreams','Forest glow',
    'Candy clouds','Northern lights','Ember','Candlelight','Fireplace','Deep space',
    'Lavender mist','Golden hour','Tropical tide','Ice glow','Rose garden','Cyberpunk',
    'Rainbow breathe','Blue breathe','Warm breathe','Heartbeat','Police colors','Color steps']
PALETTES={
    'Aurora':[(0,255,133),(0,157,255),(140,35,255)],
    'Ocean drift':[(0,80,255),(0,225,255),(0,90,130)],
    'Sunset':[(255,45,0),(255,139,12),(201,15,111)],
    'Neon dreams':[(255,0,153),(133,0,255),(0,255,230)],
    'Forest glow':[(10,255,35),(160,240,0),(0,135,80)],
    'Candy clouds':[(255,50,135),(120,60,255),(255,120,180)],
    'Northern lights':[(0,255,30),(0,208,158),(58,30,255)],
    'Deep space':[(40,0,255),(151,0,232),(0,65,255)],
    'Lavender mist':[(157,75,255),(101,60,213),(211,112,255)],
    'Golden hour':[(255,65,4),(255,173,20),(255,100,8)],
    'Tropical tide':[(0,255,151),(0,130,255),(204,255,0)],
    'Ice glow':[(0,155,255),(80,233,255),(20,60,255)],
    'Rose garden':[(255,10,45),(255,55,150),(195,8,30)],
    'Cyberpunk':[(255,0,175),(0,255,242),(108,0,255)],
}

def effect_frame(name,phase):
    """phase in cycles, controlled by the UI's cycle duration."""
    p=phase%1
    if name in PALETTES:
        palette=PALETTES[name];pos=p*len(palette);i=int(pos);f=pos-i;f=f*f*(3-2*f)
        return tuple(round(a+(b-a)*f) for a,b in zip(palette[i],palette[(i+1)%len(palette)])),1.
    if name=='Rainbow flow':return tuple(round(v*255) for v in colorsys.hsv_to_rgb(p,1,1)),1.
    if name in ['Ember','Candlelight','Fireplace']:
        # Continuous deterministic shimmer, with no random frame-to-frame jumps.
        intensity=.65+.17*math.sin(phase*math.tau*3)+.10*math.sin(phase*math.tau*7+.4)
        rgb={'Ember':(255,28,0),'Candlelight':(255,124,20),'Fireplace':(255,62,0)}[name]
        return rgb,max(.15,min(1,intensity))
    if name in ['Rainbow breathe','Blue breathe','Warm breathe']:
        rgb=tuple(round(v*255) for v in colorsys.hsv_to_rgb((phase*.2)%1,1,1)) if name=='Rainbow breathe' else (20,65,255) if name=='Blue breathe' else (255,147,35)
        return rgb,(.5-.5*math.cos(p*math.tau))**1.4
    if name=='Heartbeat':
        level=max(math.exp(-((p-.18)/.08)**2),.7*math.exp(-((p-.43)/.09)**2))
        return (255,15,45),.08+.92*level
    if name=='Police colors':
        # Slow red/blue chase rather than rapid flashing; obeys minimum 2s cycle.
        return ((255,0,0) if p<.5 else (0,40,255)),.25+.75*abs(math.sin(p*math.tau))
    if name=='Color steps':
        colors=[(255,0,0),(255,120,0),(0,255,0),(0,100,255),(160,0,255),(255,0,120)]
        return colors[int(p*6)%6],1.
    raise ValueError('Unknown atmosphere: '+name)
