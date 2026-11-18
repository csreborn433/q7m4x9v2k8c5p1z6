"""Prepare the native career page from safe, locally recorded profile counters."""
from pathlib import Path
from native_resources import install_override
from local_stats import snapshot
from career_page import patch

def prepare(directory,config):
    result=install_override(directory,enabled=True,folder='cs2_gc_stats',comment='cs2_gc local stats and achievements',
        owner='cs2-gc-stats-v1',asset='panorama/scripts/mainmenu_news.vts_c',patch=lambda source:patch(source,snapshot(directory)))
    avatar=Path(__file__).resolve().parent/'credits'/'ginekolog_avatar.jpg'
    if not avatar.is_file():
        raise FileNotFoundError('Bundled GINEKOLOG avatar is missing: '+str(avatar))
    folder=Path(directory).resolve().parents[1]/'cs2_gc_stats'
    target=folder/'panorama/images/cs2_gc/ginekolog_avatar.jpg'
    if target.exists() and target.read_bytes()!=avatar.read_bytes():
        raise ValueError('The credits avatar path is occupied by different content; leaving it unchanged.')
    from vpk_pack import pack
    pack(folder,() if target.exists() else [('panorama/images/cs2_gc/ginekolog_avatar.jpg',avatar.read_bytes())])
    return result
