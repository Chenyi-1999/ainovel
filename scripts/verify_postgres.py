"""Run inside API image against disposable ainovel_verify database, not user data."""
import json
import os
import threading
import sys
from concurrent.futures import ThreadPoolExecutor

os.environ['DATABASE_URL'] = os.environ['DATABASE_URL'].rsplit('/', 1)[0] + '/ainovel_verify'
sys.path.insert(0, '/service')
from fastapi.testclient import TestClient
from app import gateway, main, worker
from app.auth import password_hash
from app.db import Chapter, Job, Session, Version
from sqlalchemy import select

os.environ['ADMIN_PASSWORD_HASH'] = password_hash('integration-test-only')

def complete(novel_id, job_id, purpose, prompt, system, max_tokens=1000):
    if purpose == 'outline':
        return json.dumps({'title':'验证作品','synopsis':'侦探寻找失踪的灯塔守望者','volumes':[]}, ensure_ascii=False)
    if purpose == 'write':
        return json.dumps({'title':'灯塔','content':'夜色渐深，灯塔的光照亮海面。他在门前发现一封没有署名的信。'*12}, ensure_ascii=False)
    if purpose == 'audit':
        return json.dumps({'report':'未发现冲突','content':''},ensure_ascii=False)
    if purpose == 'confirm':
        return json.dumps({'memories':[{'kind':'summary','content':'主角在灯塔门前发现匿名信。'}]},ensure_ascii=False)
    raise AssertionError(purpose)

gateway.complete = complete
main.wake_worker = lambda: None

def finish(job):
    claimed = worker.claim_job()
    assert claimed and claimed[0] == job['id']
    worker.run_job(*claimed)
    with Session() as db:
        result = db.get(Job, job['id'])
        assert result.status == 'succeeded', result.error

with TestClient(main.app) as client:
    assert client.get('/api/novels').status_code == 401
    assert client.post('/api/login', json={'password':'integration-test-only'}).status_code == 200
    assert client.post('/api/novels', headers={'Origin':'https://wrong.example'},json={'premise':'测试'}).status_code == 403
    book = client.post('/api/novels', json={'premise':'灯塔与侦探'}).json()
    prefix = '/api/novels/'+book['id']
    finish(client.post(prefix+'/jobs',json={'kind':'outline'}).json())
    finish(client.post(prefix+'/jobs',json={'kind':'write','count':2,'target_words':300}).json())
    chapters = client.get(prefix+'/chapters').json()
    assert len(chapters) == 2
    assert client.get(prefix+'/memories').json() == []
    for chapter in chapters:
        finish(client.post(prefix+'/jobs',json={'kind':'confirm','chapter_id':chapter['id']}).json())
    assert len(client.get(prefix+'/memories').json()) == 2
    chapter = client.get(prefix+'/chapters').json()[0]
    cookies = dict(client.cookies)
    barrier = threading.Barrier(2)
    def edit(value):
        with TestClient(main.app) as other:
            other.cookies.update(cookies)
            barrier.wait(timeout=10)
            return other.patch('/api/chapters/'+chapter['id'],json={'revision':chapter['revision'],'content':value}).status_code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(edit,['修改甲','修改乙']))
    assert sorted(results) == [200,409], results
    changed = client.get(prefix+'/chapters').json()
    assert all(row['memory_dirty'] for row in changed)
    assert all(row['stale'] for row in client.get(prefix+'/memories').json())
    assert len(client.get('/api/chapters/'+chapter['id']+'/versions').json()) == 1
    exported = client.get(prefix+'/export').text
    assert ('修改甲' in exported) != ('修改乙' in exported)
    assert client.delete(prefix).status_code == 200
print('PostgreSQL integration passed: auth, outline, sequential writing, canon, concurrent edit, invalidation, versions, export.')
