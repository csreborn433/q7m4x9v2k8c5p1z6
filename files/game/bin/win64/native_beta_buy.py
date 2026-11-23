"""Retire the beta buy HUD that releases up to 1.0.8 could mount.

The option and its layout override are gone. Preparation only unmounts the owned
cs2_gc_beta_buy folder an earlier launch may have added, so the stock buy menu returns.
"""
from native_resources import install_override


def remove(directory):
    return install_override(directory, enabled=False, folder='cs2_gc_beta_buy', comment='cs2_gc beta buy HUD',
                            owner='cs2-gc-beta-buy-v1', asset='panorama/layout/buymenu.vxml_c',
                            patch=lambda resource: resource, compiled_layout=True)


def remove_classic(directory):
    return install_override(directory, enabled=False, folder='cs2_gc_classic_wheel',
                            comment='cs2_gc classic buy wheel', owner='cs2-gc-classic-wheel-v1',
                            asset='panorama/layout/buymenu.vxml_c', patch=lambda data: data, compiled_layout=True)
