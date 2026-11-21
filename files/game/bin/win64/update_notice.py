"""Tell the main menu when a newer CSReborn release is published, so players know to reopen the launcher.

The rewards helper starts this once per game session. The answer goes to csgo/cfg/cs2gc_update.cfg, which the main
menu executes and reads back as the cs2gc_update setting ("0" while the install is current). Installing stays the
launcher's job: it applies the update the next time it opens with CS2 closed.
"""
import os
from pathlib import Path
import re
import threading

CFG_NAME = 'cs2gc_update.cfg'
SETTING = 'cs2gc_update'
CURRENT = '0'
CHECK_EVERY = 15 * 60
VERSION = re.compile(r'[0-9][0-9A-Za-z.+-]{0,31}')


def cfg_text(version):
    value = version if version and VERSION.fullmatch(version) else CURRENT
    return 'setinfo %s "%s"\n' % (SETTING, value)


def write(cfg_dir, version):
    path = Path(cfg_dir) / CFG_NAME
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(cfg_text(version), encoding='ascii')
    os.replace(temporary, path)


def check_once(proxy_dir, cfg_dir, opener=None):
    """Write the pending version (or "0"); keep the previous answer when the feed cannot be reached."""
    import launcher_update
    root = Path(proxy_dir).resolve().parents[2]
    try:
        version = launcher_update.pending_update(root, opener)
        write(cfg_dir, version)
    except (OSError, ValueError) as error:
        print('Update notice: check skipped: ' + str(error).splitlines()[0], flush=True)
        return None
    if version:
        print('Update notice: CSReborn ' + version + ' is available; reopen the launcher to install it.', flush=True)
    return version


def start(proxy_dir, cfg_dir, opener=None, interval=CHECK_EVERY):
    """Check now and then every `interval` seconds on a daemon thread; set the returned event to stop."""
    write(cfg_dir, None)  # never show a stale notice for the release that was just installed
    stop = threading.Event()

    def loop():
        while True:
            check_once(proxy_dir, cfg_dir, opener)
            if stop.wait(interval):
                return

    threading.Thread(target=loop, name='cs2gc-update-notice', daemon=True).start()
    return stop
