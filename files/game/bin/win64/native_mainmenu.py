"""Hide obsolete promotions and show CS Reborn branding above the Armory.

Installed mainmenu.vts_c is patched in its own VPK.
"""
from native_resources import install_override
import json
import re

ANCHOR = '    function _OnShowMainMenu() {'
STATS_NAV = """
        const statsNav = $.GetContextPanel().FindChildInLayoutFile('MainMenuNavBarNews');
        if (statsNav) statsNav.FindChildrenWithClassTraverse('mainmenu-top-navbar__radio-btn__label').forEach(label => label.text = 'STATS');
"""
MAINMENU_BETA = """
        const column = $.GetContextPanel().FindChildTraverse('JsLeftColumn');
        const armory = column && column.FindChildTraverse('id-btn-open-xpshop');
        if (column && armory) {
            let armoryBranch = armory;
            while (armoryBranch.GetParent() && armoryBranch.GetParent() !== column)
                armoryBranch = armoryBranch.GetParent();
            let indicator = column.FindChildTraverse('cs2gc-beta-indicator');
            if (!indicator) {
                indicator = $.CreatePanel('Label', column, 'cs2gc-beta-indicator', {text:'CS-REBORN BETA 1.0'});
                indicator.style.width = '100%';
                indicator.style.height = '30px';
                indicator.style.marginBottom = '8px';
                indicator.style.fontSize = '20px';
                indicator.style.color = '#f1c96b';
                indicator.style.textAlign = 'left';
                indicator.AddClass('stratum-regular-condensed');
            }
            column.MoveChildBefore(indicator, armoryBranch);
        }
"""
DEFAULT_CT_PISTOL = """
        const _cs2gcMainMenu = $.GetContextPanel();
        function _cs2gcSetDefaultCtPistol() {
            if (_cs2gcMainMenu.__cs2gcDefaultCtPistolAttempted) return;
            const APIsReady = typeof MyPersonaAPI !== 'undefined' &&
                typeof MyPersonaAPI.IsInventoryValid === 'function' &&
                typeof MyPersonaAPI.IsConnectedToGC === 'function' &&
                typeof InventoryAPI !== 'undefined' &&
                typeof InventoryAPI.GetItemDefinitionIndexFromDefinitionName === 'function' &&
                typeof InventoryAPI.GetFauxItemIDFromDefAndPaintIndex === 'function' &&
                typeof InventoryAPI.GetDefaultSlot === 'function' &&
                typeof InventoryAPI.GetItemDefinitionIndex === 'function' &&
                typeof LoadoutAPI !== 'undefined' &&
                typeof LoadoutAPI.GetItemID === 'function' &&
                typeof LoadoutAPI.GetDefaultItem === 'function' &&
                typeof LoadoutAPI.CanEquipItemInSlot === 'function' &&
                typeof LoadoutAPI.EquipItemInSlot === 'function';
            if (!APIsReady || !MyPersonaAPI.IsInventoryValid() || !MyPersonaAPI.IsConnectedToGC()) {
                const retries = _cs2gcMainMenu.__cs2gcDefaultCtPistolRetries || 0;
                if (retries < 60) {
                    _cs2gcMainMenu.__cs2gcDefaultCtPistolRetries = retries + 1;
                    $.Schedule(1, _cs2gcSetDefaultCtPistol);
                }
                return;
            }
            _cs2gcMainMenu.__cs2gcDefaultCtPistolAttempted = true;
            const p2000Def = InventoryAPI.GetItemDefinitionIndexFromDefinitionName('weapon_hkp2000');
            const uspDef = InventoryAPI.GetItemDefinitionIndexFromDefinitionName('weapon_usp_silencer');
            if (p2000Def && uspDef) {
                const p2000 = InventoryAPI.GetFauxItemIDFromDefAndPaintIndex(p2000Def, 0);
                const slot = InventoryAPI.GetDefaultSlot(p2000);
                const equipped = slot && LoadoutAPI.GetItemID('ct', slot);
                const defaultItem = slot && LoadoutAPI.GetDefaultItem('ct', slot);
                if (slot && equipped && equipped === defaultItem &&
                    InventoryAPI.GetItemDefinitionIndex(equipped) === p2000Def) {
                    const usp = InventoryAPI.GetFauxItemIDFromDefAndPaintIndex(uspDef, 0);
                    if (LoadoutAPI.CanEquipItemInSlot('ct', usp, slot)) {
                        if (LoadoutAPI.EquipItemInSlot('ct', usp, slot))
                            $.Schedule(0.25, () => $.DispatchEvent('ForceRestartVanity'));
                        else
                            $.Msg('[CS2GC] Could not equip the default CT USP-S.');
                    }
                }
            }
        }
        _cs2gcSetDefaultCtPistol();
"""
HIDE_MAINMENU_FRIENDS = """
        function _LocalHideMainMenuFriendsSidebar() {
            const context = $.GetContextPanel();
            ['JsMainMenuSidebar', 'mainmenu-sidebar__blur-target', 'JsFriendsList'].forEach(id => {
                const panel = context.FindChildTraverse(id);
                if (!panel) return;
                panel.SetHasClass('hidden', true);
                panel.visible = false;
                panel.style.visibility = 'collapse';
            });
        }
"""
HIDE_NEW_POPULAR = """
        function _LocalHideNewPopular(parent) {
            if (!parent || !parent.Children) return;
            parent.Children().forEach(child => {
                const id = String(child.id || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                const text = String(child.text || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                const namedPanel = id.indexOf('newandpopular') !== -1 || id.indexOf('newpopular') !== -1;
                const titledPanel = text.indexOf('newandpopular') !== -1 || text.indexOf('newpopular') !== -1
                    || text.indexOf('sfuiheadernewandpopular') !== -1;
                if (namedPanel || titledPanel) {
                    child.visible = false;
                    child.style.visibility = 'collapse';
                    const section = child.GetParent ? child.GetParent() : null;
                    if (section) {
                        section.visible = false;
                        section.style.visibility = 'collapse';
                    }
                }
                _LocalHideNewPopular(child);
            });
        }
"""
HIDE_CLIENT_UPDATE_BUTTON = """
        // The stock client sometimes shows a yellow "Your client needs to update" button in the main
        // menu; hide it entirely because the offline mod keeps its own armory flow.
        function _LocalHideClientUpdate(parent) {
            if (!parent || !parent.Children) return;
            const pattern = /(your\\s+client\\s+needs\\s+to\\s+update|client\\s+needs\\s+to\\s+update|needs\\s+to\\s+update)/i;
            const hide = node => {
                if (!node) return;
                const text = String(node.text || '');
                const id = String(node.id || '');
                if (pattern.test(text) || pattern.test(id)) {
                    node.visible = false;
                    node.style.visibility = 'collapse';
                    node.SetHasClass && node.SetHasClass('hidden', true);
                    const section = node.GetParent ? node.GetParent() : null;
                    if (section && section !== $.GetContextPanel()) {
                        section.visible = false;
                        section.style.visibility = 'collapse';
                        section.SetHasClass && section.SetHasClass('hidden', true);
                    }
                }
            };
            parent.Children().forEach(child => {
                hide(child);
                _LocalHideClientUpdate(child);
            });
        }
"""
ARMORY_ONLY = """
        // Keep the beta label and Armory tile in the left column.
        function _LocalCollapse(panel) {
            panel.SetHasClass('hidden', true);
            panel.visible = false;
            panel.style.visibility = 'collapse';
        }
        function _LocalKeepOnlyArmory() {
            const column = $.GetContextPanel().FindChildTraverse('JsLeftColumn');
            const armory = column && column.FindChildTraverse('id-btn-open-xpshop');
            if (!armory) return;
            const holdsArmory = panel => !!panel.FindChildTraverse('id-btn-open-xpshop');
            column.Children().forEach(child => {
                if (!holdsArmory(child) && child.id !== 'cs2gc-beta-indicator' && child.id !== 'cs2gc-whatsnew-button' &&
                    child.id !== 'cs2gc-parties-button')
                    _LocalCollapse(child);
            });
            ['id-open-fullscreen-store-btn', 'id-mini-store-carousel', 'id-major-mini-store-carousel',
             'id-img-open-major-hub', 'id-mainmenu-rush-tile-panel', 'id-mission-art'].forEach(id => {
                let node = column.FindChildTraverse(id);
                while (node && node.GetParent() && node.GetParent() !== column && !holdsArmory(node.GetParent())) node = node.GetParent();
                if (node && node !== column && !holdsArmory(node)) _LocalCollapse(node);
            });
        }
"""
MENU_REFRESH = """
        m_localMenuVisible = true;
        if (m_localMenuTimer !== null) $.CancelScheduled(m_localMenuTimer);
        // The stock menu's in-match test. The main menu runs its own loopback server, so a map name is not one.
        function _LocalInMatch() {
            return GameStateAPI.IsLocalPlayerPlayingMatch();
        }
        function _LocalRefreshVisibleMenu() {
            m_localMenuTimer = null;
            if (!m_localMenuVisible || _LocalInMatch()) return;
            _LocalHideMainMenuFriendsSidebar();
            _LocalHideNewPopular($.GetContextPanel());
            _LocalHideClientUpdate($.GetContextPanel());
            __ARMORY__
            m_localMenuTimer = $.Schedule(2, _LocalRefreshVisibleMenu);
        }
        _LocalRefreshVisibleMenu();
"""
HIDE_ANCHOR = '    function _OnHideMainMenu() {'
WHATS_NEW_ICON = 'panorama/images/cs2_gc/csreborn_icon_png.vtex_c'
WHATS_NEW = """
        // cs2_gc: one-time "What's new" window per release; closing it saves the release id via the NEW settings bridge.
        // Captured here: inside a created button's onactivate, $.GetContextPanel() is not the main menu.
        const _cs2gcWhatsNewMenu = $.GetContextPanel();
        function _LocalWhatsNewClose(overlay) {
            if (!overlay || !overlay.IsValid() || overlay.__cs2gcClosing) return;
            overlay.__cs2gcClosing = true;
            const generation = overlay.__cs2gcCloseGeneration = (overlay.__cs2gcCloseGeneration || 0) + 1;
            GameInterfaceAPI.SetSettingString('ui_cs2gc_whatsnew', __SEEN__);
            $.Msg('CS2GC_SETTING ui_cs2gc_whatsnew ' + __SEEN__);
            overlay.style.opacity = '0';
            $.Schedule(0.2, () => {
                if (overlay.IsValid() && overlay.__cs2gcClosing && overlay.__cs2gcCloseGeneration === generation)
                    overlay.DeleteAsync(0);
            });
        }
        function _LocalWhatsNewLabel(parent, text, font, size, color) {
            const label = $.CreatePanel('Label', parent, '', {text: text});
            label.AddClass(font);
            label.style.fontSize = size + 'px';
            label.style.color = color;
            label.style.width = '100%';
            return label;
        }
        // reopen: the main-menu button shows the window again even after it was closed for this release.
        function _LocalShowWhatsNew(reopen) {
            const context = _cs2gcWhatsNewMenu;
            if ((!reopen && !m_localMenuVisible) || _LocalInMatch()) return;
            const previous = context.FindChildTraverse('cs2gc-whatsnew');
            if (previous && previous.IsValid()) {
                // DeleteAsync is deferred in Panorama: reuse a fading panel instead of duplicating its ID.
                if (reopen && previous.__cs2gcClosing) {
                    previous.__cs2gcClosing = false;
                    previous.style.opacity = '1';
                }
                return;
            }
            if (!reopen && (m_localWhatsNewShown ||
                GameInterfaceAPI.GetSettingString('ui_cs2gc_whatsnew') === __SEEN__)) return;
            m_localWhatsNewShown = true;
            const data = __DATA__;
            const overlay = $.CreatePanel('Panel', context, 'cs2gc-whatsnew');
            overlay.hittest = true;
            Object.assign(overlay.style, {width: '100%', height: '100%', backgroundColor: '#000000c0', opacity: '0',
                transitionProperty: 'opacity', transitionDuration: '0.2s', zIndex: '1000'});
            const card = $.CreatePanel('Panel', overlay, 'cs2gc-whatsnew-card');
            Object.assign(card.style, {width: '760px', height: '82%', horizontalAlign: 'center', verticalAlign: 'center',
                flowChildren: 'down', backgroundColor: '#15181df8', borderRadius: '6px', border: '1px solid #ffffff1a',
                boxShadow: '0px 0px 32px 4px #000000e0'});
            const stripe = $.CreatePanel('Panel', card, '');
            Object.assign(stripe.style, {width: '100%', height: '5px', borderRadius: '6px 6px 0px 0px',
                backgroundColor: 'gradient(linear, 0% 0%, 100% 0%, from(#ff8a1f), to(#e8326e))'});
            const header = $.CreatePanel('Panel', card, '');
            Object.assign(header.style, {width: '100%', flowChildren: 'right', padding: '28px 32px 18px 32px'});
            const icon = $.CreatePanel('Image', header, '', {scaling: 'stretch-to-fit-preserve-aspect'});
            icon.SetImage('file://{images}/cs2_gc/csreborn_icon.png');
            Object.assign(icon.style, {width: '72px', height: '72px', borderRadius: '10px', verticalAlign: 'center'});
            const titles = $.CreatePanel('Panel', header, '');
            Object.assign(titles.style, {width: 'fill-parent-flow(1.0)', flowChildren: 'down', marginLeft: '20px', verticalAlign: 'center'});
            _LocalWhatsNewLabel(titles, data.title, 'stratum-bold-condensed', 34, '#ffffff');
            _LocalWhatsNewLabel(titles, data.subtitle, 'stratum-regular', 17, '#aeb6c2').style.marginTop = '2px';
            const rule = $.CreatePanel('Panel', card, '');
            Object.assign(rule.style, {width: '100%', height: '1px', backgroundColor: '#ffffff1a'});
            const body = $.CreatePanel('Panel', card, 'cs2gc-whatsnew-body');
            Object.assign(body.style, {width: '100%', height: 'fill-parent-flow(1.0)', flowChildren: 'down',
                overflow: 'squish scroll', padding: '10px 32px 18px 32px'});
            data.sections.forEach(section => {
                const heading = _LocalWhatsNewLabel(body, section[0], 'stratum-bold-condensed', 22, '#ff9a3c');
                heading.style.marginTop = '16px';
                heading.style.marginBottom = '6px';
                heading.style.letterSpacing = '1px';
                section[1].forEach(entry => {
                    const row = $.CreatePanel('Panel', body, '');
                    Object.assign(row.style, {width: '100%', flowChildren: 'right', marginBottom: '9px'});
                    const dot = $.CreatePanel('Panel', row, '');
                    Object.assign(dot.style, {width: '7px', height: '7px', borderRadius: '50%', marginTop: '9px',
                        marginRight: '14px', backgroundColor: '#e8326e'});
                    const column = $.CreatePanel('Panel', row, '');
                    Object.assign(column.style, {width: 'fill-parent-flow(1.0)', flowChildren: 'down'});
                    _LocalWhatsNewLabel(column, entry[0], 'stratum-bold', 18, '#ffffff');
                    _LocalWhatsNewLabel(column, entry[1], 'stratum-regular', 17, '#c9d0da');
                });
            });
            const footer = $.CreatePanel('Panel', card, '');
            Object.assign(footer.style, {width: '100%', flowChildren: 'right', padding: '14px 32px 24px 32px',
                borderTop: '1px solid #ffffff1a'});
            const close = $.CreatePanel('Button', footer, 'cs2gc-whatsnew-close');
            Object.assign(close.style, {horizontalAlign: 'right', padding: '10px 40px', borderRadius: '3px',
                backgroundColor: 'gradient(linear, 0% 0%, 100% 0%, from(#ff8a1f), to(#e8326e))'});
            const closeText = _LocalWhatsNewLabel(close, 'CLOSE', 'stratum-bold-condensed', 22, '#ffffff');
            closeText.style.width = 'fit-children';
            closeText.style.letterSpacing = '2px';
            close.SetPanelEvent('onactivate', () => _LocalWhatsNewClose(overlay));
            close.SetPanelEvent('onmouseover', () => close.style.washColor = '#ffffff40');
            close.SetPanelEvent('onmouseout', () => close.style.washColor = 'none');
            $.Schedule(0.05, () => { if (overlay.IsValid() && !overlay.__cs2gcClosing) overlay.style.opacity = '1'; });
        }
        // A "WHAT'S NEW" button directly above the Armory tile reopens the window at any time.
        // JsLeftColumn flows up, so the following sibling renders above the Armory; 256px matches its thin tile.
        function _LocalWhatsNewButton() {
            const column = _cs2gcWhatsNewMenu.FindChildTraverse('JsLeftColumn');
            const armory = column && column.FindChildTraverse('id-btn-open-xpshop');
            if (!column || !armory) return;
            let armoryBranch = armory;
            while (armoryBranch.GetParent() && armoryBranch.GetParent() !== column)
                armoryBranch = armoryBranch.GetParent();
            let button = column.FindChildTraverse('cs2gc-whatsnew-button');
            if (!button) {
                button = $.CreatePanel('Button', column, 'cs2gc-whatsnew-button');
                button.hittest = true;
                Object.assign(button.style, {width: '256px', height: '46px', marginBottom: '8px', flowChildren: 'right',
                    padding: '0px 14px', backgroundColor: '#15181de6', borderRadius: '4px', border: '1px solid #ffffff1a',
                    borderLeft: '3px solid #ff8a1f', transitionProperty: 'background-color', transitionDuration: '0.15s'});
                const icon = $.CreatePanel('Image', button, '', {scaling: 'stretch-to-fit-preserve-aspect'});
                icon.SetImage('file://{images}/cs2_gc/csreborn_icon.png');
                Object.assign(icon.style, {width: '28px', height: '28px', borderRadius: '5px', verticalAlign: 'center'});
                const label = _LocalWhatsNewLabel(button, "WHAT'S NEW", 'stratum-bold-condensed', 20, '#ffffff');
                Object.assign(label.style, {width: 'fill-parent-flow(1.0)', marginLeft: '12px', verticalAlign: 'center',
                    letterSpacing: '1px'});
                const version = _LocalWhatsNewLabel(button, __RELEASE__, 'stratum-regular', 15, '#aeb6c2');
                Object.assign(version.style, {width: 'fit-children', verticalAlign: 'center'});
                [icon, label, version].forEach(child => child.hittest = false);
                button.SetPanelEvent('onmouseover', () => button.style.backgroundColor = '#262b33f0');
                button.SetPanelEvent('onmouseout', () => button.style.backgroundColor = '#15181de6');
            }
            button.SetPanelEvent('onactivate', () => {
                $.Msg('CS2GC whats new: reopen requested');
                _LocalShowWhatsNew(true);
            });
            column.MoveChildAfter(button, armoryBranch);
        }
        _LocalWhatsNewButton();
        if (!m_localWhatsNewShown) $.Schedule(1.5, _LocalShowWhatsNew);
"""
PARTIES = """
        // cs2_gc: PARTIES lists CS-Reborn parties worldwide. The steam_api64 proxy tags the host's own CS2 Steam
        // party lobby and searches Steam for tagged lobbies; this page sends it "CS2GC_PARTY ..." lines and reads
        // its answers from cfg/cs2gc_parties.cfg. Joining puts players in the host's CS2 party, so the host's map
        // start (PLAY) takes the whole party to the host's server.
        const _cs2gcPartyMenu = $.GetContextPanel();
        const _cs2gcPartyKeys = ['state', 'search', 'note', 'count', 'seq', 0, 1, 2, 3, 4, 5, 6, 7]
            .map(key => 'cs2gc_party_' + key);
        const _cs2gcPartyModes = {premier: 'Premier', competitive: 'Competitive', scrimcomp2v2: 'Wingman',
            casual: 'Casual', deathmatch: 'Deathmatch', gungameprogressive: 'Arms Race', skirmish: 'War Games',
            survival: 'Danger Zone', custom: 'Custom'};
        function _LocalPartyText(hex) {
            if (!/^(?:[0-9a-f]{2})*$/.test(hex)) return '';
            try { return decodeURIComponent(hex.replace(/../g, '%$&')); } catch (e) { return ''; }
        }
        function _LocalPartyHex(text) {
            let encoded = '';
            try { encoded = encodeURIComponent(text); } catch (e) { return ''; }
            let hex = '';
            for (let i = 0; i < encoded.length; i++) {
                if (encoded[i] === '%') { hex += encoded.substr(i + 1, 2).toLowerCase(); i += 2; }
                else hex += ('0' + encoded.charCodeAt(i).toString(16)).slice(-2);
            }
            return hex;
        }
        function _LocalPartySetting(key) {
            try { return String(GameInterfaceAPI.GetSettingString(key) || ''); } catch (e) { return ''; }
        }
        function _LocalPartyRead() {
            const parties = [];
            for (let i = 0; i < 8; i++) {
                const fields = _LocalPartySetting('cs2gc_party_' + i).split('|');
                if (fields.length !== 7 || !/^[0-9]+$/.test(fields[0]) || !/^[0-9]+$/.test(fields[1])) continue;
                parties.push({lobby: fields[0], host: fields[1], members: parseInt(fields[2], 10) || 0,
                    limit: parseInt(fields[3], 10) || 0, mode: fields[4], own: fields[5] === '1',
                    name: _LocalPartyText(fields[6]).replace(/^#+/, '') || 'CS-Reborn party'});
            }
            return {seq: _LocalPartySetting('cs2gc_party_seq'), state: _LocalPartySetting('cs2gc_party_state'),
                search: _LocalPartySetting('cs2gc_party_search'),
                note: _LocalPartyText(_LocalPartySetting('cs2gc_party_note')), parties: parties};
        }
        function _LocalPartySession() {
            try { return LobbyAPI.IsSessionActive() ? LobbyAPI.GetSessionSettings() : null; } catch (e) { return null; }
        }
        // Persona names come decorated for rich labels (<span class='decorated-player-name__...'>NAME</span>).
        function _LocalPartyPlain(text) {
            const named = {amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' '};
            return String(text || '').replace(/<[^>]*>/g, '')
                .replace(/&(?:#x([0-9a-f]+)|#([0-9]+)|(amp|lt|gt|quot|apos|nbsp));/gi, (entity, hex, dec, name) => {
                    if (name) return named[name.toLowerCase()];
                    const code = hex ? parseInt(hex, 16) : parseInt(dec, 10);
                    return code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : entity;
                }).trim();
        }
        function _LocalPartyMembers(session) {
            const members = session && session.members, names = [];
            const count = members ? Number(members.numPlayers) || 0 : 0;
            for (let i = 0; i < count; i++) {
                const machine = members['machine' + i];
                const xuid = machine && machine.player0 && machine.player0.xuid;
                if (!xuid) continue;
                let name = '';
                try { name = _LocalPartyPlain(FriendsListAPI.GetFriendName(String(xuid))); } catch (e) {}
                names.push(name || String(xuid));
            }
            return names;
        }
        function _LocalPartyModeName(mode) {
            return _cs2gcPartyModes[mode] || (mode ? mode.charAt(0).toUpperCase() + mode.slice(1) : 'Custom');
        }
        function _LocalPartyLabel(parent, id, size, color) {
            const label = $.CreatePanel('Label', parent, id, {text: ''});
            label.AddClass('stratum-regular');
            Object.assign(label.style, {width: '100%', fontSize: size + 'px', color: color});
            return label;
        }
        function _LocalPartyButton(parent, id, text, action) {
            const button = $.CreatePanel('Button', parent, id);
            button.hittest = true;
            Object.assign(button.style, {padding: '8px 22px', marginRight: '10px', borderRadius: '3px',
                backgroundColor: '#ffffff14', border: '1px solid #ffffff26', verticalAlign: 'center'});
            const label = _LocalWhatsNewLabel(button, text, 'stratum-bold-condensed', 18, '#ffffff');
            Object.assign(label.style, {width: 'fit-children', letterSpacing: '1px'});
            label.hittest = false;
            button.SetPanelEvent('onactivate', action);
            button.SetPanelEvent('onmouseover', () => button.style.washColor = '#ffffff30');
            button.SetPanelEvent('onmouseout', () => button.style.washColor = 'none');
            return button;
        }
        function _LocalPartyHost(ui, tries) {
            if (ui !== m_localPartyUi || ui.closing) return;
            if (!LobbyAPI.IsSessionActive()) {
                if (tries >= 3) {
                    ui.local = 'Steam did not open a party lobby. Make sure Steam is online and try again.';
                    _LocalPartyRender(ui);
                    return;
                }
                LobbyAPI.CreateSession();
                $.Schedule(1, () => _LocalPartyHost(ui, tries + 1));
                return;
            }
            if (!LobbyAPI.BIsHost()) {
                ui.local = 'You are in someone else\\'s party. Leave it before hosting your own.';
                _LocalPartyRender(ui);
                return;
            }
            const session = LobbyAPI.GetSessionSettings() || {};
            const access = session.system && session.system.access;
            if (!m_localPartyAccess) m_localPartyAccess = access === 'public' ? 'public' : 'private';
            LobbyAPI.UpdateSessionSettings({update: {system: {access: 'public'}}});
            const game = session.game || {};
            const mode = String(game.mode_ui || game.mode || '').toLowerCase().replace(/[^a-z0-9_]/g, '').slice(0, 24);
            let player = '';
            try { player = _LocalPartyPlain(MyPersonaAPI.GetName()); } catch (e) {}
            const name = player ? player.slice(0, 20) + '\\'s party' : 'CS-Reborn party';
            $.Msg('CS2GC_PARTY host ' + _LocalPartyHex(name) + ' ' + (mode || 'custom'));
            ui.local = 'Opening your party to other CS-Reborn players...';
            _LocalPartyRender(ui);
        }
        function _LocalPartyUnhost(ui) {
            $.Msg('CS2GC_PARTY unhost');
            try {
                if (m_localPartyAccess && LobbyAPI.IsSessionActive() && LobbyAPI.BIsHost())
                    LobbyAPI.UpdateSessionSettings({update: {system: {access: m_localPartyAccess}}});
            } catch (e) {}
            m_localPartyAccess = '';
        }
        function _LocalPartyRender(ui) {
            if (ui !== m_localPartyUi || ui.closing || !ui.overlay.IsValid()) return;
            const info = _LocalPartyRead(), session = _LocalPartySession(), members = _LocalPartyMembers(session);
            let isHost = true;
            try { isHost = !session || LobbyAPI.BIsHost(); } catch (e) {}
            if (info.seq !== ui.seq) {
                if (ui.seq !== null) ui.local = '';
                ui.seq = info.seq;
            }
            const missing = !info.seq && ui.ticks > 6;
            const signature = JSON.stringify([info, members, isHost, ui.local, missing]);
            if (signature === ui.signature) return;
            ui.signature = signature;
            const states = {
                hosting: 'Your party is listed for every CS-Reborn player. When everyone is in, pick a map in PLAY: ' +
                    'the whole party follows you to your server.',
                waiting: 'Opening your party to other CS-Reborn players...',
                joining: 'Joining the party through Steam...',
                member: 'You are in a party. When the host starts a map, you follow automatically.',
                idle: 'Host a party for other CS-Reborn players, or join one below.'};
            ui.status.text = info.seq ? states[info.state] || states.idle : missing ?
                'The party service is not running. Start CS2 from the CS-Reborn launcher with Steam online.' :
                'Connecting to Steam...';
            const note = ui.local || info.note;
            ui.note.text = note;
            ui.note.visible = !!note;
            ui.members.text = members.length ? 'YOUR PARTY (' + members.length + '): ' + members.join(', ') :
                'You are not in a party yet.';
            const hosting = info.state === 'hosting' || info.state === 'waiting';
            ui.host.visible = !!info.seq && !hosting && info.state !== 'joining';
            ui.host.enabled = isHost;
            ui.host.style.opacity = isHost ? '1' : '0.45';
            ui.stop.visible = hosting;
            ui.leave.visible = members.length > 1 || info.state === 'member';
            ui.list.RemoveAndDeleteChildren();
            info.parties.forEach((party, index) => {
                const row = $.CreatePanel('Panel', ui.list, 'cs2gc-parties-row-' + index);
                Object.assign(row.style, {width: '100%', flowChildren: 'right', padding: '10px 14px', marginBottom: '6px',
                    borderRadius: '4px', backgroundColor: party.own ? '#ff8a1f1f' : '#ffffff0d'});
                const text = $.CreatePanel('Panel', row, '');
                Object.assign(text.style, {width: 'fill-parent-flow(1.0)', flowChildren: 'down', verticalAlign: 'center'});
                _LocalWhatsNewLabel(text, party.name, 'stratum-bold', 19, '#ffffff');
                const full = party.limit > 0 && party.members >= party.limit;
                _LocalWhatsNewLabel(text, _LocalPartyModeName(party.mode) + '  \\u00b7  ' + party.members +
                    (party.limit ? '/' + party.limit : '') + ' players', 'stratum-regular', 16, '#aeb6c2');
                if (party.own || full) {
                    const tag = _LocalWhatsNewLabel(row, party.own ? 'YOUR PARTY' : 'FULL', 'stratum-bold-condensed', 18,
                        party.own ? '#ff9a3c' : '#7d8692');
                    Object.assign(tag.style, {width: 'fit-children', verticalAlign: 'center', marginRight: '6px'});
                    return;
                }
                const join = _LocalPartyButton(row, 'cs2gc-parties-join-' + index, 'JOIN', () => {
                    $.Msg('CS2GC_PARTY join ' + party.lobby + ' ' + party.host);
                    ui.local = 'Asking Steam to join ' + party.name + '...';
                    _LocalPartyRender(ui);
                });
                join.style.backgroundColor = 'gradient(linear, 0% 0%, 100% 0%, from(#ff8a1f), to(#e8326e))';
                join.style.marginRight = '0px';
            });
            if (!info.parties.some(party => !party.own)) {
                const empty = info.search === 'done' ? 'No open parties right now. Host one, or refresh in a moment.' :
                    info.search === 'failed' ? 'Could not load parties.' : 'Searching for parties...';
                _LocalWhatsNewLabel(ui.list, empty, 'stratum-regular', 17, '#7d8692').style.marginTop = '8px';
            }
        }
        function _LocalPartyTick(ui) {
            ui.timer = null;
            if (ui !== m_localPartyUi || ui.closing || !ui.overlay.IsValid()) return;
            if (_LocalInMatch()) {
                _LocalPartyClose(ui);
                return;
            }
            _LocalPartyRender(ui);
            // cfg values become readable once the queued exec runs; the next tick renders them.
            if (ui.ticks >= ui.nextRefresh) {
                $.Msg('CS2GC_PARTY refresh');
                ui.nextRefresh = ui.ticks + 10;
            }
            ui.ticks++;
            GameInterfaceAPI.ConsoleCommand('exec cs2gc_parties');
            ui.timer = $.Schedule(1, () => _LocalPartyTick(ui));
        }
        function _LocalPartyClose(ui) {
            if (!ui || ui.closing) return;
            ui.closing = true;
            if (ui.timer !== null) $.CancelScheduled(ui.timer);
            ui.timer = null;
            // setinfo values may travel to servers as user info: keep other players' party data out of it.
            _cs2gcPartyKeys.forEach(key => { try { GameInterfaceAPI.SetSettingString(key, ''); } catch (e) {} });
            const generation = ui.generation = (ui.generation || 0) + 1;
            ui.overlay.style.opacity = '0';
            $.Schedule(0.2, () => {
                if (ui.overlay.IsValid() && ui.closing && ui.generation === generation) {
                    ui.overlay.DeleteAsync(0);
                    if (m_localPartyUi === ui) m_localPartyUi = null;
                }
            });
        }
        function _LocalShowParties() {
            if (_LocalInMatch()) return;
            const previous = m_localPartyUi;
            if (previous && previous.overlay.IsValid()) {
                if (previous.closing) {
                    previous.closing = false;
                    previous.generation++;
                    previous.overlay.style.opacity = '1';
                    previous.signature = '';
                    _LocalPartyTick(previous);
                }
                return;
            }
            const overlay = $.CreatePanel('Panel', _cs2gcPartyMenu, 'cs2gc-parties');
            overlay.hittest = true;
            Object.assign(overlay.style, {width: '100%', height: '100%', backgroundColor: '#000000c0', opacity: '0',
                transitionProperty: 'opacity', transitionDuration: '0.2s', zIndex: '1000'});
            const card = $.CreatePanel('Panel', overlay, '');
            Object.assign(card.style, {width: '760px', height: '82%', horizontalAlign: 'center', verticalAlign: 'center',
                flowChildren: 'down', backgroundColor: '#15181df8', borderRadius: '6px', border: '1px solid #ffffff1a',
                boxShadow: '0px 0px 32px 4px #000000e0'});
            const stripe = $.CreatePanel('Panel', card, '');
            Object.assign(stripe.style, {width: '100%', height: '5px', borderRadius: '6px 6px 0px 0px',
                backgroundColor: 'gradient(linear, 0% 0%, 100% 0%, from(#e8326e), to(#ff8a1f))'});
            const header = $.CreatePanel('Panel', card, '');
            Object.assign(header.style, {width: '100%', flowChildren: 'down', padding: '26px 32px 16px 32px'});
            _LocalWhatsNewLabel(header, 'PARTIES', 'stratum-bold-condensed', 34, '#ffffff');
            _LocalWhatsNewLabel(header, 'Play online with other CS-Reborn players. Host a party or join one: when the ' +
                'host starts a map, everyone in the party follows automatically.', 'stratum-regular', 17, '#aeb6c2');
            const rule = $.CreatePanel('Panel', card, '');
            Object.assign(rule.style, {width: '100%', height: '1px', backgroundColor: '#ffffff1a'});
            const body = $.CreatePanel('Panel', card, '');
            Object.assign(body.style, {width: '100%', height: 'fill-parent-flow(1.0)', flowChildren: 'down',
                padding: '16px 32px 12px 32px'});
            const ui = {overlay: overlay, timer: null, ticks: 0, nextRefresh: 0, seq: null, signature: '', local: '',
                closing: false, generation: 0};
            ui.status = _LocalPartyLabel(body, 'cs2gc-parties-status', 18, '#ffffff');
            ui.note = _LocalPartyLabel(body, 'cs2gc-parties-note', 16, '#ffb15c');
            ui.note.style.marginTop = '6px';
            ui.members = _LocalPartyLabel(body, 'cs2gc-parties-members', 16, '#aeb6c2');
            ui.members.style.marginTop = '10px';
            const actions = $.CreatePanel('Panel', body, '');
            Object.assign(actions.style, {width: '100%', flowChildren: 'right', marginTop: '14px'});
            ui.host = _LocalPartyButton(actions, 'cs2gc-parties-host', 'HOST PARTY', () => _LocalPartyHost(ui, 0));
            ui.stop = _LocalPartyButton(actions, 'cs2gc-parties-stop', 'STOP HOSTING', () => {
                _LocalPartyUnhost(ui);
                _LocalPartyRender(ui);
            });
            ui.leave = _LocalPartyButton(actions, 'cs2gc-parties-leave', 'LEAVE PARTY', () => {
                if (ui.stop.visible) _LocalPartyUnhost(ui);
                LobbyAPI.CloseSession();
                _LocalPartyRender(ui);
            });
            const listHeader = $.CreatePanel('Panel', body, '');
            Object.assign(listHeader.style, {width: '100%', flowChildren: 'right', marginTop: '24px', marginBottom: '8px'});
            const heading = _LocalWhatsNewLabel(listHeader, 'OPEN PARTIES', 'stratum-bold-condensed', 22, '#ff9a3c');
            Object.assign(heading.style, {width: 'fill-parent-flow(1.0)', verticalAlign: 'center', letterSpacing: '1px'});
            const refresh = _LocalPartyButton(listHeader, 'cs2gc-parties-refresh', 'REFRESH', () => {
                $.Msg('CS2GC_PARTY refresh');
                ui.nextRefresh = ui.ticks + 10;
            });
            refresh.style.marginRight = '0px';
            ui.list = $.CreatePanel('Panel', body, 'cs2gc-parties-list');
            Object.assign(ui.list.style, {width: '100%', height: 'fill-parent-flow(1.0)', flowChildren: 'down',
                overflow: 'squish scroll'});
            const footer = $.CreatePanel('Panel', card, '');
            Object.assign(footer.style, {width: '100%', flowChildren: 'right', padding: '14px 32px 24px 32px',
                borderTop: '1px solid #ffffff1a'});
            const close = _LocalPartyButton(footer, 'cs2gc-parties-close', 'CLOSE', () => _LocalPartyClose(ui));
            Object.assign(close.style, {horizontalAlign: 'right', marginRight: '0px', padding: '10px 40px',
                backgroundColor: 'gradient(linear, 0% 0%, 100% 0%, from(#ff8a1f), to(#e8326e))'});
            m_localPartyUi = ui;
            _LocalPartyTick(ui);
            $.Schedule(0.05, () => { if (overlay.IsValid() && !ui.closing) overlay.style.opacity = '1'; });
        }
        // PARTIES sits above WHAT'S NEW (JsLeftColumn flows up).
        function _LocalPartiesButton() {
            const column = _cs2gcPartyMenu.FindChildTraverse('JsLeftColumn');
            const whatsNew = column && column.FindChildTraverse('cs2gc-whatsnew-button');
            if (!column || !whatsNew) return;
            let button = column.FindChildTraverse('cs2gc-parties-button');
            if (!button) {
                button = $.CreatePanel('Button', column, 'cs2gc-parties-button');
                button.hittest = true;
                Object.assign(button.style, {width: '256px', height: '46px', marginBottom: '8px', flowChildren: 'right',
                    padding: '0px 14px', backgroundColor: '#15181de6', borderRadius: '4px', border: '1px solid #ffffff1a',
                    borderLeft: '3px solid #e8326e', transitionProperty: 'background-color', transitionDuration: '0.15s'});
                const label = _LocalWhatsNewLabel(button, 'PARTIES', 'stratum-bold-condensed', 20, '#ffffff');
                Object.assign(label.style, {width: 'fill-parent-flow(1.0)', verticalAlign: 'center', letterSpacing: '1px'});
                const online = _LocalWhatsNewLabel(button, 'ONLINE', 'stratum-regular', 15, '#aeb6c2');
                Object.assign(online.style, {width: 'fit-children', verticalAlign: 'center'});
                [label, online].forEach(child => child.hittest = false);
                button.SetPanelEvent('onmouseover', () => button.style.backgroundColor = '#262b33f0');
                button.SetPanelEvent('onmouseout', () => button.style.backgroundColor = '#15181de6');
            }
            button.SetPanelEvent('onactivate', () => {
                $.Msg('CS2GC parties: open requested (map "' + GameStateAPI.GetMapBSPName() + '")');
                _LocalShowParties();
            });
            column.MoveChildAfter(button, whatsNew);
        }
        _LocalPartiesButton();
"""


def whats_new_script():
    from whats_new import DISPLAY_VERSION, SEEN_ID, SECTIONS, SUBTITLE, TITLE
    data = {'title': TITLE, 'subtitle': SUBTITLE, 'sections': [[header, [list(entry) for entry in entries]]
                                                                for header, entries in SECTIONS]}
    return (WHATS_NEW.replace('__SEEN__', json.dumps(SEEN_ID)).replace('__DATA__', json.dumps(data))
            .replace('__RELEASE__', json.dumps(DISPLAY_VERSION)))


def whats_new_icon(game):
    """The mod icon compiled like the other cs2_gc panorama images; None if the installed template is missing."""
    from pathlib import Path
    from native_finishes import make_vtex
    from native_resources import vpk_file
    directory = Path(game) / 'csgo/pak01_dir.vpk'
    if not directory.is_file():
        return None
    template = vpk_file(directory, 'panorama/images/econ/weapon_cases/crate_operation_ii_png.vtex_c')
    icon = Path(__file__).resolve().parent / 'cs2_gc_mod_icon.png'
    return make_vtex(template, icon.read_bytes(), max_size=256)

WATCH_SETTINGS = """
    // cs2_gc: CS2-style slide toggle, styled inline after slider_toggle.css (the Watch page does not load it).
    const _cs2gcAnimBoot = GameInterfaceAPI.GetSettingString('ui_cs2gc_animations') === 'csgo';
    const _cs2gcGraphicsBoot = GameInterfaceAPI.GetSettingString('ui_low_end_pc') === '1';
    function _LocalRestartToggle(parent, id, titleText, description, setting, bootValue, initialValue) {
        const row = $.CreatePanel('Button', parent, id);
        Object.assign(row.style, {flowChildren:'right', width:'100%', margin:'0px',
            padding:'16px 20px', backgroundColor:'rgba(0,0,0,0.35)', borderRadius:'4px'});
        const text = $.CreatePanel('Panel', row, '');
        Object.assign(text.style, {flowChildren:'down', width:'fill-parent-flow(1)', verticalAlign:'center'});
        const title = $.CreatePanel('Label', text, '', {text:titleText});
        title.AddClass('stratum-regular-condensed');
        Object.assign(title.style, {fontSize:'20px', color:'white', fontWeight:'medium'});
        const about = $.CreatePanel('Label', text, '', {text:description});
        Object.assign(about.style, {fontSize:'15px', color:'#a5b1bd', marginTop:'4px'});
        const status = $.CreatePanel('Label', text, id + 'Status', {text:''});
        Object.assign(status.style, {fontSize:'14px', marginTop:'6px', fontWeight:'bold'});
        const pill = $.CreatePanel('Panel', row, '');
        Object.assign(pill.style, {width:'46px', height:'24px', borderRadius:'12px', verticalAlign:'center',
            marginLeft:'24px', transitionProperty:'background-color', transitionDuration:'.25s'});
        const knob = $.CreatePanel('Panel', pill, '');
        Object.assign(knob.style, {width:'16px', height:'16px', margin:'2px', borderRadius:'50%', backgroundColor:'white',
            verticalAlign:'center', horizontalAlign:'left', transitionProperty:'transform', transitionDuration:'.25s'});
        const show = on => {
            pill.style.backgroundColor = on ? 'gradient(radial, 50% 60%, 0% 0%, 90% 70%, from(#22a527), color-stop(.7, #22a527), to(#0a580a))'
                                            : 'rgba(0,0,0,0.45)';
            pill.style.border = on ? '2px solid #147717' : '2px solid rgba(255,255,255,0.18)';
            knob.style.transform = on ? 'translateX(22px)' : 'translateX(0px)';
            status.text = on === bootValue ? (on ? 'Low-end graphics active' : 'Default graphics active')
                                           : 'Restart CS2 to apply';
            status.style.color = on === bootValue ? '#7ec27f' : '#e8c15a';
        };
        let on = initialValue;
        show(on);
        row.SetPanelEvent('onactivate', () => {
            on = !on;
            const value = on ? '1' : '0';
            GameInterfaceAPI.SetSettingString(setting, value);
            $.Msg('CS2GC_SETTING ' + setting + ' ' + value);
            show(on);
        });
        row.SetPanelEvent('onmouseover', () => { row.style.backgroundColor = 'rgba(255,255,255,0.07)'; });
        row.SetPanelEvent('onmouseout', () => { row.style.backgroundColor = 'rgba(0,0,0,0.35)'; });
        return row;
    }

    function _LocalAnimationToggle(parent) {
        const row = $.CreatePanel('Button', parent, 'CS2GCAnimationToggle');
        Object.assign(row.style, {flowChildren:'right', width:'100%', margin:'0px',
            padding:'16px 20px', backgroundColor:'rgba(0,0,0,0.35)', borderRadius:'4px'});
        const text = $.CreatePanel('Panel', row, '');
        Object.assign(text.style, {flowChildren:'down', width:'fill-parent-flow(1)', verticalAlign:'center'});
        const title = $.CreatePanel('Label', text, '', {text:'USE OLD CS:GO ANIMATIONS'});
        title.AddClass('stratum-regular-condensed');
        Object.assign(title.style, {fontSize:'20px', color:'white', fontWeight:'medium'});
        const about = $.CreatePanel('Label', text, '', {text:'Off (default): current CS2 viewmodel animations. On: the original ' +
            'CS:GO draw, inspect and reload animations for guns and knives. Restart CS2 to apply.'});
        Object.assign(about.style, {fontSize:'15px', color:'#a5b1bd', marginTop:'4px'});
        const status = $.CreatePanel('Label', text, 'CS2GCAnimationStatus', {text:''});
        Object.assign(status.style, {fontSize:'14px', marginTop:'6px', fontWeight:'bold'});
        const pill = $.CreatePanel('Panel', row, '');
        Object.assign(pill.style, {width:'46px', height:'24px', borderRadius:'12px', verticalAlign:'center',
            marginLeft:'24px', transitionProperty:'background-color', transitionDuration:'.25s'});
        const knob = $.CreatePanel('Panel', pill, '');
        Object.assign(knob.style, {width:'16px', height:'16px', margin:'2px', borderRadius:'50%', backgroundColor:'white',
            verticalAlign:'center', horizontalAlign:'left', transitionProperty:'transform', transitionDuration:'.25s'});
        const show = on => {
            pill.style.backgroundColor = on ? 'gradient(radial, 50% 60%, 0% 0%, 90% 70%, from(#22a527), color-stop(.7, #22a527), to(#0a580a))'
                                            : 'rgba(0,0,0,0.45)';
            pill.style.border = on ? '2px solid #147717' : '2px solid rgba(255,255,255,0.18)';
            knob.style.transform = on ? 'translateX(22px)' : 'translateX(0px)';
            status.text = on === _cs2gcAnimBoot ? (on ? 'CS:GO animations active' : 'CS2 animations active')
                                                : 'Restart CS2 to apply';
            status.style.color = on === _cs2gcAnimBoot ? '#7ec27f' : '#e8c15a';
        };
        let on = GameInterfaceAPI.GetSettingString('ui_cs2gc_animations') === 'csgo';
        show(on);
        row.SetPanelEvent('onactivate', () => {
            on = !on;
            const value = on ? 'csgo' : 'cs2';
            GameInterfaceAPI.SetSettingString('ui_cs2gc_animations', value);
            $.Msg('CS2GC_SETTING ui_cs2gc_animations ' + value);
            show(on);
        });
        row.SetPanelEvent('onmouseover', () => { row.style.backgroundColor = 'rgba(255,255,255,0.07)'; });
        row.SetPanelEvent('onmouseout', () => { row.style.backgroundColor = 'rgba(0,0,0,0.35)'; });
        return row;
    }

    function _LocalShowNewSettings() {
        const radio = $('#WatchNavBarYourMatches');
        const panel = $('#JsYourMatches');
        if (!radio || !panel) throw Error('Installed NEW settings navigation contract changed.');
        radio.GetParent().Children().forEach(child => {
            child.visible = child === radio;
            child.enabled = child === radio;
        });
        radio.checked = true;
        ['JsDownloaded', 'JsLive', 'JsTournaments', 'JsEvents'].forEach(id => {
            const child = $('#' + id);
            if (child) { child.visible = false; child.enabled = false; }
        });
        if (!panel.__cs2gcSettingsPlaceholder) {
            panel.RemoveAndDeleteChildren();
            const heading = $.CreatePanel('Label', panel, 'CS2GCNewSettingsHeading',
                {text:'NEW SETTINGS FOR CS-REBORN'});
            heading.AddClass('stratum-regular-condensed');
            heading.style.fontSize = '28px';
            heading.style.margin = '32px';
            const columns = $.CreatePanel('Panel', panel, 'CS2GCSettingsColumns');
            Object.assign(columns.style, {flowChildren:'right', width:'100%', padding:'0px 32px'});
            const gameplay = $.CreatePanel('Panel', columns, 'CS2GCGameplaySettingsColumn');
            Object.assign(gameplay.style, {flowChildren:'down', width:'fill-parent-flow(1)', marginRight:'24px'});
            const graphics = $.CreatePanel('Panel', columns, 'CS2GCGraphicsSettingsColumn');
            Object.assign(graphics.style, {flowChildren:'down', width:'fill-parent-flow(1)'});
            const gameplayHeading = $.CreatePanel('Label', gameplay, 'CS2GCGameplaySettingsHeading',
                {text:'NEW GAMEPLAY SETTINGS'});
            gameplayHeading.AddClass('stratum-regular-condensed');
            Object.assign(gameplayHeading.style, {fontSize:'24px', color:'white', marginBottom:'12px'});
            const graphicsHeading = $.CreatePanel('Label', graphics, 'CS2GCGraphicsSettingsHeading',
                {text:'NEW GRAPHIC SETTINGS'});
            graphicsHeading.AddClass('stratum-regular-condensed');
            Object.assign(graphicsHeading.style, {fontSize:'24px', color:'white', marginBottom:'12px'});
            _LocalAnimationToggle(gameplay);
            _LocalRestartToggle(graphics, 'CS2GCLowEndGraphicsToggle', 'ENABLE LOW END PC GRAPHICS',
                'Reduces shadows, particles, decals, fog, sky and texture detail. Restart CS2 to apply.',
                'ui_low_end_pc', _cs2gcGraphicsBoot, _cs2gcGraphicsBoot);
            panel.__cs2gcSettingsPlaceholder = true;
        }
        _m_activeTab = panel;
        _m_contextTab = panel;
        panel.RemoveClass('WatchMenu--Hide');
        panel.visible = true;
        panel.SetReadyForDisplay(true);
    }
"""


def patch_watch(source):
    if '_LocalShowNewSettings' in source:
        raise ValueError('Watch settings page is already patched')
    replacements = (
        ('    function _UpdateTab(', '    function UpdateActiveTab()',
         '    function _UpdateTab() { _LocalShowNewSettings(); }\n'),
        ('    function NavigateToTab(', '    mainmenu_watch.NavigateToTab =',
         '    function NavigateToTab() { _LocalShowNewSettings(); }\n'),
        ('    function InitMainWatchPanel()', '    mainmenu_watch.InitMainWatchPanel =',
         WATCH_SETTINGS + '    function InitMainWatchPanel() { _LocalShowNewSettings(); }\n'),
        ('    function ShowActiveTournamentPage(', '    mainmenu_watch.ShowActiveTournamentPage =',
         '    function ShowActiveTournamentPage() { _LocalShowNewSettings(); }\n'),
    )
    for start, end, replacement in replacements:
        if source.count(start) != 1 or source.count(end) != 1:
            raise ValueError('Installed Watch script contract changed: ' + start)
        first, last = source.index(start), source.index(end)
        if last <= first:
            raise ValueError('Installed Watch script function order changed')
        source = source[:first] + replacement + source[last:]
    return source


def patch_watch_labels(text):
    for key, value in (('tooltip_navbar_watch', 'NEW SETTINGS FOR CS-REBORN'),
                       ('SFUI_MainMenu_Watch', 'NEW SETTINGS FOR CS-REBORN'),
                       ('CSGO_Watch_Cat_YourMatches', 'NEW')):
        pattern = re.compile(r'("' + re.escape(key) + r'"\s*)"[^"\r\n]*"', re.I)
        if len(pattern.findall(text)) != 1:
            raise ValueError('Installed Watch localization contract changed: ' + key)
        text = pattern.sub(lambda match: match[1] + '"' + value + '"', text)
    return text


def patch(source, care_packages=False, hide_promo=True, pet_id='0'):
    store = "NavigateToTab('JsMainMenuStore', 'mainmenu_store_fullscreen', openToSection !== '' ? openToSection : 'id-store-nav-coupon');"
    store_replacement = "NavigateToTab('JsMainMenuStore', 'mainmenu_store_fullscreen', 'id-store-nav-xpshop');"
    mission = "$('#id-pausemenu-mission-panel').SetHasClass('hide-non-prime', MyPersonaAPI.GetElevatedState() != 'elevated');"
    mission_replacement = """const missionPanel = $('#id-pausemenu-mission-panel');
        if (missionPanel) { missionPanel.visible = false; missionPanel.style.visibility = 'collapse'; }"""
    if (source.count(ANCHOR) != 1 or source.count(HIDE_ANCHOR) != 1 or
            source.count(store) != 1 or source.count(mission) != 1 or
            'cs2_gc: cosmetic only' in source or 'const statsNav =' in source or
            '_LocalHideNewPopular' in source or '_LocalHideMainMenuFriendsSidebar' in source or
            '__cs2gcDefaultCtPistolAttempted' in source or
            'cs2gc-mainmenu-brand-banner' in source):
        raise ValueError('Installed main menu layout changed; no patch written')
    source=source.replace(ANCHOR, '    let m_localMenuTimer = null;\n    let m_localMenuVisible = false;\n' +
                          '    let m_localWhatsNewShown = false;\n    let m_localPartyUi = null;\n    let m_localPartyAccess = \'\';\n' +
                          ANCHOR + STATS_NAV + MAINMENU_BETA + DEFAULT_CT_PISTOL + HIDE_MAINMENU_FRIENDS +
                          HIDE_NEW_POPULAR + HIDE_CLIENT_UPDATE_BUTTON +
                          (ARMORY_ONLY if hide_promo else "") +
                          MENU_REFRESH.replace('__ARMORY__', '_LocalKeepOnlyArmory();' if hide_promo else '') +
                          whats_new_script() + PARTIES, 1)
    source=source.replace(HIDE_ANCHOR, HIDE_ANCHOR + '''
        m_localMenuVisible = false;
        if (m_localMenuTimer !== null) {
            $.CancelScheduled(m_localMenuTimer);
            m_localMenuTimer = null;
        }
''', 1)
    source=source.replace(store, store_replacement, 1)
    source=source.replace(mission, mission_replacement, 1)
    if care_packages:
        anchor = """        if (!$('#MainMenuNavBarHome').checked)
            return;
        const objStore = InventoryAPI.GetCacheTypeElementJSOByIndex("PersonalStore", 0);"""
        replacement = """        // cs2_gc: present saved choices only on Inventory, outside a match.
        if (GameStateAPI.GetMapBSPName()) return;
        if (!$('#MainMenuNavBarInventory').checked)
            return;
        const objStore = InventoryAPI.GetCacheTypeElementJSOByIndex("PersonalStore", 0);"""
        if source.count(anchor) != 1: raise ValueError('Installed care-package notification anchor changed')
        source=source.replace(anchor,replacement,1)
    if str(pet_id).isdigit() and int(pet_id)>1000000000000:
        source=source.replace(ANCHOR,"    let m_localPetApplied=false;\n"+ANCHOR+'''
        if(!m_localPetApplied && MyPersonaAPI.IsInventoryValid()) {
            m_localPetApplied=true;
            const id='__PET_ID__';
            LoadoutAPI.EquipItemInSlot('noteam',id,InventoryAPI.GetDefaultSlot(id));
            $.Schedule(.25,()=>$.DispatchEvent('ForceRestartVanity'));
        }
'''.replace('__PET_ID__',str(pet_id)),1)
    return source


def patch_pet_food(source, owned_ids):
    """The offline match-driven pets do not participate in timed feeding."""
    anchor = '    function _ShowFoodHint(elPanel, petItemId) {'
    if source.count(anchor) != 1 or 'cs2_gc: permanent companion' in source:
        raise ValueError('Installed pet food hint changed; no patch written')
    ids = [str(value) for value in owned_ids if str(value).isdigit() and int(value) > 1000000000000]
    return source.replace(anchor, anchor + '''
        // cs2_gc: permanent companion; growth follows completed matches, not food timers.
        if (__OWNED_IDS__.indexOf(String(petItemId)) !== -1) {
            elPanel.SetHasClass('low-food', false);
            elPanel.SetHasClass('needs-food', false);
            return;
        }
'''.replace('__OWNED_IDS__', json.dumps(ids)), 1)


def prepare(directory, config):
    from companions import snapshot
    pets=snapshot(directory)
    pet_id=pets.get('selected','0')
    from pathlib import Path
    icon=whats_new_icon(Path(directory).resolve().parents[1])
    menu=install_override(directory, enabled=True, folder='cs2_gc_mainmenu',
        comment='cs2_gc main-menu promotion', owner='cs2-gc-mainmenu-v1',
        asset='panorama/scripts/mainmenu.vts_c', patch=lambda source: patch(source,bool(config['care_packages_enabled']),bool(config['hide_mainmenu_promo']),pet_id),
        extra=[(WHATS_NEW_ICON, icon)] if icon else ())
    food=install_override(directory, enabled=True, folder='cs2_gc_pet_food',
        comment='cs2_gc permanent companion food hint', owner='cs2-gc-pet-food-v1',
        asset='panorama/scripts/vanity_pet_info.vts_c',
        patch=lambda source: patch_pet_food(source,[pet['id'] for pet in pets.get('pets',[])]))
    watch=install_override(directory, enabled=True, folder='cs2_gc_watch_settings',
        comment='cs2_gc NEW settings placeholder', owner='cs2-gc-watch-settings-v1',
        asset='panorama/scripts/mainmenu_watch.vts_c', patch=patch_watch)
    return menu + '; ' + food + '; ' + watch
