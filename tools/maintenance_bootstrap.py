"""Operator-only initial rollout. Run only after explicit approval of the manifest digest."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_release(release, root, approved_digest):
    root = root.resolve()
    raw = (release / 'manifest.json').read_bytes()
    if digest(raw) != approved_digest:
        raise RuntimeError('Manifest does not match the approved digest')
    manifest = json.loads(raw)
    for name, expected in manifest['artifacts'].items():
        if digest((release / name).read_bytes()) != expected:
            raise RuntimeError(f'Review artifact drift: {name}')
    for name, item in manifest['files'].items():
        if name.startswith('/') or '..' in Path(name).parts or name.startswith(('config/', 'store/', 'data/')) or name == '.env':
            raise RuntimeError('Forbidden bootstrap target')
        target = root / name
        if target.resolve() != target.absolute():
            raise RuntimeError(f'Symlink target rejected: {name}')
        current = digest(target.read_bytes()) if target.exists() else None
        if current != item['baseline_sha256']:
            raise RuntimeError(f'Production source drift: {name}')
        if digest((release / 'payload' / name).read_bytes()) != item['sha256']:
            raise RuntimeError(f'Candidate source drift: {name}')
    return manifest


def command(root, args, timeout=120):
    return subprocess.run(args, cwd=root, check=True, capture_output=True, text=True, timeout=timeout)


def install(release, root, approved_digest):
    manifest = verify_release(release, root, approved_digest)
    directory = root / 'data/.host-change-drafts' / manifest['id']
    lock = directory.parent / '.activation-lock'
    handed_off = False
    mutated = False
    baseline = {name: (root / name).read_bytes().decode('utf-8') if (root / name).exists() else None for name in manifest['files']}
    candidate = {name: (release / 'payload' / name).read_bytes().decode('utf-8') for name in manifest['files']}
    if directory.exists():
        raise RuntimeError('Bootstrap already attempted; inspect its activation state before retrying')
    pid = int(command(root, ['systemctl', '--user', 'show', manifest['unit'], '--property=MainPID', '--value']).stdout.strip())
    plan = {'state': 'approved', 'unit': manifest['unit'], 'group': manifest['group'], 'old_pid': pid,
            'baseline': baseline, 'candidate': candidate, 'checked_at': datetime.now(timezone.utc).isoformat()}
    activation = directory / 'activation.json'
    lock.mkdir()
    try:
        directory.mkdir(mode=0o700)
        activation.write_text(json.dumps(plan)); activation.chmod(0o600)
        # Revoke only the superseded pending cancellation draft named in this approval.
        with sqlite3.connect(root / 'data/v2.db') as db:
            old = db.execute('SELECT status FROM pending_approvals WHERE approval_id=?', (manifest['superseded_approval'],)).fetchone()
            if old and old[0] != 'pending':
                raise RuntimeError('Superseded approval is already executing; stop and revalidate')
            db.execute('DELETE FROM pending_approvals WHERE approval_id=? AND status=?', (manifest['superseded_approval'], 'pending'))
        for name, source in candidate.items():
            mutated = True
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + '.bootstrap')
            temporary.write_bytes(source.encode('utf-8'))
            if target.exists():
                temporary.chmod(target.stat().st_mode & 0o777)
            temporary.replace(target)
        command(root, ['node', 'node_modules/typescript/bin/tsc'])
        plan['state'] = 'built'
        activation.write_text(json.dumps(plan))
        draft = {'group': manifest['group'], 'summary': manifest['summary'], 'diff': (release / 'full.diff').read_text(),
                 'digest': approved_digest, 'files': candidate, 'baseline': baseline, 'tests': manifest['tests']}
        (directory / 'draft.json').write_text(json.dumps(draft)); (directory / 'draft.json').chmod(0o600)
        command(root, ['systemd-run', '--user', '--collect', '--unit', f"pa-maintenance-{manifest['id']}", '--property=Type=exec',
                       'python3', str(root / 'tools/maintenance_supervisor.py'), str(root), manifest['id']])
        handed_off = True
        print(json.dumps({'id': manifest['id'], 'state': 'built', 'healthy': False, 'approval_digest': approved_digest}))
    except Exception:
        spec = importlib.util.spec_from_file_location('maintenance_supervisor', release / 'payload/tools/maintenance_supervisor.py')
        supervisor = importlib.util.module_from_spec(spec); spec.loader.exec_module(supervisor)
        if mutated:
            try:
                supervisor.restore(root, plan)
                supervisor.save_state(activation, plan, 'rolled_back', 'Bootstrap build/start failed; previous source/build restored')
            except Exception:
                supervisor.save_state(activation, plan, 'failed', 'Bootstrap recovery failed; operator intervention required')
        else:
            supervisor.save_state(activation, plan, 'conflict', 'Bootstrap stopped before source mutation; revalidate source/approvals')
        raise
    finally:
        if not handed_off:
            lock.rmdir()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest-digest', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    release = Path(__file__).resolve().parent
    root = Path('/home/assistant/nanoclaw')
    if args.apply:
        install(release, root, args.manifest_digest)
    else:
        manifest = verify_release(release, root, args.manifest_digest)
        print(json.dumps({'verified': True, 'files': len(manifest['files']), 'production_modified': False}))
