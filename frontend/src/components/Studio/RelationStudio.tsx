import { memoryAtRevision } from './studioPolicy';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Api, Entity, Empty, Feedback, Header, Memory, json, useOperation, useUnsaved } from './shared';
type Relation = { id?: string; source_entity_id: string; target_entity_id: string; label: string; description: string; basis: string; memory_id: string | null; revision?: number; stale?: boolean; memory_revision?: number | null; revalidate_source?: boolean };
const entityNames: Record<string, string> = { character: '人物', location: '地点', organization: '组织', item: '物品', other: '其他' };
const blankEntity = (): Entity => ({ id: '', name: '', kind: 'character', aliases: [], description: '', revision: 1 });
const blankRelation = (): Relation => ({ source_entity_id: '', target_entity_id: '', label: '', description: '', basis: 'author', memory_id: null });
export default function RelationStudio({ api, novelId, memories, locked }: { api: Api; novelId: string; memories: Memory[]; locked: boolean }) {
  const [tab, setTab] = useState('graph');
  const [entities, setEntities] = useState<Entity[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [graph, setGraph] = useState<{ nodes: Entity[]; edges: Relation[]; cutoff: number | null }>({ nodes: [], edges: [], cutoff: null });
  const [entity, setEntity] = useState<Entity | null>(null);
  const [relation, setRelation] = useState<Relation | null>(null);
  const [original, setOriginal] = useState('');
  const [aliases, setAliases] = useState('');
  const [before, setBefore] = useState('');
  const [stale, setStale] = useState(false);
  const [page, setPage] = useState(0);
  const [focused, setFocused] = useState('');
  const { busy, error, run } = useOperation();
  const dirty = tab === 'entities' ? !!entity && JSON.stringify({ ...entity, aliases: aliases.split(/[,，]/).map(v => v.trim()).filter(Boolean) }) !== original : tab === 'relations' ? !!relation && JSON.stringify(relation) !== original : false;
  useUnsaved(dirty);
  const requestVersion = useRef(0);
  const load = async () => {
    const version = ++requestVersion.current;
    const [es, rs, g] = await Promise.all([api<Entity[]>(`/novels/${novelId}/entities`), api<Relation[]>(`/novels/${novelId}/relations`), api<typeof graph>(`/novels/${novelId}/graph?include_stale=${stale}${before ? `&before_chapter=${Number(before)}` : ''}`)]);
    if (version !== requestVersion.current) return;
    setEntities(es);
    setRelations(rs);
    setGraph(g);
  };
  useEffect(() => {
    run(load);
  }, [novelId, stale, before]);
  const name = (id: string) => entities.find(e => e.id === id)?.name || '未知实体';
  const visibleNodes = graph.nodes.slice(page * 24, page * 24 + 24);
  const nodeIds = new Set(visibleNodes.map(n => n.id));
  const visibleEdges = graph.edges.filter(e => nodeIds.has(e.source_entity_id) && nodeIds.has(e.target_entity_id));
  const positions = useMemo(() => Object.fromEntries(visibleNodes.map((n, i) => {
    const angle = i / Math.max(1, visibleNodes.length) * Math.PI * 2 - Math.PI / 2;
    return [n.id, { x: visibleNodes.length === 1 ? 400 : 400 + Math.cos(angle) * 280, y: visibleNodes.length === 1 ? 265 : 265 + Math.sin(angle) * 200 }];
  })), [visibleNodes]);
  const switchTab = (next: string) => {
    if (dirty && !window.confirm('放弃未保存的实体或关系修改？')) return;
    setTab(next);
    setEntity(null);
    setRelation(null);
    setOriginal('');
  };
  const chooseEntity = (e: Entity) => {
    if (dirty && !window.confirm('放弃当前实体修改？')) return;
    setEntity({ ...e });
    setAliases(e.aliases.join(', '));
    setOriginal(JSON.stringify(e));
  };
  const chooseRelation = (r: Relation) => {
    if (dirty && !window.confirm('放弃当前关系修改？')) return;
    setRelation({ ...r });
    setOriginal(JSON.stringify(r));
  };
  const evidence = memories.filter(m => !m.stale && m.provenance !== 'legacy' && m.source_chapter_id && m.evidence_quote);
  const source = (r: Relation) => {
    const evidence = memoryAtRevision(memories.find(m => m.id === r.memory_id), r.memory_revision);
    return <>
      <span className={`studio-badge ${r.stale ? 'stale' : ''}`}>{r.basis === 'chapter' ? '正文证据' : '作者设定'}{r.stale ? ' · 已过期' : ''}
      </span>{r.memory_id && <details>
        <summary>来源记忆与原句 · 记忆版本 {r.memory_revision || '未知'}
        </summary>{evidence ? <>
          <p>{evidence.content}
          </p>
          <blockquote>{evidence.evidence_quote || '缺少原句'}
          </blockquote>
          <small>来源正文版本 {evidence.source_revision || '未知'}
          </small>
        </> :
          <p>历史证据不可用，无法确认当时引用的事实。请重新复核来源。</p>
        }
      </details>
      }</>;
  };
  return <section className="section-card studio">
    <Header title="关系图谱" text="用实体组织人物、地点与组织。作者设定和正文关系分开记录，保留证据来源。">
      <button
        className="button outline small"
        disabled={busy}
        onClick={() => {
          if (dirty && !window.confirm('重新载入将放弃未保存修改，继续？')) return;
          run(async () => {
            await load();
            setEntity(null);
            setRelation(null);
            setOriginal('');
          });
        }}>重新载入</button>
    </Header>
    <div className="studio-subtabs" role="tablist" aria-label="关系资料">{[['graph', '关系图谱'], ['entities', '实体管理'], ['relations', '关系管理']].map(([k, v]) =>
      <button
        role="tab"
        aria-selected={tab === k}
        key={k}
        className={tab === k ? 'active' : ''}
        onClick={() => switchTab(k)}>{v}
      </button>
    )}
    </div>
    <Feedback busy={busy} error={error} />
    {tab === 'graph' && <>
      <div className="studio-filters">
        <label>按章截断（仅显示该章之前的正文证据）<input
          type="number"
          min={1}
          aria-label="按章截断"
          value={before}
          onChange={e => {
            setBefore(e.target.value);
            setPage(0);
          }}
          placeholder="全部章节" />
        </label>
        <label className="studio-check">
          <input type="checkbox" checked={stale} onChange={e => setStale(e.target.checked)} />显示已过期关系</label>
        <span className="muted">{graph.nodes.length} 个实体 · {graph.edges.length} 条关系</span>
      </div>{graph.nodes.length ? <>
        <div className="studio-graph">
          <svg viewBox="0 0 800 530" role="img" aria-label="人物和故事实体关系图">
            <title>关系图谱。点击节点筛选下方关系列表。</title>
            <defs>
              <marker id="studio-arrow" markerWidth="7" markerHeight="7" refX="20" refY="3" orient="auto">
                <path d="M0,0 L6,3 L0,6" fill="context-stroke" />
              </marker>
            </defs>{visibleEdges.map((r, i) => {
              const a = positions[r.source_entity_id];
              const b = positions[r.target_entity_id];
              return <g key={r.id || i} className={r.stale ? 'studio-edge stale' : 'studio-edge'}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} markerEnd="url(#studio-arrow)" />
                <text x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 7}>{r.label.slice(0, 14)}
                </text>
              </g>;
            })}{visibleNodes.map(n =>
              <g
                key={n.id}
                role="button"
                tabIndex={0}
                aria-label={`${n.name}，${entityNames[n.kind]}，点击筛选关系`}
                onClick={() => setFocused(focused === n.id ? '' : n.id)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setFocused(focused === n.id ? '' : n.id);
                  }
                }}
                className={`studio-node ${focused === n.id ? 'active' : ''}`}
                transform={`translate(${positions[n.id].x},${positions[n.id].y})`}>
                <title>{n.name} · {n.description}
                </title>
                <circle r={24} />
                <text textAnchor="middle" y={5}>{n.name.slice(0, 3)}
                </text>
                <text className="studio-node-label" textAnchor="middle" y={43}>{n.name.length > 12 ? `${n.name.slice(0, 12)}…` : n.name}
                </text>
              </g>
            )}
          </svg>
        </div>{graph.nodes.length > 24 && <div className="studio-actions">
          <button
            className="button outline small"
            disabled={page === 0}
            onClick={() => {
              setPage(page - 1);
              setFocused('');
            }}>上一组</button>
          <span>{page + 1} / {Math.ceil(graph.nodes.length / 24)} 组 · 每组最多 24 个节点，完整关系见下方列表</span>
          <button
            className="button outline small"
            disabled={(page + 1) * 24 >= graph.nodes.length}
            onClick={() => {
              setPage(page + 1);
              setFocused('');
            }}>下一组</button>
        </div>
        }
        <div className="studio-detail-title">
          <h3>{focused ? `${name(focused)}的关系` : '关系与来源'}
          </h3>{focused && <button className="text-button" onClick={() => setFocused('')}>取消筛选</button>
          }
        </div>
        <div className="studio-edge-list">{graph.edges.filter(r => !focused || r.source_entity_id === focused || r.target_entity_id === focused).map((r, i) =>
          <article key={r.id || i} className={r.stale ? 'stale' : ''}>
            <b>{name(r.source_entity_id)} → {r.label} → {name(r.target_entity_id)}
            </b>
            <p>{r.description}
            </p>{source(r)}
          </article>
        )}
        </div>{!graph.edges.length && <Empty>目前没有符合范围的关系。请到关系管理添加作者设定或正文证据。</Empty>
        }</> :
        <Empty>图谱尚无实体。先到实体管理添加人物、地点或组织。</Empty>
      }</>}
    {tab === 'entities' && <>
      <div className="studio-actions">
        <button
          className="button primary small"
          disabled={locked}
          onClick={() => chooseEntity(blankEntity())}>新增实体</button>
      </div>
      <div className="studio-split">
        <div className="studio-list">{entities.map(e =>
          <button
            key={e.id}
            className={`studio-list-item ${entity?.id === e.id ? 'active' : ''}`}
            onClick={() => chooseEntity(e)}>
            <b>{e.name}
            </b>
            <span>{entityNames[e.kind]} · {e.aliases.join(' / ') || '无别名'}
            </span>
            <small>{e.description}
            </small>
          </button>
        )}{!entities.length && <Empty>还没有故事实体。</Empty>
          }
        </div>{entity ?
          <form
            className="studio-detail studio-fields"
            onSubmit={e => {
              e.preventDefault();
              run(async () => {
                const payload: Partial<Entity> = { ...entity, aliases: aliases.split(/[,，]/).map(v => v.trim()).filter(Boolean) };
                if (!entity.id) {
                  delete payload.id;
                  delete payload.revision;
                }
                const saved = await api<Entity>(entity.id ? `/entities/${entity.id}` : `/novels/${novelId}/entities`, { method: entity.id ? 'PATCH' : 'POST', ...json(payload) });
                setEntity(saved);
                setAliases(saved.aliases.join(', '));
                setOriginal(JSON.stringify(saved));
                await load();
              });
            }}>
            <h3>{entity.id ? '编辑实体' : '新增实体'}{dirty && <small> · 未保存</small>
            }
            </h3>
            <fieldset className="studio-fields" disabled={busy || locked}>
              <label>名称<input
                required
                value={entity.name}
                onChange={e => setEntity({ ...entity, name: e.target.value })} />
              </label>
              <label>类型<select value={entity.kind} onChange={e => setEntity({ ...entity, kind: e.target.value })}>{Object.entries(entityNames).map(([k, v]) =>
                <option key={k} value={k}>{v}
                </option>
              )}
              </select>
              </label>
              <label>别名（用逗号分隔）<input value={aliases} onChange={e => setAliases(e.target.value)} />
              </label>
              <label>描述<textarea
                rows={5}
                value={entity.description}
                onChange={e => setEntity({ ...entity, description: e.target.value })} />
              </label>
              <div className="studio-actions">
                <button className="button primary small" disabled={!dirty}>保存实体</button>{entity.id && <button
                  type="button"
                  className="button outline small danger-text"
                  onClick={() => {
                    if (window.confirm(`删除实体“${entity.name}”？如有关联关系或知情记录，服务端会拒绝删除。`)) run(async () => {
                      await api(`/entities/${entity.id}`, { method: 'DELETE' });
                      setEntity(null);
                      await load();
                    });
                  }}>删除</button>
                }
              </div>
            </fieldset>
          </form>
          :
          <Empty>选择实体查看与编辑。</Empty>
        }
      </div>
    </>}
    {tab === 'relations' && <>
      <div className="studio-actions">
        <button
          className="button primary small"
          disabled={locked || entities.length < 2}
          onClick={() => chooseRelation(blankRelation())}>新增关系</button>{entities.length < 2 && <span className="muted">先添加至少两个实体。</span>
        }
      </div>
      <div className="studio-split">
        <div className="studio-list">{relations.map(r =>
          <button
            key={r.id}
            className={`studio-list-item ${relation?.id === r.id ? 'active' : ''}`}
            onClick={() => chooseRelation(r)}>
            <b>{name(r.source_entity_id)} → {name(r.target_entity_id)}
            </b>
            <span>{r.label}
            </span>
            <small>{r.basis === 'chapter' ? '正文关系' : '作者设定'}{r.stale ? ' · 已过期' : ''}
            </small>
          </button>
        )}{!relations.length && <Empty>还没有关系记录。</Empty>
          }
        </div>{relation ?
          <form
            className="studio-detail studio-fields"
            onSubmit={e => {
              e.preventDefault();
              run(async () => {
                if (relation.source_entity_id === relation.target_entity_id) throw new Error('请选择两个不同的实体。');
                if (relation.basis === 'chapter' && !relation.memory_id) throw new Error('正文关系必须选择有效来源记忆。');
                const saved = await api<Relation>(relation.id ? `/relations/${relation.id}` : `/novels/${novelId}/relations`, { method: relation.id ? 'PATCH' : 'POST', ...json(relation) });
                setRelation(saved);
                setOriginal(JSON.stringify(saved));
                await load();
              });
            }}>
            <h3>{relation.id ? '编辑关系' : '新增关系'}{dirty && <small> · 未保存</small>
            }
            </h3>
            <fieldset className="studio-fields" disabled={busy || locked}>
              <div className="studio-form-row">
                <label>起点<select
                  required
                  value={relation.source_entity_id}
                  onChange={e => setRelation({ ...relation, source_entity_id: e.target.value })}>
                  <option value="">选择实体</option>{entities.map(e =>
                    <option key={e.id} value={e.id}>{e.name}
                    </option>
                  )}
                </select>
                </label>
                <label>终点<select
                  required
                  value={relation.target_entity_id}
                  onChange={e => setRelation({ ...relation, target_entity_id: e.target.value })}>
                  <option value="">选择实体</option>{entities.map(e =>
                    <option key={e.id} value={e.id}>{e.name}
                    </option>
                  )}
                </select>
                </label>
              </div>
              <label>关系名称<input
                required
                value={relation.label}
                onChange={e => setRelation({ ...relation, label: e.target.value })}
                placeholder="例如：师徒、敌对、隶属" />
              </label>
              <label>说明<textarea
                rows={3}
                value={relation.description}
                onChange={e => setRelation({ ...relation, description: e.target.value })} />
              </label>
              <label>依据<select
                value={relation.basis}
                onChange={e => setRelation({ ...relation, basis: e.target.value, memory_id: null })}>
                <option value="author">作者设定</option>
                <option value="chapter">正文证据</option>
              </select>
              </label>{relation.basis === 'chapter' && <label>有效来源记忆<select
                required
                value={relation.memory_id || ''}
                onChange={e => setRelation({ ...relation, memory_id: e.target.value || null })}>
                <option value="">选择来源</option>{evidence.map(m =>
                  <option key={m.id} value={m.id}>{m.content.slice(0, 75)}
                  </option>
                )}{relation.memory_id && !evidence.some(m => m.id === relation.memory_id) && <option value={relation.memory_id}>现有来源 · 已过期或不可用</option>
                }
              </select>
              </label>
              }
              <div>{source(relation)}
              </div>{relation.id && relation.basis === 'chapter' && <label className="studio-check">
                <input
                  type="checkbox"
                  checked={!!relation.revalidate_source}
                  onChange={e => setRelation({ ...relation, revalidate_source: e.target.checked })} />我已复核当前来源，保存时采用该记忆的当前版本</label>
              }{relation.revalidate_source && <div className="studio-callout">
                <b>将采用的当前事实</b>
                <p>{memories.find(m => m.id === relation.memory_id)?.content || '来源不可用'}
                </p>
                <blockquote>{memories.find(m => m.id === relation.memory_id)?.evidence_quote || '缺少原句'}
                </blockquote>
                <small>记忆版本 {memories.find(m => m.id === relation.memory_id)?.revision || '未知'}；若来源本身已过期，服务端会拒绝采用。</small>
              </div>
              }
              <div className="studio-actions">
                <button className="button primary small" disabled={!dirty}>保存关系</button>{relation.id && <button
                  type="button"
                  className="button outline small danger-text"
                  onClick={() => {
                    if (window.confirm('删除这条关系？')) run(async () => {
                      await api(`/relations/${relation.id}`, { method: 'DELETE' });
                      setRelation(null);
                      await load();
                    });
                  }}>删除</button>
                }
              </div>
            </fieldset>
          </form>
          :
          <Empty>选择关系查看其来源，或新增关系。</Empty>
        }
      </div>
    </>}
  </section>;
}
