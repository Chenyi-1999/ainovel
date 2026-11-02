import { memoryApplication } from './studioPolicy';
import { useEffect, useState } from 'react';
import { Api, Chapter, Entity, Empty, Feedback, Header, Job, Memory, MemoryFields, json, memoryNames, useOperation, useUnsaved } from './shared';
const emptyMemory = (): Partial<Memory> => ({ kind: 'setting', content: '', provenance: 'manual', visibility: 'author_only', known_by_entity_ids: [] });
function CandidateReview({ job, api, chapters, entities, locked, onApplied }: { job: Job; api: Api; chapters: Chapter[]; entities: Entity[]; locked: boolean; onApplied: () => Promise<void> }) {
  const [candidates, setCandidates] = useState<Partial<Memory>[]>(() => (job.result?.memory_candidates || []).map((m: Partial<Memory>) => ({ ...m, visibility: m.visibility || 'unknown' })));
  const [checked, setChecked] = useState<boolean[]>(() => (job.result?.memory_candidates || []).map(() => true));
  const [modified, setModified] = useState(false);
  const { busy, error, run } = useOperation();
  useUnsaved(modified);
  const picked = candidates.filter((_, i) => checked[i]);
  const chapter = chapters.find(c => c.id === (job.result?.chapter_id || job.chapter_id));
  return <article className="studio-review">
    <div className="studio-detail-title">
      <h3>待审核 · 第 {chapter?.number || '?'} 章 {chapter?.title}
      </h3>
      <span className="studio-badge">正文版本 {job.result?.expected_revision}
      </span>
    </div>
    <p className="muted">模型只提出候选。请核对原句与知情范围，至少保留一条章节摘要；采纳后才会更新记忆并确认该章节。</p>
    <Feedback busy={busy} error={error} />{candidates.map((m, i) =>
      <div className="studio-candidate" key={i}>
        <label className="studio-check">
          <input
            type="checkbox"
            checked={checked[i]}
            disabled={busy || locked}
            onChange={e => {
              setChecked(xs => xs.map((x, index) => index === i ? e.target.checked : x));
              setModified(true);
            }} />采纳这条{m.kind === 'summary' ? '章节摘要' : '记忆'}
        </label>
        <fieldset className="studio-fields" disabled={!checked[i] || busy || locked}>
          <MemoryFields
            value={m}
            entities={entities}
            onChange={value => {
              setCandidates(xs => xs.map((x, index) => index === i ? value : x));
              setModified(true);
            }} />
          <label>正文证据原句<textarea
            rows={2}
            value={m.evidence_quote || ''}
            onChange={e => {
              setCandidates(xs => xs.map((x, index) => index === i ? { ...x, evidence_quote: e.target.value } : x));
              setModified(true);
            }} />
          </label>
        </fieldset>
      </div>
    )}
    <button
      className="button primary"
      disabled={busy || locked || !picked.length || !picked.some(m => m.kind === 'summary') || picked.some(m => !m.content?.trim() || !m.evidence_quote?.trim())}
      onClick={() => run(async () => {
        await api(`/jobs/${job.id}/apply-memory`, { method: 'POST', ...json(memoryApplication(job.result.expected_revision, picked)) });
        setModified(false);
        await onApplied();
      })}>采纳所选记忆并确认章节</button>{!picked.some(m => m.kind === 'summary') && <p className="studio-error">必须勾选至少一条章节摘要。</p>
    }
  </article>;
}
export default function MemoryStudio({ api, novelId, memories, jobs, chapters, locked, onRefresh }: { api: Api; novelId: string; memories: Memory[]; jobs: Job[]; chapters: Chapter[]; locked: boolean; onRefresh: () => Promise<void> }) {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [draft, setDraft] = useState<Partial<Memory> | null>(null);
  const [original, setOriginal] = useState('');
  const [filter, setFilter] = useState('active');
  const [search, setSearch] = useState('');
  const { busy, error, run } = useOperation();
  const dirty = draft !== null && JSON.stringify(draft) !== original;
  useUnsaved(dirty);
  useEffect(() => {
    run(async () => setEntities(await api<Entity[]>(`/novels/${novelId}/entities`)));
  }, [novelId]);
  const select = (m: Partial<Memory>) => {
    if (dirty && !window.confirm('放弃这条记忆的未保存修改？')) return;
    setDraft({ ...m });
    setOriginal(JSON.stringify(m));
  };
  const pending = jobs.filter(j => j.kind === 'confirm' && j.status === 'succeeded' && j.result?.memory_candidates && !j.result?.applied);
  const visible = memories.filter(m => (filter === 'all' || (filter === 'stale' ? m.stale : !m.stale)) && (!search || `${m.content} ${m.evidence_quote || ''}`.includes(search)));
  return <section className="section-card studio">
    <Header title="故事记忆" text="保存人物与情节事实，逐条保留来源。知情标注用于整理与保守筛选上下文。">
      <button className="button outline small" disabled={busy} onClick={() => run(onRefresh)}>刷新</button>
      <button className="button primary small" disabled={locked} onClick={() => select(emptyMemory())}>新增作者设定</button>
    </Header>
    <Feedback busy={busy} error={error} />{pending.length > 0 && <div className="studio-review-list">
      <h3>待审核的提取结果 · {pending.length}
      </h3>{pending.map(j =>
        <CandidateReview
          key={j.id}
          job={j}
          api={api}
          chapters={chapters}
          entities={entities}
          locked={locked}
          onApplied={onRefresh} />
      )}
    </div>
    }
    <div className="studio-filters">
      <input
        aria-label="搜索记忆"
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="搜索内容与证据" />
      <select aria-label="记忆状态" value={filter} onChange={e => setFilter(e.target.value)}>
        <option value="active">有效记忆</option>
        <option value="stale">已过期 / 已移除</option>
        <option value="all">全部记忆</option>
      </select>
    </div>
    <div className="studio-split">
      <div className="studio-list">{visible.map(m =>
        <button
          key={m.id}
          className={`studio-list-item ${draft?.id === m.id ? 'active' : ''}`}
          onClick={() => select(m)}>
          <span className="studio-item-title">
            <b>{memoryNames[m.kind] || m.kind}
            </b>
            <small>{m.stale ? '已过期' : m.provenance === 'legacy' ? '历史迁移 · 无可靠证据' : m.provenance === 'manual' ? '手动设定' : '正文提取'}
            </small>
          </span>
          <span>{m.content}
          </span>
          <small>{m.source_chapter_id ? `第 ${chapters.find(c => c.id === m.source_chapter_id)?.number || '?'} 章 · 来源版本 ${m.source_revision || '未知'}` : '作者设定 · 无章节来源'}
          </small>
        </button>
      )}{!visible.length && <Empty>暂无符合条件的记忆。可手动补充，或从章节提取候选后审核。</Empty>
        }
      </div>{draft ?
        <form
          className="studio-detail studio-fields"
          onSubmit={e => {
            e.preventDefault();
            run(async () => {
              await api(draft.id ? `/memories/${draft.id}` : `/novels/${novelId}/memories`, { method: draft.id ? 'PATCH' : 'POST', ...json({ ...draft, provenance: 'manual' }) });
              setDraft(null);
              setOriginal('');
              await onRefresh();
            });
          }}>
          <div className="studio-detail-title">
            <h3>{draft.id ? '编辑记忆' : '新增作者设定'}
            </h3>
            <span className="studio-badge">{dirty ? '未保存' : `版本 ${draft.revision || 1}`}
            </span>
          </div>
          <fieldset className="studio-fields" disabled={busy || locked || draft.stale}>
            <MemoryFields value={draft} onChange={setDraft} entities={entities} />{draft.source_chapter_id && <>
              <p className="muted">来源：第 {chapters.find(c => c.id === draft.source_chapter_id)?.number || '?'} 章 · 正文版本 {draft.source_revision || '未知'}
              </p>
              <label>来源原句<textarea
                rows={3}
                value={draft.evidence_quote || ''}
                onChange={e => setDraft({ ...draft, evidence_quote: e.target.value })} />
              </label>
            </>}{draft.provenance === 'legacy' && <p className="studio-callout">这条记录来自历史数据，缺少可靠的来源版本或原句，不作为已核验正文事实自动使用。</p>
            }
            <div className="studio-actions">
              <button className="button primary small" disabled={!draft.content?.trim() || !dirty}>保存记忆</button>{draft.id && <button
                type="button"
                className="button outline small danger-text"
                onClick={() => {
                  if (window.confirm('移除这条记忆？记录与引用会保留并标记过期。')) run(async () => {
                    await api(`/memories/${draft.id}`, { method: 'DELETE' });
                    setDraft(null);
                    await onRefresh();
                  });
                }}>移除记忆</button>
              }
            </div>
          </fieldset>{draft.stale && <p className="studio-callout">来源已变化或记录已移除。请重新提取审核，或新增修正后的作者设定。</p>
          }
        </form>
        :
        <Empty>选择记忆查看来源与知情范围。</Empty>
      }
    </div>
  </section>;
}
