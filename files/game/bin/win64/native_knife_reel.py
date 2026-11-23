"""Show native reels for the Black Market, Gauntlet and standalone Anime cases.

The stock unlock popup (popup_capability_decodable) shows a countdown when the client counts at most one loot list
item, and it collapses an all-knife list into one "rare special item". For our case only, the reel is filled with
real knives sampled by native_finishes.py (cs2_gc_black_market_reel.json); the stop tile still shows the item the
GC actually granted. Anime Case contents use their real portraits and rarity
colours instead of the native agent list's collapsed Rare Special Item.
Every other container keeps the stock behaviour.
"""
import json
from pathlib import Path

from native_resources import install_override, patch_installed_script, vpk_file

FOLDER = 'cs2_gc_reel'
COMMENT = 'cs2_gc black market case reel'
OWNER = 'cs2-gc-knife-reel-v1'
ASSET = 'panorama/scripts/popups/popup_capability_decodable.vjs_c'
ANCHOR = """        if (lootListCount <= 1) {
            _SetUpCaseOpeningCountdown();
        }"""
INSERT = """        if (lootListCount <= 1 && _LocalKnifeReel(caseId)) {
            _SetUpCaseOpeningScroll();
        }
        else if (lootListCount <= 1) {
            _SetUpCaseOpeningCountdown();
        }"""
HELPER = """    // cs2_gc: the knife-only Black Market Case and glove-only Gauntlet Case roll real items (sampled when the
    // cases were generated).
    const m_localKnifeReels = __REEL__;
    function _LocalKnifeReel(caseId) {
        const m_localKnifeReel = m_localKnifeReels[InventoryAPI.GetItemDefinitionName(caseId)] || [];
        if (!m_localKnifeReel.length)
            return false;
        // Like a real case, every reel tile is the gold Rare Special Item; the knife is revealed after the reel.
        const image = InventoryAPI.GetLootListUnusualItemImage(caseId);
        $.GetContextPanel().Data().unusualItemImagePath = (image || 'econ/weapon_cases/default_rare_item') + '.png';
        $.GetContextPanel().Data().localKnifeReel = true;
        $.GetContextPanel().Data().aItemsInLootlist = m_localKnifeReel.map(pair =>
            ({ id: InventoryAPI.GetFauxItemIDFromDefAndPaintIndex(pair[0], pair[1]), weight: 1 }));
        return true;
    }
"""
FUNCTION = '    function _ShowUnlockAnimation() {'
TILE = "        if ((InventoryAPI.GetItemQuality(itemId) === 3) && $.GetContextPanel().Data().unusualItemImagePath) {"
TILE_INSERT = ("        if (($.GetContextPanel().Data().localKnifeReel || InventoryAPI.GetItemQuality(itemId) === 3) &&"
               " $.GetContextPanel().Data().unusualItemImagePath) {")
# Stock code only updates the "comes with all N items" label when count > 1 or every entry is an extra drop, so a
# loot list that collapses to one Rare Special Item tile left it visible over the hint with an empty count.
HINT = "        $.GetContextPanel().FindChildInLayoutFile('CanDecodableDesc').visible = !bAllItems;"
HINT_INSERT = HINT + "\n        $.GetContextPanel().FindChildInLayoutFile('CanDecodableDescMulti').visible = false;"
ANIME_HELPER = """    function _LocalAnimeLoot(caseId) {
        return InventoryAPI.GetItemDefinitionName(caseId) === 'crate_cs2gc_anime'
            ? __AGENTS__.map(definition => InventoryAPI.GetFauxItemIDFromDefAndPaintIndex(definition, 0)) : [];
    }
"""
ANIME_LIST = """    function _SetLootListItems(caseId, keyId) {
        const count = InventoryAPI.GetLootListItemsCount(caseId);"""
ANIME_ITEM = "            const itemid = InventoryAPI.GetLootListItemIdByIndex(caseId, i) === '0' ? specialItemId : InventoryAPI.GetLootListItemIdByIndex(caseId, i);"
ANIME_COUNT = '        const lootListCount = InventoryAPI.GetLootListItemsCount(caseId);'
ANIME_INSPECT = """        $.DispatchEvent("LootlistItemPreview", itemid, caseId +
            ',' + storeid);"""
# The lootlist preview switches to the weapon view, which hides an agent's character panel and leaves a black popup.
ANIME_INSPECT_INSERT = """        if (InventoryAPI.GetDefaultSlot(itemid) === 'customplayer') {
            UiToolkitAPI.ShowCustomLayoutPopup('', 'file://{resources}/layout/popups/popup_inventory_inspect.xml').Data().oSettings =
                { item_id: itemid, inspect_only: true, hide_all_action_items: true, hide_item_cert: true };
            return;
        }
""" + ANIME_INSPECT


def patch(source, reel, keyless=False, agents=()):
    if '_LocalKnifeReel' in source: raise ValueError('Script is already patched')
    if (source.count(ANCHOR) != 1 or source.count(FUNCTION) != 1 or source.count(TILE) != 1
            or '_SetUpCaseOpeningScroll()' not in source):
        raise ValueError('Installed popup_capability_decodable layout has changed; no patch was written')
    if isinstance(reel, list): reel = {'crate_cs2gc_black_market': reel}  # reel file from before the Gauntlet Case
    helper = HELPER.replace('__REEL__', json.dumps({name: [[int(a), int(b)] for a, b in pairs]
                                                   for name, pairs in sorted(reel.items())}, sort_keys=True))
    result = source.replace(ANCHOR, INSERT, 1).replace(FUNCTION, helper + FUNCTION, 1).replace(TILE, TILE_INSERT, 1)
    if result.count(HINT) == 1: result = result.replace(HINT, HINT_INSERT, 1)
    if agents:
        for anchor in (ANIME_LIST, ANIME_ITEM, ANIME_COUNT, ANIME_INSPECT):
            if result.count(anchor) != 1:
                raise ValueError('Installed anime contents/reel anchors changed; no patch written')
        result = result.replace(FUNCTION, ANIME_HELPER.replace('__AGENTS__', json.dumps([int(a) for a in agents])) + FUNCTION, 1)
        result = result.replace(ANIME_LIST, """    function _SetLootListItems(caseId, keyId) {
        const localItems = _LocalAnimeLoot(caseId);
        const count = localItems.length || InventoryAPI.GetLootListItemsCount(caseId);""", 1)
        result = result.replace(ANIME_ITEM, ANIME_ITEM.replace('const itemid = ', 'const itemid = localItems.length ? localItems[i] : '), 1)
        result = result.replace(ANIME_COUNT, '        const lootListCount = _LocalAnimeLoot(caseId).length || InventoryAPI.GetLootListItemsCount(caseId);', 1)
        result = result.replace(ANIME_INSPECT, ANIME_INSPECT_INSERT, 1)
    if keyless:
        anchor = '            const associatedItemCount = InventoryAPI.GetAssociatedItemsCount(caseId);'
        if result.count(anchor) != 1: raise ValueError('Installed unlock key branch changed; no patch written')
        result = result.replace(anchor,"""            // cs2_gc: local free cases use the native keyless opening path; never offer to buy a key.
            const localCase = Number(caseId) > 1000000000000 && Number(caseId) < 2000000000000 &&
                !InventoryAPI.GetItemAttributeValue(caseId, '{uint32}volatile container');
            const associatedItemCount = localCase ? 0 : InventoryAPI.GetAssociatedItemsCount(caseId);""",1)
    return result


def prepare(proxy_directory, config):
    from native_agents import installed_manifest
    manifest = installed_manifest(proxy_directory)
    agents = [entry['definition'] for entry in manifest['agents']] if manifest else []
    extra = []
    if agents:
        original, actual = vpk_file(Path(proxy_directory).resolve().parents[1] / 'csgo/pak01_dir.vpk',
                                   'panorama/scripts/common/iteminfo.vjs_c', aliases=True, with_path=True)
        extra.append((actual, patch_installed_script(original, actual, patch_agent_preview)))
    path = Path(proxy_directory) / 'cs2_gc_black_market_reel.json'
    reel = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    if isinstance(reel, list): reel = {'crate_cs2gc_black_market': reel}
    reel = {name: pairs for name, pairs in reel.items() if pairs}
    return install_override(proxy_directory, enabled=bool(agents) or bool(config.get('free_case_keys', 1)) or (bool(config.get('knife_finishes', 1)) and bool(reel)),
                            folder=FOLDER, comment=COMMENT, owner=OWNER, asset=ASSET,
                            patch=lambda source: patch(source, reel if config.get('knife_finishes', 1) else {}, bool(config.get('free_case_keys', 1)), agents),
                            extra=extra)


def patch_agent_preview(source):
    # Stock vanity settings discard the requested character when its team is Any.
    anchor = '        if (!oSettings.charItemId)\n            oSettings.charItemId = LoadoutAPI.GetItemID(oSettings.team, \'customplayer\');'
    if source.count(anchor) != 1 or '// cs2_gc standalone agent inspect' in source:
        raise ValueError('Installed character preview fallback changed; no patch written')
    return source.replace(anchor, """        // cs2_gc standalone agent inspect: retain a both-team agent in the selected vanity team.
        if (optionalCharacterItemId && InventoryAPI.IsValidItemID(optionalCharacterItemId) &&
            InventoryAPI.GetItemDefinitionName(optionalCharacterItemId).startsWith('customplayer_cs2gc_anime_'))
            oSettings.charItemId = optionalCharacterItemId;
""" + anchor, 1)
