"""Safe progress actions used by the CS2 GC desktop launcher."""
import argparse
from pathlib import Path
import sys


def run(action, proxy):
    import progress_saves
    with progress_saves.closed(proxy):
        if action == 'backup':
            saved = progress_saves.snapshot(proxy)
            print('Progress backup created:\n' + str(saved))
            return
        if action == 'reset-inventory':
            from reset_profile import reset
            backup, moved = reset(Path(proxy), 'all')
            print('Local inventory and progress reset. Previous files are preserved in:\n' +
                  str(backup) + '\nFiles moved: ' + (', '.join(moved) or 'none'))
            return
        raise ValueError('Unsupported launcher action: ' + action)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'reset-inventory'))
    parser.add_argument('--proxy-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.action, args.proxy_dir)
        return 0
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print('Launcher action stopped: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
