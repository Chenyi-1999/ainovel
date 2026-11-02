"""Exercise renewal versus takeover on real PostgreSQL, without model calls."""
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

os.environ['DATABASE_URL'] = os.environ['DATABASE_URL'].rsplit('/', 1)[0] + '/ainovel_verify'
sys.path.insert(0, '/service')
from app import worker
from app.db import Job, Novel, Session, engine, now, uid
from sqlalchemy import delete, select

assert engine.url.database == 'ainovel_verify', 'Refuse verification outside disposable database'

with Session() as db:
    assert not db.scalar(select(Job.id).where(Job.status.in_(['pending', 'running'])))
    novel = Novel(title='字数续租并发验证', premise='仅测试执行权，不调用模型')
    db.add(novel)
    db.flush()
    novel_id = novel.id
    job = Job(novel_id=novel_id, kind='write', count=1, current=0, payload={'target_words':300},
              status='running', owner_token=uid(), lease_until=now() - timedelta(minutes=1))
    db.add(job)
    db.commit()
    job_id, original_token = job.id, job.owner_token
    db.expunge(job)

try:
    # Renewal prevents a subsequent claimant from taking the same execution.
    worker.checkpoint(job)
    assert worker.claim_job() is None
    with Session() as db:
        live = db.get(Job, job_id)
        assert live.owner_token == original_token and live.lease_until > now() + timedelta(minutes=9)
        live.lease_until = now() - timedelta(minutes=1)
        db.commit()
    # Race the locking renewal and SKIP LOCKED recovery. Exactly one owner wins.
    barrier = threading.Barrier(2)
    def renew():
        barrier.wait(timeout=10)
        try:
            worker.checkpoint(job)
            return 'renewed'
        except worker.Superseded:
            return 'superseded'
    def recover():
        barrier.wait(timeout=10)
        return worker.claim_job()
    with ThreadPoolExecutor(2) as pool:
        renewed, recovered = pool.submit(renew), pool.submit(recover)
        outcome, claimed = renewed.result(timeout=20), recovered.result(timeout=20)
    with Session() as db:
        live = db.get(Job, job_id)
        assert live.status == 'running' and live.lease_until > now() + timedelta(minutes=9)
        if claimed is None:
            assert outcome == 'renewed' and live.owner_token == original_token
        else:
            assert claimed[0] == job_id and claimed[1] == live.owner_token != original_token
            assert outcome == 'superseded'
        live.lease_until = now() - timedelta(minutes=1)
        db.commit()
    # An already replaced owner can neither renew nor pass the final save fence.
    claimed = worker.claim_job()
    assert claimed and claimed[0] == job_id
    try:
        worker.checkpoint(job)
    except worker.Superseded:
        pass
    else:
        raise AssertionError('Old owner renewed a recovered execution')
    with Session() as db:
        try:
            worker.lock_job(db, job_id, original_token)
        except worker.Superseded:
            pass
        else:
            raise AssertionError('Old owner passed the final save fence')
    print('PostgreSQL lease verification passed: renewal, concurrent takeover, stale-owner fencing; no model calls.')
finally:
    with Session() as db:
        db.execute(delete(Job).where(Job.id == job_id))
        db.execute(delete(Novel).where(Novel.id == novel_id))
        db.commit()
