"""Local player directory, party follow fallback and recent pulls in the home menu."""

SOCIAL_MENU = r"""
        function _LocalAccount(id) {
            return /^76561\d{12}$/.test(id) && id > '76561197960265728' && id <= '76561202255233023';
        }
        function _LocalFollowOffer() {
            const raw = _LocalPartySetting('cs2gc_follow');
            const match = /^(\d{17,20})\|(\d{17})\|(\d{1,20})\|((?:\d{1,3}\.){3}\d{1,3}):27015$/.exec(raw);
            if (!match || !_LocalAccount(match[2])) return null;
            const octets = match[4].split('.').map(Number);
            if (octets.some((n,i) => n > 255 || String(n) !== match[4].split('.')[i]) ||
                !octets[0] || octets[0] === 127 || octets[0] >= 224) return null;
            const session = _LocalPartySession();
            if (!session || !session.members || LobbyAPI.BIsHost()) return null;
            const members = session.members;
            for (let i = 0; i < Math.min(Number(members.numPlayers), 64); i++) {
                const machine = members['machine' + i];
                if (machine && machine.player0 && String(machine.player0.xuid) === match[2])
                    return {key:raw, address:match[4] + ':27015'};
            }
            return null;
        }
        function _LocalShowPlayers() {
            if (_LocalInMatch() || _cs2gcPartyMenu.FindChildTraverse('cs2gc-players')) return;
            const screen = $.CreatePanel('Panel', _cs2gcPartyMenu, 'cs2gc-players');
            Object.assign(screen.style, {width:'100%', height:'100%', backgroundColor:'#000000b0', zIndex:'1000'});
            screen.hittest = true;
            const card = $.CreatePanel('Panel', screen, '');
            Object.assign(card.style, {width:'680px', height:'72%', flowChildren:'down', padding:'24px',
                horizontalAlign:'center', verticalAlign:'center', backgroundColor:'#15181dfa'});
            _LocalWhatsNewLabel(card,'LEADERBOARDS','stratum-bold-condensed',32,'#ffffff');
            _LocalWhatsNewLabel(card,'Steam profiles discovered on this device, newest discoveries first. ' +
                'Open a profile to add a friend. This is not a global ranking.','stratum-regular',16,'#aeb6c2');
            const list = $.CreatePanel('Panel', card, 'cs2gc-players-list');
            Object.assign(list.style,{width:'100%',height:'fill-parent-flow(1)',flowChildren:'down',overflow:'squish scroll'});
            const status = _LocalPartyLabel(card,'cs2gc-players-status',16,'#aeb6c2');
            const actions = $.CreatePanel('Panel', card, '');
            actions.style.flowChildren = 'right';
            let page = 0, signature = null, timer = null, ticks = 0;
            const request = n => {
                page = n; signature = null; ticks = 0;
                list.RemoveAndDeleteChildren(); status.text = 'Loading saved profiles...';
                $.Msg('CS2GC_PARTY players ' + page);
            };
            const back = _LocalPartyButton(actions,'cs2gc-players-back','PREVIOUS',() => request(page - 1));
            const more = _LocalPartyButton(actions,'cs2gc-players-next','NEXT',() => request(page + 1));
            function close() {
                if (timer !== null) $.CancelScheduled(timer);
                for (let i=0;i<8;i++) GameInterfaceAPI.SetSettingString('cs2gc_player_' + i,'');
                GameInterfaceAPI.SetSettingString('cs2gc_players_page','');
                screen.DeleteAsync(0);
            }
            _LocalPartyButton(actions,'cs2gc-players-close','CLOSE',close);
            function tick() {
                timer = null;
                if (!screen.IsValid()) return;
                if (!m_localMenuVisible || _LocalInMatch()) { close(); return; }
                const header = _LocalPartySetting('cs2gc_players_page').split('|');
                const total = Number(header[2]);
                const self = String(MyPersonaAPI.GetXuid());
                const ready = _LocalAccount(self) && header.length === 3 && header[0] === self &&
                    header[1] === String(page) && Number.isInteger(total) && total >= 0 && total <= 48;
                back.enabled = page > 0;
                more.enabled = ready && (page + 1) * 8 < total;
                if (ready) {
                    const rows = Array.from({length:Math.min(8, Math.max(0,total-page*8))}, (_,i) =>
                        _LocalPartySetting('cs2gc_player_' + i));
                    const key = JSON.stringify([page,total,rows]);
                    if (key !== signature) {
                        signature = key; list.RemoveAndDeleteChildren();
                        rows.forEach((row,i) => {
                            const [id,hex] = row.split('|');
                            if (!_LocalAccount(id)) return;
                            const name = _LocalPartyText(hex).replace(/^#+/,'') || id;
                            const btn = _LocalPartyButton(list,'cs2gc-player-' + i,name + (id===self?' (YOU)':''),
                                () => SteamOverlayAPI.OpenUrlInOverlayOrExternalBrowser('https://steamcommunity.com/profiles/' + id));
                            btn.style.marginTop = '6px'; btn.style.width = '100%';
                        });
                        status.text = total ? total + ' saved profiles  ·  Page ' + (page+1) + ' / ' + Math.ceil(total/8)
                            : 'No players discovered yet. Browse or host a party.';
                    }
                } else if (ticks > 6) status.text = 'Player directory unavailable. Launch the mod with Steam online.';
                if (ticks % 10 === 0) $.Msg('CS2GC_PARTY refresh');
                ticks++;
                GameInterfaceAPI.ConsoleCommand('exec cs2gc_players');
                timer = $.Schedule(1,tick);
            }
            request(0); tick();
        }
        function _LocalRecentPulls(home) {
            let box = _cs2gcPartyMenu.FindChildTraverse('cs2gc-home-pulls');
            if (!home.checked) { if (box) box.visible = false; return; }
            if (!box) {
                box = $.CreatePanel('Panel', _cs2gcPartyMenu, 'cs2gc-home-pulls');
                Object.assign(box.style,{width:'24%',maxWidth:'340px',flowChildren:'down',padding:'12px',
                    horizontalAlign:'right',verticalAlign:'center',marginRight:'22px',backgroundColor:'#171e25e8',
                    borderRadius:'4px'});
                box.hittest = false; box.hittestchildren = false;
                _LocalWhatsNewLabel(box,'RECENTLY UNBOXED','stratum-bold-condensed',22,'#ffffff');
                box.rows = $.CreatePanel('Panel',box,'cs2gc-home-pull-list');
                box.rows.style.flowChildren = 'down'; box.rows.style.width = '100%';
            }
            box.visible = true;
            const total = _LocalPartySetting('cs2gc_openings');
            const rows = [0,1,2,3].map(i => _LocalPartySetting('cs2gc_pull_' + i));
            const key = JSON.stringify([total,rows,MyPersonaAPI.IsInventoryValid()]);
            if (box.__cs2gcPullKey !== key) {
                box.__cs2gcPullKey = key; box.rows.RemoveAndDeleteChildren();
                let shown = 0;
                rows.forEach(row => {
                    const f = row.split('|');
                    if (f.length !== 11 || f.some((v,i) => !(i===3?/^(?:0|1)\.\d{6}$/:/^\d+$/).test(v))) return;
                    const [id,def,paint,wear,seed,st,rarity,source,sticker,music,charm] = f;
                    let imageId = '', name = '';
                    if (MyPersonaAPI.IsInventoryValid()) {
                        imageId = Number(InventoryAPI.GetItemDefinitionIndex(id)) === Number(def) ? id :
                            InventoryAPI.GetFauxItemIDFromDefAndPaintIndex(Number(def),Number(paint));
                        if (imageId) name = InventoryAPI.GetItemName(imageId);
                    }
                    if (imageId !== id) {
                        if (+sticker) name = 'Sticker #' + sticker;
                        else if (+music) name = 'Music kit #' + music;
                        else if (+charm) name = 'Charm #' + charm;
                    }
                    name = _LocalPartyPlain(name) || 'Item ' + def;
                    if (+st && name.indexOf('StatTrak') < 0) name = 'StatTrak™ ' + name;
                    const tile = $.CreatePanel('Panel',box.rows,'');
                    Object.assign(tile.style,{width:'100%',flowChildren:'right',marginTop:'6px'});
                    const image = $.CreatePanel('ItemImage',tile,'');
                    if (imageId) image.itemid = imageId;
                    Object.assign(image.style,{width:'58px',height:'44px',marginRight:'6px'});
                    const text = $.CreatePanel('Panel',tile,'');
                    Object.assign(text.style,{width:'fill-parent-flow(1)',flowChildren:'down'});
                    const colors = ['#a7b1b9','#b0c3d9','#5e98d9','#8090ff','#b580ff','#e68aea','#ff7777','#e4ae39','#d7bc68'];
                    _LocalWhatsNewLabel(text,name,'stratum-bold',15,colors[Number(rarity)] || colors[0]);
                    _LocalWhatsNewLabel(text,(+source?'Armory':'Container') + (+paint?'  ·  Float '+wear+'  ·  Seed '+seed:''),
                        'stratum-regular',13,'#b4bec8');
                    shown++;
                });
                if (!shown) _LocalWhatsNewLabel(box.rows,total==='0'?'Your next opening will appear here.':
                    total==='unavailable'?'Opening history is unavailable.':'Waiting for your inventory...','stratum-regular',14,'#aeb6c2');
            }
            GameInterfaceAPI.ConsoleCommand('exec cs2gc_openings');
        }
        function _LocalSocialTick() {
            const home = _cs2gcPartyMenu.FindChildInLayoutFile('MainMenuNavBarHome');
            if (home) _LocalRecentPulls(home);
            if (partyNav && partyNav.checked && _LocalPartySession() && !LobbyAPI.BIsHost())
                GameInterfaceAPI.ConsoleCommand('exec cs2gc_follow');
        }
"""
