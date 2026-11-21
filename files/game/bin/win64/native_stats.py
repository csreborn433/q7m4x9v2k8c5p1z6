"""Repurpose the native News tab (formerly Stats) as the party browser's host."""
from pathlib import Path
from native_resources import install_override

def lobby_page(source):
    if source.count('var NewsPanel;') != 1 or 'BlogAPI.RequestRSSFeed();' not in source:
        raise ValueError('Installed News page script changed; no party tab written')
    return """var NewsPanel;
    (function () {
        const host = $.GetContextPanel().FindChildInLayoutFile('NewsPanelLister');
        if (!host) throw Error('Party tab layout changed: missing NewsPanelLister.');
        host.RemoveAndDeleteChildren();
        host.RemoveClass('history');
        Object.assign(host.style, {width:'100%', height:'100%', padding:'0px', overflow:'squish squish'});
        const tab = $.CreatePanel('Panel', host, 'cs2gc-party-tab');
        Object.assign(tab.style, {width:'100%',height:'100%'});
    })();"""

def prepare(directory,config):
    result=install_override(directory,enabled=True,folder='cs2_gc_stats',comment='cs2_gc local stats and achievements',
        owner='cs2-gc-stats-v1',asset='panorama/scripts/mainmenu_news.vts_c',patch=lobby_page)
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
