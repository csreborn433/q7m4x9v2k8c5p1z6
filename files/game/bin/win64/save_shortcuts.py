"""Generate root-level save shortcuts; paths follow the portable game folder."""
def files():
    result={}
    for action,title in (('backup','Back Up Progress'),('restore','Restore Progress')):
        text='@echo off\r\ncd /d "%~dp0.."\r\n"game\\bin\\win64\\cs2_gc_python\\python.exe" -B "game\\bin\\win64\\progress_saves.py" '+action+' --proxy-dir "game\\bin\\win64"\r\necho.\r\npause\r\n'
        result['CS2 GC Saves/'+title+'.cmd']=text.encode()
    return result

def install(root):
    from pathlib import Path
    root=Path(root)
    for name,data in files().items():
        target=root/name
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            with target.open('xb') as output:output.write(data)
