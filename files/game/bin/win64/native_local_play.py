"""Restrict local Play to Wingman on bundled Cobblestone."""
import json
import hashlib
import re
import shutil
import struct
import tempfile
from pathlib import Path
from native_resources import install_override, vpk_file
from native_tradeups import atomic_write, mount_gameinfo, parse as parse_keyvalues, read_text

WORKSHOP_MAP = 'cobblewingman'
WORKSHOP_MAP_GROUP = 'mg_cobblewingman'
MAP_ARCHIVE = 'maps/cobblewingman.vpk'
MAX_MAP_ARCHIVE = 512 * 1024 * 1024
MAP_ASSET = Path(__file__).resolve().parent / 'map_assets' / 'cobblewingman.vpk'
MAP_RESOURCES = Path(__file__).resolve().parent / 'map_assets' / 'cobblestone_resources'
MAP_RESOURCES_FOLDER = 'cs2_gc_cobblestone_assets'
MAP_RESOURCES_COMMENT = 'cs2_gc Cobblestone compiled resources'
MAP_RESOURCES_OWNER = 'cs2-gc-cobblestone-resources-v1'
MAP_RESOURCE_FILES = ('pak01_dir.vpk', 'pak01_000.vpk')
LOCAL_PLAY_FOLDER = 'cs2_gc_local_play'
LOCAL_PLAY_COMMENT = 'cs2_gc local native Wingman maps'
LOCAL_PLAY_OWNER = 'cs2-gc-local-play-v1'
# Written by the earlier reference build for this same owned folder.
LEGACY_LOCAL_PLAY_COMMENTS = ('cs2_gc local premier and night maps',)
HASH_CHUNK = 1024 * 1024


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        while True:
            block = source.read(HASH_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def validate_map_archive(path):
    path = Path(path)
    with path.open('rb') as source:
        header = source.read(28)
        if len(header) != 28:
            raise ValueError('Cobblestone map VPK header is truncated')
        magic, version, tree, data, archive_md5, other_md5, signature = struct.unpack('<IIIIIII', header)
        if (magic != 0x55aa1234 or version != 2 or not 0 < tree <= 64 * 1024 * 1024
                or 28 + tree + data + archive_md5 + other_md5 + signature != path.stat().st_size
                or path.stat().st_size > MAX_MAP_ARCHIVE):
            raise ValueError('Cobblestone map file is not a complete VPK v2 package')


def migrate_local_play_mount(game):
    info = game / 'csgo/gameinfo.gi'
    manifest = game / LOCAL_PLAY_FOLDER / 'cs2_gc_ui_manifest.json'
    if not info.is_file() or not manifest.is_file():
        return False
    if json.loads(read_text(manifest)).get('owner') != LOCAL_PLAY_OWNER:
        return False
    current = read_text(info)
    legacy = '|'.join(re.escape(comment) for comment in LEGACY_LOCAL_PLAY_COMMENTS)
    line = re.compile(r'(\r?\n[ \t]*Game[ \t]+' + re.escape(LOCAL_PLAY_FOLDER) +
                      r'[ \t]*// )(?:' + legacy + r')(?=\r?\n)')
    updated, count = line.subn(lambda match: match.group(1) + LOCAL_PLAY_COMMENT, current)
    if count != 1:
        return False
    mount_gameinfo(updated, True, LOCAL_PLAY_FOLDER, LOCAL_PLAY_COMMENT)
    backup = info.with_name(info.name + '.' + LOCAL_PLAY_FOLDER + '_backup')
    if not backup.exists():
        with backup.open('x', encoding='utf-8', newline='') as output:
            output.write(current)
    atomic_write(info, updated)
    return True


def install_cobblestone_resources(proxy_directory, source=MAP_RESOURCES):
    source = Path(source)
    assets = {name: source / name for name in MAP_RESOURCE_FILES}
    if any(not path.is_file() for path in assets.values()):
        raise ValueError('The bundled Cobblestone texture/resource VPK is incomplete.')
    validate_map_archive(assets['pak01_dir.vpk'])
    if not 0 < assets['pak01_000.vpk'].stat().st_size <= 1 << 30:
        raise ValueError('The bundled Cobblestone resource archive has an invalid size.')

    game = Path(proxy_directory).resolve().parents[1]
    target = game / MAP_RESOURCES_FOLDER
    manifest_path = target / 'cs2_gc_cobblestone_resources.json'
    if manifest_path.is_file():
        manifest = json.loads(read_text(manifest_path))
        if manifest.get('owner') != MAP_RESOURCES_OWNER:
            raise ValueError('Cobblestone resource folder is not owned by this feature.')
        previous = manifest.get('files')
        if not isinstance(previous, dict):
            raise ValueError('Cobblestone resource manifest is invalid.')
    else:
        if target.exists() and any(target.iterdir()):
            raise ValueError('Cobblestone resource folder contains unowned files.')
        previous = {}

    target.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, path in assets.items():
        digest = _sha256_file(path)
        destination = target / name
        current = None
        if destination.exists():
            current = _sha256_file(destination)
            if current not in (previous.get(name), digest):
                raise ValueError('Refusing to overwrite an externally changed Cobblestone resource: ' + name)
        if not destination.is_file() or current != digest:
            temporary = destination.with_name(destination.name + '.tmp')
            shutil.copyfile(path, temporary)
            temporary.replace(destination)
        hashes[name] = digest

    atomic_write(manifest_path, json.dumps({'owner': MAP_RESOURCES_OWNER, 'files': hashes}, indent=2) + '\n')
    info = game / 'csgo/gameinfo.gi'
    if not info.is_file():
        raise ValueError('Installed gameinfo.gi is missing; cannot mount Cobblestone resources.')
    current_info = read_text(info)
    mounted = mount_gameinfo(current_info, True, MAP_RESOURCES_FOLDER, MAP_RESOURCES_COMMENT)
    if mounted != current_info:
        backup = info.with_name(info.name + '.' + MAP_RESOURCES_FOLDER + '_backup')
        if not backup.exists():
            with backup.open('x', encoding='utf-8', newline='') as output:
                output.write(current_info)
        atomic_write(info, mounted)
    return 'installed owned Cobblestone compiled resources'


def patch_gamemodes(source, include_cobblestone=True):
    if not include_cobblestone:
        raise ValueError('Cobblestone is required for the Play menu.')
    game_modes = parse_keyvalues(source).one('GameModes.txt')
    mapgroups = game_modes.one('mapgroups')
    mapgroups.one('mg_de_overpass')
    if include_cobblestone and any(group.key == WORKSHOP_MAP_GROUP for group in mapgroups.children or []):
        raise ValueError('Cobblestone map group already exists in installed gamemodes.txt')
    wingman = (game_modes.one('gameTypes').one('classic')
               .one('gameModes').one('scrimcomp2v2'))
    practice_groups = wingman.one('mapgroupsSP')
    multiplayer_groups = wingman.one('mapgroupsMP')
    wingman_template = game_modes.one('templates#include').one('2v2')
    mapgroup_insertion = mapgroups.end - 1
    if source[mapgroup_insertion] != '}':
        raise ValueError('Installed gamemodes.txt mapgroups block changed')
    newline = '\r\n' if '\r\n' in source else '\n'

    def wingman_map_list_body(node):
        if source[node.end - 1] != '}':
            raise ValueError('Installed gamemodes.txt Wingman map list changed')
        close_line_start = source.rfind('\n', 0, node.end - 1) + 1
        close_indent = source[close_line_start:node.end - 1]
        entry_indent = close_indent + '\t'
        entries = [entry_indent + '"mg_cobblewingman"\t"0"']
        entries.append(close_indent)
        return newline + newline.join(entries)

    group = newline.join((
        '\t"mg_cobblewingman"',
        '\t{',
        '\t\t"imagename"\t\t\t\t"map-cbble-overall"',
        '\t\t"nameID"\t\t\t\t"#SFUI_Map_de_cbble"',
        '\t\t"tooltipID"\t\t\t"#SFUI_Map_Tooltip_Desc_Reserves"',
        '\t\t"name"\t\t\t\t\t"mg_cobblewingman"',
        '\t\t"icontag"\t\t\t\t"bomb"',
        '\t\t"grouptype"\t\t\t\t"reserves"',
        '\t\t"icon_image_path"\t\t"map_icons/map_icon_de_cbble"',
        '\t\t"maps"',
        '\t\t{',
        '\t\t\t"cobblewingman"\t\t""',
        '\t\t}',
        '\t}',
        '\t',
    )) if include_cobblestone else ''
    edits = (
        (practice_groups.opening, practice_groups.end - 1, wingman_map_list_body(practice_groups)),
        (multiplayer_groups.opening, multiplayer_groups.end - 1,
         wingman_map_list_body(multiplayer_groups)),
        (wingman_template.opening, wingman_template.end - 1,
         wingman_map_list_body(wingman_template)),
    )
    if include_cobblestone:
        edits += ((mapgroup_insertion, mapgroup_insertion, group),)
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source

SCRIPT=r'''
    let m_localVetoMap='',m_localVeto=null,m_localStarting=false;
    const m_localInstalled=__MAPS__;
    const m_localOnline=true;
    // Every map started here is an online listen server (network_server = 0 turns this off): LAN, Hamachi,
    // ZeroTier and internet players use connect <ip>:27015, Steam party members follow through the native lobby.
    // engine2's sv_lan 1 refuses every non-class-C address, so the server always runs with sv_lan 0.
    function _LocalApplyHostOnline() {
        if(!m_localOnline)return;
        GameInterfaceAPI.ConsoleCommand('exec cs2_gc_network');
        GameInterfaceAPI.ConsoleCommand('sv_lan 0');
        GameInterfaceAPI.ConsoleCommand('sv_hibernate_when_empty 0');
    }
    // cs2_gc_network.cfg lists this PC's addresses (native_network.py); UPnP adds the router's external IP.
    function _LocalHostAddresses() {
        const order=['Hamachi','VPN','Internet','Public','LAN'],out=[];
        const add=(label,ip)=>{
            if(order.includes(label)&&/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)&&!out.some(a=>a.ip===ip))out.push({label,ip});
        };
        let listed='',external='';
        try { listed=GameInterfaceAPI.GetSettingString('cs2gc_host_addresses')||''; } catch(e) {}
        try { external=GameInterfaceAPI.GetSettingString('cs2gc_host_external')||''; } catch(e) {}
        listed.split(',').forEach(entry=>{const pair=entry.split('=');if(pair.length===2)add(pair[0],pair[1]);});
        add('Internet',external);
        return out.sort((a,b)=>order.indexOf(a.label)-order.indexOf(b.label));
    }
    function _LocalConnectCommand() {
        const first=_LocalHostAddresses()[0];
        return 'connect '+(first?first.ip:'<your LAN/Hamachi IP>')+':27015';
    }
    function _LocalAnnouncePartyStart() {
        if (!m_localOnline || !LobbyAPI.BIsHost()) return;
        const addresses = _LocalHostAddresses();
        const address = addresses.find(a => a.label === 'Internet' || a.label === 'Public') || addresses[0];
        if (address) $.Msg('CS2GC_PARTY start ' + address.ip + ':27015');
    }
    function _LocalApplyServerPassword(pw) {
        pw=(pw||'').trim();
        GameInterfaceAPI.SetSettingString('ui_host_password',pw);
        GameInterfaceAPI.ConsoleCommand('sv_password "'+pw.replace(/[";\\]/g,'')+'"');
    }
    function _LocalShowConnectInfo() {
        const pw=GameInterfaceAPI.GetSettingString('ui_host_password')||'';
        const lines=_LocalHostAddresses().map(a=>'connect '+a.ip+':27015   ('+a.label+')');
        UiToolkitAPI.ShowGenericPopupOk('Online Match',
            (m_localOnline?'Every map you start here is an online server your friends can join:\n\n':
                'Online hosting is off (network_server = 0 in cs2_gc_gameplay.cfg).\n\n')+
            'Steam: invite friends to your party before pressing GO; Cobblestone uses the native lobby start.\n\n'+
            'Hamachi, LAN or internet: friends open the console (~) and type\n'+
            (lines.length?lines.join('\n'):'connect <your LAN/Hamachi IP>:27015')+'\n\n'+
            (pw?'Server password: '+pw+'\n\n':'')+
            'Internet play without Hamachi needs UDP and TCP port 27015 open; the launcher tries UPnP automatically. '+
            'This build shares equipped skins, Armory items and Premier ratings over Steam and direct connections. '+
            'All players need the same build and matching custom-finish assets.',
            '',()=>{});
    }
    function _LocalUpdateHostStatus(row) {
        const status=row&&row.IsValid()&&row.FindChildTraverse('id-play-menu-hostonline-status');
        if(!status)return;
        const first=_LocalHostAddresses()[0];
        status.text=!m_localOnline?'ONLINE HOSTING OFF':
            'ONLINE  ·  Steam party or connect '+(first?first.ip+':27015 ('+first.label+')':'<your IP>:27015');
    }
    function _LocalEnsureHostOnlineToggle() {
        const container=$('#id-play-menu-practicesettings-container');
        if(!container)return;
        let row=container.FindChildInLayoutFile('id-play-menu-practicesettings-hostonline');
        if(!row) {
            row=$.CreatePanel('Panel',container,'id-play-menu-practicesettings-hostonline');
            row.style.flowChildren='left';row.style.width='100%';row.style.padding='6px 20px';
            const status=$.CreatePanel('Label',row,'id-play-menu-hostonline-status');
            status.style.verticalAlign='center';status.style.color=m_localOnline?'#9fe3a2':'#aab8c1';
            const pw=$.CreatePanel('TextEntry',row,'id-play-menu-hostonline-password');
            pw.style.width='150px';pw.style.height='30px';pw.style.marginLeft='14px';pw.style.verticalAlign='center';
            pw.text=GameInterfaceAPI.GetSettingString('ui_host_password')||'';
            pw.SetPanelEvent('ontextentrychange',()=>_LocalApplyServerPassword(pw.text));
            const copy=$.CreatePanel('Button',row,'id-play-menu-hostonline-copy',{class:'content-navbar__tabs__btn'});
            copy.style.marginLeft='10px';copy.style.padding='4px 12px';copy.style.verticalAlign='center';
            $.CreatePanel('Label',copy,'',{text:'COPY CONNECT'});
            copy.SetPanelEvent('onactivate',()=>{
                SteamOverlayAPI.CopyTextToClipboard(_LocalConnectCommand());
                UiToolkitAPI.ShowTextTooltip('id-play-menu-hostonline-copy','Copied: '+_LocalConnectCommand());
            });
            const fwd=$.CreatePanel('Button',row,'id-play-menu-hostonline-forward',{class:'content-navbar__tabs__btn'});
            fwd.style.marginLeft='6px';fwd.style.padding='4px 12px';fwd.style.verticalAlign='center';
            $.CreatePanel('Label',fwd,'',{text:'FORWARD PORT'});
            fwd.SetPanelEvent('onactivate',()=>{
                UiToolkitAPI.ShowGenericPopupOk('Forward Port (UPnP)',
                    'The launcher already tries to forward port 27015 automatically (UPnP) each time it starts the game. If friends still cannot connect over the internet, enable UPnP on your router or forward UDP/TCP 27015 to this PC manually — or use Hamachi/ZeroTier or a Steam party, which need no forwarding.',
                    '',()=>{});
            });
            const info=$.CreatePanel('Button',row,'id-play-menu-hostonline-info',{class:'content-navbar__tabs__btn'});
            info.style.marginLeft='6px';info.style.padding='4px 12px';info.style.verticalAlign='center';
            $.CreatePanel('Label',info,'',{text:'?'});
            info.SetPanelEvent('onactivate',_LocalShowConnectInfo);
        }
        _LocalUpdateHostStatus(row);
        if(m_localOnline) {
            // UPnP finishes after the game starts; re-read its external IP for the connect line.
            GameInterfaceAPI.ConsoleCommand('exec cs2_gc_network_external');
            $.Schedule(.5,()=>_LocalUpdateHostStatus(row));
        }
    }
    function _LocalPremierPool() {
        const cfg=GameTypesAPI.GetConfig(),active=cfg.mapgroups&&cfg.mapgroups.mg_active;
        const entries=active&&active.maps||{},names=Array.isArray(entries)?entries:Object.keys(entries);
        return names.filter(m=>m_localInstalled.includes(m)&&GetMGDetails('mg_'+m)).slice(0,7);
    }
    function _LocalMapName(map) {
        const group=GetMGDetails('mg_'+map);return group?$.Localize(group.nameID):map;
    }
    function _LocalStartSelected(map,team) {
        if(m_localStarting||PartyListAPI.GetCount()>1||!LobbyAPI.BIsHost())return;
        if(!m_localInstalled.includes(map)) {
            UiToolkitAPI.ShowGenericPopupOk('Map unavailable', 'This local custom map is not installed on this PC.', '', ()=>{});
            return;
        }
        m_localStarting=true;m_localVetoMap=map;
        _LocalApplyHostOnline();
        const settings={update:{Options:{action:'custommatch',server:'listen',practicesettings_grenades:0,practicesettings_infammo:0,practicesettings_infwarmup:0,practicesettings_annotations:0},
            Game:{mode:'competitive',mode_ui:'premier',type:GetGameType('competitive'),mapgroupname:'mg_'+map,map:map,gamemodeflags:16,prime:0}},delete:{Options:{challengekey:1}}};
        LobbyAPI.StopMatchmaking();let attempts=0;
        function ready() {
            const s=LobbyAPI.GetSessionSettings();
            if(s&&s.options&&s.game&&s.options.server==='listen'&&s.options.action==='custommatch'&&s.game.mode==='competitive'&&s.game.map===map&&s.game.mapgroupname==='mg_'+map&&Number(s.game.gamemodeflags)===16) {
                if(m_localVeto){m_localVeto.DeleteAsync(0);m_localVeto=null;}
                _LocalAnnouncePartyStart();LobbyAPI.StartMatchmaking('','','','');m_localStarting=false;
                let waits=0;
                function join() {if(GameStateAPI.GetMapBSPName()===map){GameInterfaceAPI.ConsoleCommand('jointeam '+team);return;}if(++waits<180)$.Schedule(1,join);}
                $.Schedule(1,join);return;
            }
            if(++attempts>30){m_localStarting=false;UiToolkitAPI.ShowGenericPopupOk('Local Premier','The local session did not become ready. Cancel and try again.','',()=>{});return;}
            if(!LobbyAPI.IsSessionActive())LobbyAPI.CreateSession();
            if(LobbyAPI.BIsHost())LobbyAPI.UpdateSessionSettings(settings);$.Schedule(.1,ready);
        }
        ready();
    }
    const m_localAllowedGameModes=['scrimcomp2v2'];
    function _LocalRestrictPlayTabs() {
        const nav=$('#PlayTypeTopNav');
        if(!nav)throw Error('Installed Play page is missing PlayTypeTopNav.');
        nav.Children().forEach(tab=>{
            tab.visible=tab.id==='Play-listen';
            if(!tab.visible) {
                tab.enabled=false;
                tab.style.visibility='collapse';
            }
        });
        const context=$.GetContextPanel();
        const modes=$('#GameModeSelectionRadios');
        if(!modes)throw Error('Installed Play page is missing GameModeSelectionRadios.');
        modes.Children().forEach(tab=>{
            tab.visible=tab.id==='scrimcomp2v2';
        });
        [
            'PlayCommunity',
            'PlayCommunityServers',
            'id-play-community-servers',
            'PlayWorkshop',
            'PrimeStatusPanel',
            'id-play-menu-get-prime',
            'PlayMenulLeaderboards',
            'gameModeButtonContainer_workshop',
            'WorkshopSearchBar',
            'WorkshopVisitButton'
        ].forEach(id=>{
            const panel=context.FindChildTraverse(id);
            if(!panel)return;
            panel.visible=false;
            panel.enabled=false;
            panel.style.visibility='collapse';
            panel.SetHasClass('hidden',true);
        });
    }
    function _LocalOpenVeto() {
        $.Msg('[CS2GC Premier] opening local veto');
        if(m_localVeto||m_localStarting)return;
        const maps=_LocalPremierPool();
        if(maps.length!==7){UiToolkitAPI.ShowGenericPopupOk('Local Premier','Seven installed Active Duty maps are required for this local veto.','',()=>{});return;}
        if(PartyListAPI.GetCount()>1){UiToolkitAPI.ShowGenericPopupOk('Local Premier','Leave your party before starting a local bot match.','',()=>{});return;}
        const root=$.CreatePanel('Panel',$.GetContextPanel(),'LocalPremierVeto');m_localVeto=root;
        root.style.ignoreParentFlow=true;root.style.position='0px 0px 0px';
        root.style.width='100%';root.style.height='100%';root.style.backgroundColor='#0c1219fa';root.style.zIndex='1000';
        if(!root.BLoadLayout('file://{resources}/layout/popups/popup_premier_pick_ban.xml',false,false))
            throw Error('The installed Premier layout could not be loaded.');
        root.AddClass('show');
        const find=id=>root.FindChildInLayoutFile(id);
        const middle=find('id-team-vote-middle');
        if(!middle||!find('id-map-vote-btn-6'))throw Error('The installed Premier layout contract changed.');
        // The native layout is shared; only this local panel is driven by our draft.
        const graph=find('id-team-vote-spider-graph');
        if(graph){graph.SetPanelEvent('oncanvaslayout',()=>{});graph.visible=false;}
        const chat=find('PartyChat');if(chat)chat.visible=false;
        const status=find('id-team-vote-title-phase');
        const history=$.CreatePanel('Label',root,'LocalVetoHistory');
        history.AddClass('stratum-regular-condensed');history.style.horizontalAlign='center';
        history.style.verticalAlign='bottom';history.style.marginBottom='80px';history.style.fontSize='16px';
        history.style.color='#aab8c1';
        const actions=$.CreatePanel('Panel',root,'LocalVetoActions');actions.style.flowChildren='right';
        actions.style.horizontalAlign='center';actions.style.verticalAlign='bottom';actions.style.marginBottom='24px';
        function button(parent,id,value,fn){const p=$.CreatePanel('Button',parent,id);p.AddClass('PopupButton');
            const label=$.CreatePanel('Label',p,'');label.AddClass('stratum-medium-condensed');label.text=value;
            p.SetPanelEvent('onactivate',fn);return p;}
        function renderPhase(phase,human) {
            root.SwitchClass('pick-ban-phase','premier-pickban-phase-'+phase);
            root.SetHasClass('your-turn',human);
            middle.SwitchClass('bg-fade',human?'premier-pickban__middle--light':'premier-pickban__middle--dark');
            find('id-team-vote-title-spinner').SetHasClass('hide',human);
            const labels=['OPENING BANS','OPPOSING BANS','FINAL BAN','DECIDER','STARTING SIDE','READY'];
            for(let i=2;i<=7;i++) {
                const bar=find('id-team-vote-phasebar-'+i);
                bar.SetDialogVariable('section-label',labels[i-2]);bar.SetDialogVariable('section-time','');
                bar.SetHasClass('premier-pickban__progress--ban',i===phase&&phase<5);
                bar.SetHasClass('premier-pickban__progress--pick',i===phase&&phase>=5);
                bar.SetHasClass('premier-pickban__progress--pre',i>phase);
                bar.SetHasClass('premier-pickban__progress--post',i<phase);
                bar.FindChildInLayoutFile('id-team-phase-bar-inner').style.width=i<phase?'100%':'0%';
            }
        }
        const humanFirst=Math.random()<.5,turns=[humanFirst,humanFirst,!humanFirst,!humanFirst,!humanFirst,humanFirst];
        const banned=[],buttons={};let step=0,ended=false,side=2;
        function advance(map) {
            if(ended||banned.includes(map))return;
            banned.push(map);buttons[map].enabled=false;buttons[map].checked=false;
            buttons[map].SetHasClass('premier-pickban-veto',true);
            buttons[map].SetDialogVariable('btm-line',turns[step]?'YOUR BAN':'OPPOSING BAN');
            $.DispatchEvent('CSGOPlaySoundEffect','UI.Premier.MapSelect','MOUSE');
            history.text+=(step?'   ·   ':'')+(turns[step]?'YOU: ':'BOTS: ')+_LocalMapName(map);step++;show();
        }
        function show() {
            const remaining=maps.filter(m=>!banned.includes(m));
            if(step===6) {
                ended=true;renderPhase(6,!humanFirst);status.text='DECIDER: '+_LocalMapName(remaining[0]);
                maps.forEach((m,i)=>{const chosen=m===remaining[0],parent=find('id-map-vote-btn-'+i);
                    parent.SetHasClass('premier-pickban__map-btn--picked',chosen);parent.SetHasClass('not-picked',!chosen);
                    buttons[m].SetHasClass('premier-pickban-pick',chosen);buttons[m].enabled=false;
                    find('id-map-vote-btn-ref-'+i).visible=false;});
                find('id-pick-vote-team').AddClass('show');
                find('id-team-vote-map-icon').SetImage('file://{images}/map_icons/map_icon_'+remaining[0]+'.svg');
                find('id-team-vote-map-icon').AddClass('show');
                find('id-team-vote-map-image').style.backgroundImage='url("file://{images}/map_icons/screenshots/360p/'+remaining[0]+'.png")';
                if(!humanFirst) {
                    status.text+=' · CHOOSE YOUR STARTING SIDE';
                    [3,2].forEach((team,i)=>{const btn=find('id-team-vote-btn-'+i).FindChild('id-pickban-btn');
                        btn.enabled=true;btn.SetPanelEvent('onactivate',()=>_LocalStartSelected(remaining[0],team));});
                } else {
                    side=Math.random()<.5?2:3;renderPhase(7,true);
                    status.text+=' · YOU START '+(side===2?'T':'CT');
                    [3,2].forEach((team,i)=>find('id-team-vote-btn-'+i).FindChild('id-pickban-btn').SetHasClass('premier-pickban-pick',side===team));
                    button(actions,'LocalVetoStart','START MATCH',()=>_LocalStartSelected(remaining[0],side));
                }
                return;
            }
            const human=turns[step];renderPhase(step<2?2:step<5?3:4,human);status.text=(human?'YOUR BAN':'OPPOSING CAPTAIN IS BANNING')+' · '+(6-step)+' bans remaining';
            maps.forEach(m=>buttons[m].enabled=human&&!banned.includes(m));
            if(!human)$.Schedule(.65,()=>{if(root.IsValid()&&m_localVeto===root)advance(remaining[Math.floor(Math.random()*remaining.length)]);});
        }
        maps.forEach((map,i)=>{
            const parent=find('id-map-vote-btn-'+i),p=parent.FindChild('id-pickban-btn');
            p.SetDialogVariable('map-name',_LocalMapName(map));p.SetDialogVariable('btm-line','');p.SetDialogVariable('status','');
            p.FindChildInLayoutFile('id-pickban-map-btn-bg').style.backgroundImage='url("file://{images}/map_icons/screenshots/360p/'+map+'.png")';
            p.SetPanelEvent('onactivate',()=>{p.checked=false;if(!ended&&turns[step]&&!banned.includes(map))advance(map);});buttons[map]=p;
            find('id-map-vote-btn-ref-'+i).SetImageFromPanel(parent,false);
        });
        [3,2].forEach((team,i)=>{
            const parent=find('id-team-vote-btn-'+i),p=parent.FindChild('id-pickban-btn'),name=team===3?'ct':'t';
            p.enabled=false;p.SetDialogVariable('map-name',team===3?'COUNTER-TERRORISTS':'TERRORISTS');
            p.SetDialogVariable('btm-line','');p.SetDialogVariable('status','');
            const image=InventoryAPI.GetItemInventoryImage(LoadoutAPI.GetItemID(name,'customplayer'));
            p.FindChildInLayoutFile('id-pickban-map-btn-bg').style.backgroundImage='url("file://{images}'+image+'.png")';
            find('id-team-vote-btn-ref-'+i).SetImageFromPanel(parent,false);
        });
        button(actions,'LocalVetoCancel','CANCEL',()=>{if(m_localStarting)return;root.DeleteAsync(0);m_localVeto=null;m_localVetoMap='';});show();
    }
'''

def patch(source,maps,online=True):
    start_search = '    function StartSearch() {'
    # Use native StartMatchmaking so the Steam party follows.
    host_online = '''
        if (m_serverSetting === 'listen' && !m_isWorkshop && LobbyAPI.BIsHost()) {
            _LocalApplyHostOnline();
            if (m_gameModeSetting !== 'premier') _LocalAnnouncePartyStart();
        }'''
    anchors=[(start_search, start_search + host_online + '''
        $.Msg('[CS2GC Premier] GO server='+m_serverSetting+' mode='+m_gameModeSetting+' workshop='+m_isWorkshop);
        if (m_serverSetting === "listen" && m_gameModeSetting === "premier" && !m_isWorkshop) {
            try { _LocalOpenVeto(); }
            catch(error) {
                if(m_localVeto){m_localVeto.DeleteAsync(0);m_localVeto=null;}
                $.Msg('[CS2GC Premier] veto failed: '+String(error));
                UiToolkitAPI.ShowGenericPopupOk('Local Premier','Could not open the local veto: '+String(error),'',()=>{});
            }
            return;
        }'''),
        # Keep the custom online hosting row visible for every local mode, not just 'classic'.
        ("            if (bForceHidden || (sessionSettings.game.type !== 'classic')) {",
         "            const _cs2gcCustom=['id-play-menu-practicesettings-hostonline'].indexOf(elChild.id)!==-1;\n            if (!_cs2gcCustom && (bForceHidden || (sessionSettings.game.type !== 'classic'))) {"),
        ('''    function _IsGameModeAvailable(serverType, gameMode) {''','''    function _IsGameModeAvailable(serverType, gameMode) {
        const localOnly=serverType==='listen' && m_localAllowedGameModes.includes(gameMode);
        _SetGameModeRadioButtonVisible(gameMode,localOnly);
        if(!localOnly)return false;'''),
        ('''    function _Init() {''','''    function _Init() {
        try { _LocalInitialize(); }
        catch(error) {
            $.Msg('[CS2GC Play] initialization failed: '+String(error));
            $.Msg('[CS2GC Play] '+String(error.stack));
            throw error;
        }
    }
    function _LocalInitialize() {'''),
        ('''        m_serverSetting = settings.options.server;
        m_gameModeSetting = settings.game.mode_ui;''',
         '''        m_serverSetting = 'listen';
        m_gameModeSetting = 'scrimcomp2v2';
        m_isWorkshop = false;'''),
        ('''    function _SelectActivePlayPlayTypeBtn() {''','''    function _SelectActivePlayPlayTypeBtn() {
        _LocalRestrictPlayTabs();
        _LocalEnsureHostOnlineToggle();
'''),
        ('''    function _ReadyForDisplay() {''','''    function _ReadyForDisplay() {
        _LocalRestrictPlayTabs();
        _LocalEnsureHostOnlineToggle();
        if(!GameStateAPI.GetMapBSPName()) {
            m_serverSetting='listen';m_isWorkshop=false;
            if(!m_localAllowedGameModes.includes(m_gameModeSetting))m_gameModeSetting='scrimcomp2v2';
            _ApplySessionSettings();
        }'''),
        ('''    function OnPressOfficialServers() {
        m_isWorkshop = false;
        m_serverSetting = 'official';
        _TurnOffDirectChallenge();
        _ApplySessionSettings();
    }''','''    function OnPressOfficialServers() {
        OnPressListenServers();
    }'''),
        ('''    function OnPressListenServers() {
        m_isWorkshop = false;
        m_serverSetting = 'listen';
        _TurnOffDirectChallenge();
        _ApplySessionSettings();
    }''','''    function OnPressListenServers() {
        m_isWorkshop = false;
        m_serverSetting = 'listen';
        if(!m_localAllowedGameModes.includes(m_gameModeSetting))m_gameModeSetting='scrimcomp2v2';
        _TurnOffDirectChallenge();
        _ApplySessionSettings();
    }'''),
        ('''    function OnPressWorkshop() {
        m_isWorkshop = true;
        _SetPlayDropdownToWorkshop();
        _TurnOffDirectChallenge();
        _UpdateDirectChallengePage(_IsSearching(), LobbyAPI.BIsHost());
        _UpdateGameModeFlagsBtn();
        _SelectActivePlayPlayTypeBtn();
    }''','''    function OnPressWorkshop() {
        OnPressListenServers();
    }'''),
        ('    function _GetAvailableMapGroups(gameMode, isPlayingOnValveOfficial) {','    function _GetAvailableMapGroups(gameMode, isPlayingOnValveOfficial) {\n        if (m_serverSetting === "listen" && !isPlayingOnValveOfficial && m_localAllowedGameModes.includes(gameMode)) return m_localInstalled.filter(m=>GetMGDetails("mg_"+m)).map(m=>"mg_"+m);\n        if (gameMode === "premier" && !isPlayingOnValveOfficial) return _LocalPremierPool().map(m=>"mg_"+m);'),
        ("            return Object.keys(mapgroup);", "            const groups=Object.keys(mapgroup);\n            if (gameMode === 'competitive' && !isPlayingOnValveOfficial) m_localInstalled.filter(m=>m.indexOf('_night')>=0).forEach(m=>{const g='mg_'+m;if(GetMGDetails(g)&&!groups.includes(g))groups.push(g);});\n            return groups;"),
        ("            selectedMaps = 'mg_lobby_mapveto';\n            primePreference = 1;", "            selectedMaps = m_serverSetting === 'listen' ? 'mg_'+(m_localVetoMap||_LocalPremierPool()[0]||'de_ancient') : 'mg_lobby_mapveto';\n            if(m_serverSetting === 'listen')gameModeFlags=16;\n            primePreference = m_serverSetting === 'listen' ? 0 : 1;"),
        ("        LobbyAPI.UpdateSessionSettings(settings);\n    }\n    function _SessionSettingsUpdate", "        if(m_serverSetting === 'listen' && m_gameModeSetting === 'premier')settings.update.Game.map=m_localVetoMap||'';\n        LobbyAPI.UpdateSessionSettings(settings);\n    }\n    function _SessionSettingsUpdate")]
    if WORKSHOP_MAP in maps:
        anchors.extend([
            ("""        const iconPath = mapGroupName === 'random_classic' ? 'file://{images}/icons/ui/random_map.svg' : 'file://{images}/' + mg.icon_image_path + '.svg';""",
             """        const iconPath = mapGroupName === 'mg_cobblewingman' ? 'file://{images}/cs2_gc/cobblestone_emblem.png' : mapGroupName === 'random_classic' ? 'file://{images}/icons/ui/random_map.svg' : 'file://{images}/' + mg.icon_image_path + '.svg';"""),
            ("""                mapImage.style.backgroundImage = 'url("file://{images}/map_icons/screenshots/720p/' + keysList[i] + '.png")';""",
             """                mapImage.style.backgroundImage = mapGroupName === 'mg_cobblewingman'
                    ? 'url("file://{images}/cs2_gc/cobblestone_banner.png")'
                    : 'url("file://{images}/map_icons/screenshots/720p/' + keysList[i] + '.png")';"""),
        ])
    for old,new in anchors:
        if source.count(old)!=1:raise ValueError('Installed local-play contract changed: '+old[:65])
        source=source.replace(old,new,1)
    practice_row = "            if (!elChild.id.startsWith('id-play-menu-practicesettings-'))"
    if source.count(practice_row) != 2:
        raise ValueError('Installed Play practice-row initialization/update contract changed.')
    source = source.replace(practice_row,
        "            if (elChild.id === 'id-play-menu-practicesettings-hostonline' ||\n"
        "                    !elChild.id.startsWith('id-play-menu-practicesettings-'))")
    marker='    function StartSearch() {'
    script=SCRIPT.replace('__MAPS__',json.dumps(maps))
    if not online:
        script=script.replace('const m_localOnline=true;','const m_localOnline=false;',1)
    return source.replace(marker,script+marker,1)

def prepare(directory,config):
    game=Path(directory).resolve().parents[1]
    maps=[WORKSHOP_MAP]
    extra=[]
    mod = game / LOCAL_PLAY_FOLDER
    map_path = mod / MAP_ARCHIVE
    staged_map = None
    if map_path.is_file():
        validate_map_archive(map_path)
    elif MAP_ASSET.is_file():
        validate_map_archive(MAP_ASSET)
        staged_map = tempfile.TemporaryDirectory(prefix='cs2gc-cobble-map-', dir=game)
        staged_path = Path(staged_map.name) / 'cobblewingman.vpk'
        shutil.copyfile(MAP_ASSET, staged_path)
        validate_map_archive(staged_path)
    if map_path.is_file() or staged_map:
        resources_result = install_cobblestone_resources(directory)
    else:
        raise ValueError('The bundled Cobblestone map package is missing; no replacement map was enabled.')
    gamemodes=vpk_file(game/'csgo/pak01_dir.vpk','gamemodes.txt').decode('utf-8-sig')
    patched_gamemodes=patch_gamemodes(gamemodes, include_cobblestone=WORKSHOP_MAP in maps)
    extra.append(('gamemodes.txt',patched_gamemodes.encode('utf-8')))
    if WORKSHOP_MAP in maps:
        from native_finishes import make_vtex
        assets=Path(__file__).resolve().parent/'map_assets'
        template = vpk_file(game/'csgo/pak01_dir.vpk',
                            'panorama/images/econ/weapon_cases/crate_operation_ii_png.vtex_c')
        extra.extend([
            ('panorama/images/cs2_gc/cobblestone_banner_png.vtex_c',
             make_vtex(template, (assets/'cobblestone_banner.png').read_bytes())),
            ('panorama/images/cs2_gc/cobblestone_emblem_png.vtex_c',
             make_vtex(template, (assets/'cobblestone_emblem.png').read_bytes(), max_size=256)),
        ])
    try:
        migrate_local_play_mount(game)
        result=install_override(directory,enabled=True,folder=LOCAL_PLAY_FOLDER,comment=LOCAL_PLAY_COMMENT,owner=LOCAL_PLAY_OWNER,
            asset='panorama/scripts/mainmenu_play.vts_c',patch=lambda source:patch(source,maps,bool(config.get('network_server',1))),extra=extra)
        if staged_map:
            map_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path = Path(staged_map.name) / 'cobblewingman.vpk'
            if map_path.exists():
                raise ValueError('Refusing to overwrite an existing Cobblestone map archive')
            staged_path.replace(map_path)
    finally:
        if staged_map:
            staged_map.cleanup()
    if map_path.is_file():
        return result+'; bundled Cobblestone map installed in the native map path; '+resources_result
    raise ValueError('Cobblestone map installation did not complete.')
