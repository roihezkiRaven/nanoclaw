"""Independent, fixed-command restart/health/rollback for approved maintenance drafts."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from datetime import datetime, timezone


def run(root, args, timeout=30):
    return subprocess.run(args, cwd=root, capture_output=True, text=True, timeout=timeout, check=True)


def save_state(file, plan, state, error=None):
    plan.update(state=state, checked_at=datetime.now(timezone.utc).isoformat(), error=error)
    temporary = file.with_suffix('.tmp')
    with temporary.open('w') as stream:
        os.chmod(temporary, 0o600)
        json.dump(plan, stream)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(file)


def affected_units(plan):
    units = [plan['unit']]
    if any(name.startswith('tools/gdrive_') and not name.endswith('_test.py') for name in plan['candidate']):
        units.append('gdrive-broker.service')
    if any(name in ('tools/whatsapp_collector.ts', 'src/modules/personal-assistant/whatsapp-coverage.ts') for name in plan['candidate']):
        units.append('whatsapp-collector.service')
    return units


def healthy(root, plan):
    for unit in affected_units(plan):
        run(root, ['systemctl', '--user', 'is-active', '--quiet', unit])
    pid = run(root, ['systemctl', '--user', 'show', plan['unit'], '--property=MainPID', '--value']).stdout.strip()
    if not pid.isdigit() or int(pid) in (0, plan['old_pid']):
        raise RuntimeError('host has not restarted')
    response = json.loads(run(root, ['node', 'dist/cli/client.js', 'groups', 'get', plan['group'], '--json'], 8).stdout)
    if response.get('ok') is not True:
        raise RuntimeError('host CLI readiness check failed')
    if 'gdrive-broker.service' in affected_units(plan):
        run(root, [str(root / '.venv-gdrive/bin/python'), 'tools/gdrive_assistant.py', 'reader', 'check'], 15)
    if any(name.endswith('/agy.ts') for name in plan['candidate']):
        run(root, [str(Path.home() / '.local/bin/agy'), 'models'], 30)
    if 'whatsapp-collector.service' in affected_units(plan):
        heartbeat = root / 'store/whatsapp-collector/heartbeat'
        if not heartbeat.exists() or (time.time() - heartbeat.stat().st_mtime > 90 or heartbeat.stat().st_mtime < plan.get('restart_started_epoch', 0)):
            raise RuntimeError('collector heartbeat unavailable')


def restore(root, plan):
    for name, original in plan['baseline'].items():
        file = root / name
        if original is None:
            file.unlink(missing_ok=True)
            if name.startswith('src/') and name.endswith('.ts'):
                built = root / 'dist' / name[4:-3]
                for suffix in ['.js', '.js.map', '.d.ts', '.d.ts.map']:
                    Path(str(built) + suffix).unlink(missing_ok=True)
        else:
            temporary = file.with_suffix(file.suffix + '.rollback')
            temporary.write_bytes(original.encode('utf-8'))
            temporary.replace(file)
    run(root, ['node', 'node_modules/typescript/bin/tsc'], 120)


def wait_healthy(root, plan, attempts=30):
    stable = 0
    for _ in range(attempts):
        try:
            healthy(root, plan)
            stable += 1
            if stable == 3:
                return
        except Exception:
            stable = 0
        time.sleep(3)
    raise RuntimeError('post-restart readiness did not stabilize')


def supervise(root, draft_id):
    directory = root / 'data/.host-change-drafts' / draft_id
    file = directory / 'activation.json'
    plan = json.loads(file.read_text())
    try:
        if plan['state'] != 'built':
            raise RuntimeError('activation is not in built state')
        if any((root / name).read_bytes().decode('utf-8') != content for name, content in plan['candidate'].items()):
            save_state(file, plan, 'conflict', 'Source drift after build; operator review required')
            return
        time.sleep(8)
        plan['restart_started_epoch'] = time.time()
        save_state(file, plan, 'restarting')
        try:
            run(root, ['systemctl', '--user', 'restart', *affected_units(plan)], 60)
            wait_healthy(root, plan)
            save_state(file, plan, 'healthy')
            (directory / 'applied.json').write_text(json.dumps({'checked_at': plan['checked_at'], 'state': 'healthy'}))
        except Exception:
            save_state(file, plan, 'rolling_back', 'Restart or health verification failed')
            restore(root, plan)
            run(root, ['systemctl', '--user', 'restart', *affected_units(plan)], 60)
            wait_healthy(root, plan)
            save_state(file, plan, 'rolled_back', 'Candidate failed health; previous source/build restored and verified')
    except Exception:
        save_state(file, plan, 'failed', 'Activation/recovery could not be verified; operator intervention required')
    finally:
        lock = root / 'data/.host-change-drafts/.activation-lock'
        if lock.exists():
            lock.rmdir()


if __name__ == '__main__':
    root = Path(sys.argv[1]).resolve()
    draft_id = sys.argv[2]
    if not re.fullmatch(r'[a-f0-9-]{36}', draft_id):
        raise SystemExit('Invalid draft id')
    supervise(root, draft_id)
