"""Create fresh evaluation login secrets, never model API configuration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parent / 'private')
    args = parser.parse_args()
    target = args.directory
    names = ['runtime.env', 'auth.json', 'access.json']
    if any((target / name).exists() for name in names):
        raise SystemExit('Existing evaluation credentials preserved; no files changed.')
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    password = secrets.token_urlsafe(18)
    salt = secrets.token_bytes(24)
    auth = {'username': 'viewer', 'password_salt': salt.hex(),
            'password_hash': hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200000).hex(),
            'session_secret': secrets.token_hex(32)}
    runtime = {'MUMU_DB_PASSWORD': secrets.token_hex(24), 'MUMU_ADMIN_PASSWORD': password,
               'MUMU_SESSION_SECRET': secrets.token_hex(32), 'LITE_ADMIN_USER': 'lab-admin',
               'LITE_ADMIN_PASSWORD': password, 'LITE_SESSION_SIGNING_KEY': secrets.token_hex(32)}
    access = {'gateway_user': 'viewer', 'gateway_password': password, 'mumu_user': 'admin',
              'mumu_password': password, 'lite_user': 'lab-admin', 'lite_password': password,
              'urls': {name: f'http://188.68.41.4:{port}' for name, port in
                       [('mumu', 18020), ('lite', 18021), ('story', 18022), ('cli', 18023)]}}
    content = {'runtime.env': ''.join(key + '=' + value + '\n' for key, value in runtime.items()),
               'auth.json': json.dumps(auth, indent=2), 'access.json': json.dumps(access, indent=2)}
    for name, value in content.items():
        fd = os.open(target / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(value + ('\n' if not value.endswith('\n') else ''))
    # Only the internal unprivileged auth container mounts this individual file.
    # Parent directory remains private; no other application mounts it.
    (target / 'auth.json').chmod(0o644)
    print(f'Private evaluation login files created in {target}; no model configuration added.')


if __name__ == '__main__':
    main()
