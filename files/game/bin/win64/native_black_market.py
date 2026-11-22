"""Native home-menu Black Market; the local GC owns all offers and paid transactions."""

BLACK_MARKET = r"""
        function _LocalMarketOpen() {
            const screen = _cs2gcPartyMenu.FindChildTraverse('cs2gc-black-market');
            return screen && screen.IsValid() && !screen.__closing;
        }
        function _LocalMarketClose() {
            const screen = _cs2gcPartyMenu.FindChildTraverse('cs2gc-black-market');
            if (!screen || screen.__closing) return;
            screen.__closing = true;
            if (screen.__timer !== null) $.CancelScheduled(screen.__timer);
            ['cs2gc_market',0,1,2,3,4,5].forEach(key =>
                GameInterfaceAPI.SetSettingString(typeof key === 'number' ? 'cs2gc_market_' + key : key, ''));
            screen.DeleteAsync(0);
        }
        // The panel lives in the former Parties category tab and closes as soon as another tab is selected.
        function _LocalShowBlackMarket(tab) {
            if (!tab || _LocalInMatch() || !m_localMenuVisible || _LocalMarketOpen()) return;
            const previous = _cs2gcPartyMenu.FindChildTraverse('cs2gc-black-market');
            if (previous) return; // deletion is deferred until the end of this frame
            const screen = $.CreatePanel('Panel', tab, 'cs2gc-black-market');
            Object.assign(screen.style, {width:'100%',height:'100%',backgroundColor:'#080b12fa',
                padding:'24px 40px',flowChildren:'down'});
            screen.hittest = true;
            screen.__timer = null;
            const header = $.CreatePanel('Panel', screen, '');
            Object.assign(header.style,{width:'100%',flowChildren:'right',marginBottom:'8px'});
            const title = _LocalWhatsNewLabel(header,'BLACK MARKET','stratum-bold-condensed',40,'#efd9a7');
            title.style.width = 'fill-parent-flow(1)';
            _LocalWhatsNewLabel(screen,'SIX PERSONAL OFFERS  /  30 STARS EACH  /  ONE PURCHASE PER CARD',
                'stratum-bold-condensed',18,'#b8c3d3');
            _LocalWhatsNewLabel(screen,'Reveal your selection. No timer, no refresh, no replacement offers.',
                'stratum-regular',16,'#8e9aad');
            const status = _LocalPartyLabel(screen,'cs2gc-market-status',18,'#efd9a7');
            status.style.marginTop = '8px';
            const content = $.CreatePanel('Panel',screen,'cs2gc-market-content');
            Object.assign(content.style,{width:'100%',height:'fill-parent-flow(1)',flowChildren:'down',overflow:'squish scroll'});
            const row = $.CreatePanel('Panel',content,'cs2gc-market-cards');
            Object.assign(row.style,{width:'100%',height:'416px',flowChildren:'right',marginTop:'12px',marginBottom:'24px'});
            const cards = [];
            let pending = null, ticks = 0, owner = '', sent = false;
            const errors = {unavailable:'Black Market is unavailable. Start this build through the launcher.',
                missing_pool:'The required custom-skin or knife assets are missing. Offers were not changed.',
                invalid_offer:'This offer is no longer valid. Reopen Black Market.',
                not_enough_stars:'You need 30 stars for this offer.',
                not_revealed:'Reveal the card before buying it.',
                missing_item:'This saved skin is unavailable in the current build. No stars were charged.',
                save_failed:'Could not save your inventory. No stars were charged. Check disk access.'};
            function request(token, action) {
                if (pending || !owner || owner !== String(MyPersonaAPI.GetXuid())) return;
                pending = {token:token, action:action, ticks:0, revision:_LocalPartySetting('cs2gc_market').split('|')[3]};
                TournamentsAPI.SetTournamentFavorite(4500000000000000 + token * 16 + action, true);
            }
            for (let slot = 0; slot < 6; slot++) {
                const panel = $.CreatePanel('Panel',row,'cs2gc-market-card-' + slot);
                Object.assign(panel.style,{width:'fill-parent-flow(1)',height:'400px',marginRight:slot===5?'0px':'10px',
                    backgroundColor:'gradient(linear, 0% 0%, 100% 100%, from(#263042), to(#10141e))',
                    border:'1px solid #d7ba793d',borderTop:'3px solid #d7ba79',padding:'14px',
                    transitionProperty:'transform, opacity',transitionDuration:'0.18s'});
                const front = $.CreatePanel('Panel',panel,'');
                Object.assign(front.style,{width:'100%',height:'100%',flowChildren:'down'});
                _LocalWhatsNewLabel(front,'RARE SPECIAL','stratum-bold-condensed',16,'#efd9a7');
                const image = $.CreatePanel('ItemImage',front,'');
                Object.assign(image.style,{width:'100%',height:'180px',verticalAlign:'center'});
                const name = _LocalWhatsNewLabel(front,'','stratum-bold-condensed',21,'#ffffff');
                name.style.height = '70px';
                const detail = _LocalWhatsNewLabel(front,'','stratum-regular',14,'#9daabe');
                detail.style.height = '40px';
                const buy = _LocalPartyButton(front,'cs2gc-market-buy-' + slot,'30 STARS',() => {
                    const data = cards[slot].data;
                    if (data && data.revealed && !data.purchased && buy.enabled) request(data.token,2);
                });
                buy.style.width = '100%'; buy.style.marginRight = '0px';
                const cover = $.CreatePanel('Button',panel,'cs2gc-market-reveal-' + slot);
                Object.assign(cover.style,{width:'100%',height:'100%',flowChildren:'down',padding:'28px 8px',
                    backgroundColor:'gradient(linear, 0% 0%, 100% 100%, from(#363247), to(#0e1724))'});
                const number = _LocalWhatsNewLabel(cover,'0' + (slot+1),'stratum-bold-condensed',70,'#efd9a7');
                Object.assign(number.style,{textAlign:'center',marginTop:'45px',marginBottom:'40px'});
                _LocalWhatsNewLabel(cover,'SEALED OFFER','stratum-bold-condensed',22,'#ffffff').style.textAlign = 'center';
                _LocalWhatsNewLabel(cover,'CLICK TO REVEAL','stratum-regular',14,'#b4c7dc').style.textAlign = 'center';
                cover.Children().forEach(child => child.hittest = false);
                cover.SetPanelEvent('onactivate',() => {
                    const data = cards[slot].data;
                    if (data && !data.revealed && cover.enabled) request(data.token,1);
                });
                front.visible = false; cover.enabled = false;
                cards.push({panel:panel,front:front,cover:cover,image:image,name:name,detail:detail,buy:buy,data:null});
            }
            function tick() {
                screen.__timer = null;
                if (!screen.IsValid() || screen.__closing) return;
                if (!m_localMenuVisible || _LocalInMatch() || !partyNav || !partyNav.checked) { _LocalMarketClose(); return; }
                const self = String(MyPersonaAPI.GetXuid());
                if (owner && owner !== self) { _LocalMarketClose(); return; }
                if (!sent && _LocalAccount(self) && MyPersonaAPI.IsInventoryValid() && MyPersonaAPI.IsConnectedToGC()) {
                    owner = self; sent = true; request(0,0);
                }
                const header = _LocalPartySetting('cs2gc_market').split('|');
                const ready = owner && header.length === 5 && header[0] === owner && /^\d+$/.test(header[1]) &&
                    /^\d+$/.test(header[3]) && header[4] === '6';
                const acknowledged = pending && header[0] === owner && header[3] !== pending.revision;
                let animate = 0;
                if (acknowledged) {
                    if (pending.action === 1 && header[2] === 'ready') animate = pending.token;
                    pending = null;
                }
                let validRows = ready;
                const tokens = new Set();
                const parsed = cards.map((card,slot) => {
                    const f = _LocalPartySetting('cs2gc_market_' + slot).split('|');
                    if (f.length !== 9 || f.some((value,i) => !(i===3?/^(?:0|1)\.\d{6}$/:/^\d+$/).test(value))) {
                        validRows = false; return null;
                    }
                    const [token,def,paint,wear,seed,rarity,unusual,revealed,purchased] = f.map(Number);
                    if (!token || token>4294967295 || tokens.has(token) || def<1 || def>65535 || paint<1 || paint>65535 ||
                        wear>1 || seed<1 || seed>1000 || rarity<5 || rarity>7 || unusual>1 || revealed>1 ||
                        !Number.isSafeInteger(purchased)) validRows = false;
                    tokens.add(token);
                    return {token,def,paint,wear,seed,rarity,unusual,revealed,purchased};
                });
                cards.forEach((card,slot) => {
                    const data = validRows ? parsed[slot] : null;
                    card.data = data;
                    card.buy.enabled = !!data && !!data.revealed && !data.purchased && !pending && Number(header[1])>=30;
                    card.cover.enabled = !!data && !pending;
                    if (!data) { card.front.visible = false; card.cover.visible = true; return; }
                    const id = InventoryAPI.GetFauxItemIDFromDefAndPaintIndex(data.def,data.paint);
                    card.image.itemid = id;
                    card.name.text = _LocalPartyPlain(InventoryAPI.GetItemName(id)) || 'Skin ' + data.def + ' / ' + data.paint;
                    card.detail.text = (data.unusual?'KNIFE':'CUSTOM FINISH') + '  /  SEED ' + data.seed;
                    card.buy.Children()[0].text = data.purchased ? 'PURCHASED' : '30 STARS';
                    card.panel.style.borderTop = '3px solid ' + (data.unusual?'#e4bc6e':'#b98ee5');
                    const reveal = () => {
                        if (!screen.IsValid() || screen.__closing) return;
                        card.front.visible = !!data.revealed; card.cover.visible = !data.revealed;
                        card.panel.style.transform = 'scale3d(1,1,1)';
                    };
                    if (animate === data.token && data.revealed) {
                        card.panel.style.transform = 'scale3d(0.04,1,1)';
                        $.Schedule(0.18,reveal);
                    } else reveal();
                });
                if (pending && ++pending.ticks > 12) {
                    pending = null;
                    status.text = 'No response from the local GC. Reopen Black Market to check the saved result.';
                } else if (pending) status.text = pending.action === 2 ? 'Saving your purchase...' : 'Opening your saved offers...';
                else if (header[0] === owner && errors[header[2]]) status.text = errors[header[2]];
                else if (validRows) status.text = header[1] + ' STARS  /  Your six offers are saved permanently.';
                else status.text = ticks>12 ? 'Waiting for the Black Market bridge. Reopen the launcher if this persists.' : 'Loading your personal offers...';
                ticks++;
                GameInterfaceAPI.ConsoleCommand('exec cs2gc_market');
                screen.__timer = $.Schedule(0.5,tick);
            }
            tick();
        }
"""
