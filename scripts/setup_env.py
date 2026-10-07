"""Create private runtime config; never commit generated credentials."""
import argparse
import hashlib
import pathlib
import secrets

parser = argparse.ArgumentParser()
parser.add_argument('--key-file', required=True)
parser.add_argument('--base-url', default='https://agentrouter.org/v1')
parser.add_argument('--model', default='deepseek-v4-flash')
args = parser.parse_args()
root = pathlib.Path(__file__).resolve().parent.parent
target = root / '.env'
if target.exists():
    raise SystemExit('Existing .env preserved. Edit it explicitly for updates.')
key = pathlib.Path(args.key_file).read_text().strip()
password = secrets.token_urlsafe(18)
db_password = secrets.token_hex(24)
salt = secrets.token_hex(16)
digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000).hex()
password_hash = f'pbkdf2_sha256$600000${salt}${digest}'
content = '\n'.join([
    'APP_PORT=18110', 'APP_BIND=0.0.0.0', f'DB_PASSWORD={db_password}',
    f'DATABASE_URL=postgresql+psycopg://ainovel:{db_password}@db:5432/ainovel',
    'REDIS_URL=redis://redis:6379/0', f"ADMIN_PASSWORD_HASH='{password_hash}'",
    f'SESSION_SECRET={secrets.token_hex(32)}', 'COOKIE_SECURE=false',
    f'LLM_BASE_URL={args.base_url}', f'LLM_API_KEY={key}', f'LLM_MODEL={args.model}', ''])
target.write_text(content, encoding='utf-8')
private = root / '.secrets'
private.mkdir(exist_ok=True)
(private / 'login.txt').write_text('纸间登录密码：' + password + '\n访问地址：http://152.136.236.238:18110\n',encoding='utf-8')
print('Runtime configuration created. Login information is in .secrets/login.txt')
