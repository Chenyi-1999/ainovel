import { appendEvent, memoryAtRevision } from './studioPolicy';
import { useEffect, useState } from 'react';
import { Api, Empty, Feedback, Header, Memory, json, useOperation, useUnsaved } from './shared';
type Event = { id?: string; state: string; note: string; memory_id: string | null; basis: string; stale?: boolean; memory_revision?: number | null };
type Foreshadow = { id?: string; title: string; description: string; target_chapter: number | null; events: Event[]; revision?: number; status?: string; needs_review?: boolean };
const states: Record<string, string> = { planned: '计划中', planted: '已埋设', progressing: '推进中', resolved: '已回收', abandoned: '已放弃' };
export default function ForeshadowStudio({ api, novelId, memories, locked }: { api: Api; novelId: string; memories: Memory[]; locked: boolean }) {
  const [items, setItems] = useState<Foreshadow[]>([]);
  const [draft, setDraft] = useState<Foreshadow | null>(null);
  const [original, setOriginal] = useState('');
  const [filter, setFilter] = useState('');
  const [event, setEvent] = useState<Event>({ state: 'planted', note: '', memory_id: null, basis: 'author' });
  const { busy, error, run } = useOperation();
  const dirty = !!draft && (JSON.stringify(draft) !== original || !!event.note.trim());
  useUnsaved(dirty);
  const load = async () => {
    const rows = await api<Foreshadow[]>(`/novels/${novelId}/foreshadows`);
    setItems(rows);
    return rows;
  };
  useEffect(() => {
    run(async () => {
      await load();
    });
  }, [novelId]);
  const choose = (value: Foreshadow) => {
    if (dirty && !window.confirm('放弃当前伏笔的未保存修改？')) return;
    setDraft({ ...value });
    setOriginal(JSON.stringify(value));
    setEvent({ state: 'planted', note: '', memory_id: null, basis: 'author' });
  };
  const evidence = memories.filter(m => !m.stale && m.provenance !== 'legacy' && m.source_chapter_id && m.evidence_quote);
  return <section className="section-card studio">
    <Header title="伏笔台账" text="先记录计划，再追加埋设、推进与回收事件。旧事件保留，修正请追加说明。">
      <button
        className="button outline small"
        disabled={busy}
        onClick={() => {
          if (dirty && !window.confirm('重新载入会放弃未保存修改，继续？')) return;
          run(async () => {
            const rows = await load();
            const fresh = rows.find(x => x.id === draft?.id);
            if (fresh) {
              setDraft(fresh);
              setOriginal(JSON.stringify(fresh));
              setEvent({ state: 'planted', note: '', memory_id: null, basis: 'author' });
            }
          });
        }}>重新载入</button>
      <button
        className="button primary small"
        disabled={locked}
        onClick={() => choose({ title: '', description: '', target_chapter: null, events: [] })}>新建伏笔计划</button>
    </Header>
    <Feedback busy={busy} error={error} />
    <div className="studio-filters">
      <select aria-label="伏笔状态筛选" value={filter} onChange={e => setFilter(e.target.value)}>
        <option value="">全部状态</option>{Object.entries(states).map(([k, v]) =>
          <option key={k} value={k}>{v}
          </option>
        )}
        <option value="review">需要复核</option>
      </select>
    </div>
    <div className="studio-split">
      <div className="studio-list">{items.filter(f => !filter || (filter === 'review' ? f.needs_review : f.status === filter)).map(f =>
        <button
          key={f.id}
          className={`studio-list-item ${draft?.id === f.id ? 'active' : ''}`}
          onClick={() => choose(f)}>
          <span className="studio-item-title">
            <b>{f.title}
            </b>
            <small>{states[f.status || 'planned'] || f.status}{f.needs_review ? ' · 待复核' : ''}
            </small>
          </span>
          <span>{f.description}
          </span>
          <small>{f.target_chapter ? `目标第 ${f.target_chapter} 章` : '未设目标章节'} · {f.events.length} 条事件</small>
        </button>
      )}{!items.length && <Empty>还没有伏笔。从一个计划开始，发生后再追加证据。</Empty>
        }
      </div>{draft ?
        <form
          className="studio-detail studio-fields"
          onSubmit={e => {
            e.preventDefault();
            run(async () => {
              if (!draft.title.trim()) throw new Error('请填写伏笔标题。');
              if (event.basis === 'chapter' && event.note.trim() && !event.memory_id) throw new Error('正文事件必须选择有效记忆作为来源。');
              const payload = { ...draft, events: appendEvent(draft.events, event) };
              const saved = await api<Foreshadow>(draft.id ? `/foreshadows/${draft.id}` : `/novels/${novelId}/foreshadows`, { method: draft.id ? 'PATCH' : 'POST', ...json(payload) });
              setDraft(saved);
              setOriginal(JSON.stringify(saved));
              setEvent({ state: 'planted', note: '', memory_id: null, basis: 'author' });
              await load();
            });
          }}>
          <div className="studio-detail-title">
            <h3>{draft.id ? draft.title : '新伏笔计划'}
            </h3>
            <span className="studio-badge">{dirty ? '未保存修改' : `版本 ${draft.revision || 1}`}
            </span>
          </div>
          <fieldset className="studio-fields" disabled={busy || locked}>
            <label>标题<input required value={draft.title} onChange={e => setDraft({ ...draft, title: e.target.value })} />
            </label>
            <label>计划说明<textarea
              rows={4}
              value={draft.description}
              onChange={e => setDraft({ ...draft, description: e.target.value })} />
            </label>
            <label>目标章节（可留空）<input
              type="number"
              min={1}
              value={draft.target_chapter ?? ''}
              onChange={e => setDraft({ ...draft, target_chapter: e.target.value ? Number(e.target.value) : null })} />
            </label>
            <h3>事件时间线</h3>{!draft.events.length && <p className="muted">尚无事件，当前只是作者计划。</p>
            }
            <ol className="studio-timeline">{draft.events.map((ev, i) =>
              <li key={ev.id || i}>
                <b>{states[ev.state] || ev.state}
                </b>
                <span className="studio-badge">{ev.basis === 'chapter' ? '正文证据' : '作者设定'}{ev.stale ? ' · 来源过期' : ''}
                </span>
                <p>{ev.note}
                </p>{ev.memory_id && <details>
                  <summary>查看来源记忆</summary>
                  <small>引用记忆版本 {ev.memory_revision || '未知'}
                  </small>
                  <p>{memoryAtRevision(memories.find(m => m.id === ev.memory_id), ev.memory_revision)?.content || '历史证据不可用'}
                  </p>
                  <blockquote>{memoryAtRevision(memories.find(m => m.id === ev.memory_id), ev.memory_revision)?.evidence_quote || '无法展示当时的正文原句'}
                  </blockquote>
                </details>
                }
              </li>
            )}
            </ol>
            <div className="studio-preview">
              <h3>追加事件（可选）</h3>
              <div className="studio-form-row">
                <label>进展<select value={event.state} onChange={e => setEvent({ ...event, state: e.target.value })}>{Object.entries(states).filter(([k]) => k !== 'planned').map(([k, v]) =>
                  <option key={k} value={k}>{v}
                  </option>
                )}
                </select>
                </label>
                <label>依据<select
                  value={event.basis}
                  onChange={e => setEvent({ ...event, basis: e.target.value, memory_id: null })}>
                  <option value="author">作者设定 / 后续计划</option>
                  <option value="chapter">正文已发生 · 关联记忆</option>
                </select>
                </label>
              </div>{event.basis === 'chapter' ?
                <label>有效来源记忆<select
                  value={event.memory_id || ''}
                  onChange={e => setEvent({ ...event, memory_id: e.target.value || null })}>
                  <option value="">选择正文来源</option>{evidence.map(m =>
                    <option key={m.id} value={m.id}>{m.content.slice(0, 75)}
                    </option>
                  )}
                </select>
                </label>
                :
                <p className="muted">作者事件表示设定或计划，不证明正文中已经发生。</p>
              }
              <label>事件说明<textarea
                rows={3}
                value={event.note}
                onChange={e => setEvent({ ...event, note: e.target.value })}
                placeholder="写明本次推进、回收或修正；留空则只保存上方计划" />
              </label>
            </div>
            <button className="button primary" disabled={!dirty}>保存计划与新增事件</button>
          </fieldset>
        </form>
        :
        <Empty>选择一条伏笔，查看计划与事件时间线。</Empty>
      }
    </div>
  </section>;
}
