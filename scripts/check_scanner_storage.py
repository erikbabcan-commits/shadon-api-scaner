"""Read-only scanner storage gate; never prunes or changes host configuration."""
import argparse
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--path', type=Path, default=Path('/var/lib/docker'))
    args = parser.parse_args()
    try:
        usage = shutil.disk_usage(args.path)
    except OSError:
        print(json.dumps({'status': 'unknown', 'reason': 'storage_unavailable'}))
        return 2
    # A fixed absolute and proportional floor protects small and large disks.
    critical = max(1024 ** 3, usage.total // 20)
    warning = max(2 * 1024 ** 3, usage.total // 10)
    status = 'critical' if usage.free < critical else 'warning' if usage.free < warning else 'ok'
    print(json.dumps({'status': status, 'total_bytes': usage.total,
                      'free_bytes': usage.free, 'critical_floor_bytes': critical,
                      'warning_floor_bytes': warning, 'read_only': True}))
    return 0 if status == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
