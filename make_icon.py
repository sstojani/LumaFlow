"""Build the Windows app icon from the same vector paths used in the UI."""
from pathlib import Path
from PySide6.QtWidgets import QApplication
from visuals import logo

if __name__=='__main__':
    app=QApplication([]);dest=Path(__file__).parent/'assets';dest.mkdir(exist_ok=True)
    image=logo(256)
    if not image.save(str(dest/'lumaflow.ico'),'ICO'):raise RuntimeError('Qt ICO writer unavailable')
    if not image.save(str(dest/'lumaflow.png'),'PNG'):raise RuntimeError('Qt PNG writer unavailable')
    print('LumaFlow icon created')
