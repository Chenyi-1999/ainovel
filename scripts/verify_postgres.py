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
from app.db import Chapter, Job, Session, Version, engine
from app.migrations import migrate
from sqlalchemy import select

assert engine.url.database == 'ainovel_verify', 'Refuse migration outside the disposable verification database'
migrate(engine)

os.environ['ADMIN_PASSWORD_HASH'] = password_hash('integration-test-only')

def complete(novel_id, job_id, purpose, prompt, system, max_tokens=1000):
    if purpose == 'outline':
        return json.dumps({'title':'验证作品','synopsis':'侦探寻找失踪的灯塔守望者','volumes':[]}, ensure_ascii=False)
    if purpose == 'write':
        return json.dumps({'title':'灯塔','content':'夜色渐深，灯塔的光照亮海面。他在门前发现一封没有署名的信。'*12}, ensure_ascii=False)
    if purpose == 'audit':
        return json.dumps({'report':'未发现冲突','content':''},ensure_ascii=False)
    if purpose == 'confirm':
        return json.dumps({'memories':[{'kind':'summary','content':'主角在灯塔门前发现匿名信。',
            'evidence_quote':'夜色渐深，灯塔的光照亮海面。','visibility':'public'}]},ensure_ascii=False)
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
        extraction = client.post(prefix+'/jobs',json={'kind':'confirm','chapter_id':chapter['id']}).json()
        finish(extraction)
        proposal = client.get('/api/jobs/'+extraction['id']).json()['result']
        assert proposal['applied'] is False
        response = client.post('/api/jobs/'+extraction['id']+'/apply-memory',json={
            'expected_revision':proposal['expected_revision'],'memories':proposal['memory_candidates']})
        assert response.status_code == 200, response.text
    assert len(client.get(prefix+'/memories').json()) == 2
    # Use the same public contracts as the editor, against real PostgreSQL locks.
    memory = client.get(prefix+'/memories').json()[0]
    def create_entity(name):
        response = client.post(prefix+'/entities',json={'name':name,'kind':'character','aliases':[], 'description':'PostgreSQL integration fixture'})
        assert response.status_code == 200, response.text
        return response.json()
    source, target = create_entity('守望者'), create_entity('侦探')
    relation = client.post(prefix+'/relations',json={'source_entity_id':source['id'],'target_entity_id':target['id'],
        'label':'留下线索','description':'引用已审核正文证据','basis':'chapter','memory_id':memory['id']})
    assert relation.status_code == 200, relation.text
    hint = client.post(prefix+'/foreshadows',json={'title':'匿名信的来源','description':'验证引用失效传播','target_chapter':10,
        'events':[{'state':'planted','note':'在正文埋设','basis':'chapter','memory_id':memory['id']}]})
    assert hint.status_code == 200, hint.text
    graph = client.get(prefix+'/graph').json()
    assert len(graph['nodes']) == 2 and len(graph['edges']) == 1
    assert client.delete('/api/entities/'+source['id']).status_code == 409
    assert client.get(prefix+'/graph',params={'before_chapter':1}).json()['edges'] == []

    prompt = client.post('/api/prompts',json={'name':'PG并发模板','category':'创作规划','task_kind':'outline',
        'genre_tags':['悬疑'],'description':'独立测试数据','body':'为{{title}}规划清晰的因果。{{instructions}}',
        'novel_id':book['id'],'enabled':True})
    assert prompt.status_code == 200, prompt.text
    prompt = prompt.json()
    assert client.post('/api/prompts/'+prompt['id']+'/preview',json={'novel_id':book['id'],'instructions':'不要生成正文'}).status_code == 200
    barrier_job = threading.Barrier(2)
    cookies_job = dict(client.cookies)
    job_payload = {'kind':'outline','skill_id':'outline','prompt_template_id':prompt['id'],'idempotency_key':'pg-concurrent-outline'}
    def queue_once(_):
        with TestClient(main.app) as other:
            other.cookies.update(cookies_job)
            barrier_job.wait(timeout=10)
            response = other.post(prefix+'/jobs',json=job_payload)
            assert response.status_code == 200, response.text
            return response.json()
    with ThreadPoolExecutor(2) as pool:
        submitted = list(pool.map(queue_once,[0,1]))
    assert submitted[0]['id'] == submitted[1]['id']
    finish(submitted[0])
    assert client.post(prefix+'/jobs',json=job_payload).json()['id'] == submitted[0]['id']
    assert client.post(prefix+'/jobs',json={**job_payload,'instructions':'同key不同请求'}).status_code == 409

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
    # Both memories are sourced from chapter 1 or 2, so the chapter-1 edit
    # invalidates every dependent graph edge and foreshadow event.
    assert client.get(prefix+'/graph').json()['edges'] == []
    assert client.get(prefix+'/relations').json()[0]['stale'] is True
    assert client.get(prefix+'/foreshadows').json()[0]['needs_review'] is True
    assert len(client.get('/api/chapters/'+chapter['id']+'/versions').json()) == 1
    exported = client.get(prefix+'/export').text
    assert ('修改甲' in exported) != ('修改乙' in exported)
    assert client.delete(prefix).status_code == 200
print('PostgreSQL integration passed: auth, template preview, skill/job idempotency, sequential writing, reviewed canon, relations/foreshadows, concurrent edit, invalidation, versions, export.')
