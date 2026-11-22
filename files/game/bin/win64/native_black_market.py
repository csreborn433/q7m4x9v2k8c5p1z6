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
        // Guns use the stock Armory camera for their type (that tile is 260x120). Knives are missing from the stock camera
        // data, so each knife def uses the xpshop_item camera whose frame holds its stock world model with margin.
        const _cs2gcMarketKnifeCameras = {42:'2',59:'2',500:'8',503:'8',505:'2',506:'2',507:'3',508:'8',509:'8',512:'2',
            514:'0',515:'3',516:'4',517:'8',518:'2',519:'2',520:'4',521:'2',522:'2',523:'3',525:'2',526:'0'};
        let _cs2gcMarketGunCameras = null;
        function _LocalMarketCamera(data, id) {
            if (data.unusual) return 'camera_weapon_' + (_cs2gcMarketKnifeCameras[data.def] || '0');
            try {
                if (!_cs2gcMarketGunCameras) _cs2gcMarketGunCameras = JSON.parse(InventoryAPI.GetCameraDataJson()).weapons || [];
                const entry = _cs2gcMarketGunCameras.find(({type}) => type === InventoryAPI.GetItemDefinitionName(id));
                return 'camera_weapon_' + (entry ? entry.camera : '0');
            } catch (error) {
                return 'camera_weapon_0';
            }
        }
        function _LocalMarketWear(wear) {
            return wear < 0.07 ? 'Factory New' : wear < 0.15 ? 'Minimal Wear' : wear < 0.38 ? 'Field-Tested' :
                wear < 0.45 ? 'Well-Worn' : 'Battle-Scarred';
        }
        // The stage is sized from its own layout: knives get a tall viewport, guns the stock tile shape their cameras assume.
        function _LocalMarketFit(card, data) {
            const stage = card.stage;
            const width = Math.round(stage.actuallayoutwidth / (stage.actualuiscale_x || 1)) || 258;
            const stageHeight = Math.round(stage.actuallayoutheight / (stage.actualuiscale_y || 1)) || 300;
            const height = data.unusual ? Math.min(stageHeight, Math.round(width * 1.5)) : Math.round(width * 120 / 260);
            if (Math.abs(card.fit[0] - width) < 3 && Math.abs(card.fit[1] - height) < 3) return;
            card.fit = [width, height];
            card.holder.style.width = width + 'px';
            card.holder.style.height = height + 'px';
        }
        // A revealed offer shows its own 3D model: custom guns have no generated 2D icon and custom knives only a placeholder.
        function _LocalMarketModel(card, data, id) {
            _LocalMarketFit(card, data);
            if (card.modelId === id && (card.model ? card.model.IsValid() : card.failed)) return;
            if (card.model && card.model.IsValid()) card.model.DeleteAsync(0);
            card.model = null; card.failed = false; card.modelId = id;
            let model = null;
            try {
                model = $.CreatePanel('MapItemPreviewPanel', card.holder, 'cs2gc-market-model-' + card.slot + '-' + (++card.models), {
                    'require-composition-layer': 'true', 'transparent-background': true, 'disable-depth-of-field': true,
                    camera: _LocalMarketCamera(data, id), player: 'false', map: 'ui/xpshop_item', initial_entity: 'item',
                    active_item_idx: 0, mouse_rotate: 'false', rotation_limit_x: '0', rotation_limit_y: '0',
                    auto_rotate_x: '0', auto_rotate_y: '0', auto_rotate_period_x: '0', auto_rotate_period_y: '0',
                    auto_recenter: true, hittest: 'false', hide_while_waiting_for_composite_materials: 'false'});
                Object.assign(model.style, {width: '100%', height: '100%'});
                model.hittest = false; model.hittestchildren = false;
                model.SetActiveItem(0); model.SetItemItemId(id, ''); model.SetRenderInterval(10);
                card.model = model; card.image.visible = false;
            } catch (error) {
                if (model && model.IsValid()) model.DeleteAsync(0);
                card.failed = true; card.image.itemid = id; card.image.visible = true;
                $.Msg('[CS2GC Black Market] 3D preview unavailable: ' + error);
            }
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
            Object.assign(row.style,{width:'100%',height:'fill-parent-flow(1)',flowChildren:'right',marginTop:'12px'});
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
                Object.assign(panel.style,{width:'fill-parent-flow(1)',height:'100%',marginRight:slot===5?'0px':'10px',
                    backgroundColor:'gradient(linear, 0% 0%, 100% 100%, from(#263042), to(#10141e))',
                    border:'1px solid #d7ba793d',borderTop:'3px solid #d7ba79',padding:'14px',
                    transitionProperty:'transform, opacity',transitionDuration:'0.18s'});
                const front = $.CreatePanel('Panel',panel,'');
                Object.assign(front.style,{width:'100%',height:'100%',flowChildren:'down'});
                const tag = _LocalWhatsNewLabel(front,'RARE SPECIAL','stratum-bold-condensed',16,'#efd9a7');
                // The stage takes all height the text and button below do not need; the holder inside it is sized by _LocalMarketFit.
                const stage = $.CreatePanel('Panel',front,'cs2gc-market-stage-' + slot);
                Object.assign(stage.style,{width:'100%',height:'fill-parent-flow(1)',marginTop:'8px',marginBottom:'10px',
                    backgroundColor:'#ffffff0a'});
                const holder = $.CreatePanel('Panel',stage,'cs2gc-market-holder-' + slot);
                Object.assign(holder.style,{width:'100%',height:'100%',horizontalAlign:'center',verticalAlign:'center'});
                holder.hittest = false; holder.hittestchildren = false;
                const image = $.CreatePanel('ItemImage',stage,'');
                Object.assign(image.style,{width:'100%',height:'70%',verticalAlign:'center'});
                image.visible = false; // only a fallback when the 3D preview cannot be created
                const weapon = _LocalWhatsNewLabel(front,'','stratum-bold-condensed',15,'#9daabe');
                weapon.style.letterSpacing = '1px';
                const skin = _LocalWhatsNewLabel(front,'','stratum-bold-condensed',23,'#ffffff');
                skin.style.height = '62px';
                const stat = key => {
                    const line = $.CreatePanel('Panel',front,'');
                    Object.assign(line.style,{width:'100%',flowChildren:'right',marginTop:'3px'});
                    _LocalWhatsNewLabel(line,key,'stratum-regular',14,'#8e9aad').style.width = '40%';
                    const value = _LocalWhatsNewLabel(line,'','stratum-bold-condensed',16,'#ffffff');
                    Object.assign(value.style,{width:'60%',textAlign:'right'});
                    return value;
                };
                const wearName = stat('WEAR'), wearFloat = stat('FLOAT'), pattern = stat('PATTERN');
                const inspect = _LocalPartyButton(front,'cs2gc-market-inspect-' + slot,'INSPECT',() => {
                    const data = cards[slot].data;
                    if (!data || !data.revealed || screen.__closing || owner !== String(MyPersonaAPI.GetXuid())) return;
                    const owned = String(data.purchased);
                    const id = data.purchased && Number(InventoryAPI.GetItemDefinitionIndex(owned)) === data.def
                        ? owned : InventoryAPI.GetFauxItemIDFromDefAndPaintIndex(data.def,data.paint);
                    UiToolkitAPI.ShowCustomLayoutPopup('', 'file://{resources}/layout/popups/popup_inventory_inspect.xml')
                        .Data().oSettings = {item_id:id, inspect_only:true, hide_all_action_items:true, hide_item_cert:true};
                });
                Object.assign(inspect.style,{width:'100%',marginRight:'0px',marginTop:'6px'});
                const buy = _LocalPartyButton(front,'cs2gc-market-buy-' + slot,'30 STARS',() => {
                    const data = cards[slot].data;
                    if (data && data.revealed && !data.purchased && buy.enabled) request(data.token,2);
                });
                buy.style.width = '100%'; buy.style.marginRight = '0px'; buy.style.marginTop = '10px';
                const cover = $.CreatePanel('Button',panel,'cs2gc-market-reveal-' + slot);
                Object.assign(cover.style,{width:'100%',height:'100%',flowChildren:'down',padding:'28px 8px',
                    backgroundColor:'gradient(linear, 0% 0%, 100% 100%, from(#363247), to(#0e1724))'});
                const seal = $.CreatePanel('Panel',cover,'');
                Object.assign(seal.style,{width:'100%',height:'fit-children',flowChildren:'down',verticalAlign:'center'});
                const number = _LocalWhatsNewLabel(seal,'0' + (slot+1),'stratum-bold-condensed',70,'#efd9a7');
                Object.assign(number.style,{textAlign:'center',marginBottom:'30px'});
                _LocalWhatsNewLabel(seal,'SEALED OFFER','stratum-bold-condensed',22,'#ffffff').style.textAlign = 'center';
                _LocalWhatsNewLabel(seal,'CLICK TO REVEAL','stratum-regular',14,'#b4c7dc').style.textAlign = 'center';
                seal.hittest = false; seal.hittestchildren = false;
                cover.SetPanelEvent('onactivate',() => {
                    const data = cards[slot].data;
                    if (data && !data.revealed && cover.enabled) request(data.token,1);
                });
                front.visible = false; cover.enabled = false;
                cards.push({slot:slot,panel:panel,front:front,cover:cover,tag:tag,stage:stage,holder:holder,image:image,
                    weapon:weapon,skin:skin,wearName:wearName,wearFloat:wearFloat,pattern:pattern,buy:buy,data:null,
                    fit:[0,0],models:0,model:null,modelId:null,failed:false});
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
                    const full = _LocalPartyPlain(InventoryAPI.GetItemName(id)) || 'Skin ' + data.def + ' / ' + data.paint;
                    const cut = full.indexOf(' | ');
                    card.tag.text = 'RARE SPECIAL  /  ' + (data.unusual?'KNIFE':'CUSTOM FINISH');
                    card.weapon.text = cut > 0 ? full.slice(0,cut) : (data.unusual?'KNIFE':'WEAPON SKIN');
                    card.skin.text = cut > 0 ? full.slice(cut + 3) : full;
                    card.wearName.text = _LocalMarketWear(data.wear);
                    card.wearFloat.text = data.wear.toFixed(4);
                    card.pattern.text = String(data.seed);
                    if (data.revealed) _LocalMarketModel(card,data,id);
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
