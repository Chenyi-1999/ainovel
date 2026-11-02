import { useEffect, useMemo, useState } from 'react';
import { Api, Prompt, Empty, Feedback, Header, json, taskNames, useOperation, useUnsaved } from './shared';
import { restorePromptFields } from './studioPolicy';
const blank = (novelId?: string): Prompt => ({ id: '', name: '', category: '创作规划', task_kind: 'outline', genre_tags: [], description: '', body: '', novel_id: novelId || null, enabled: true, builtin: false, source_label: '自定义', revision: 1 });
export default function PromptLibrary({ api, novelId, onChanged }: { api: Api; novelId?: string; onChanged: () => void }) {
  const [items, setItems] = useState<Prompt[]>([]);
  const [draft, setDraft] = useState<Prompt | null>(null);
  const [original, setOriginal] = useState('');
  const [tags, setTags] = useState('');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [task, setTask] = useState('');
  const [tag, setTag] = useState('');
  const [scope, setScope] = useState('');
  const [preview, setPreview] = useState('');
  const [previewInstructions, setPreviewInstructions] = useState('');
  const [history, setHistory] = useState<any[] | null>(null);
  const [importData, setImportData] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [notice, setNotice] = useState('');
  const { busy, error, run, setError } = useOperation();
  const dirty = !!draft && JSON.stringify({ ...draft, genre_tags: tags.split(/[,，]/).map(v => v.trim()).filter(Boolean) }) !== original;
  useUnsaved(dirty);
  const load = async () => {
    const data = await api<Prompt[]>('/prompts');
    setItems(data);
    return data;
  };
  useEffect(() => {
    run(async () => {
      await load();
    });
  }, [novelId]);
  const select = (p: Prompt) => {
    if (dirty && !window.confirm('放弃当前提示词的未保存修改？')) return;
    setDraft({ ...p });
    setTags(p.genre_tags.join(', '));
    setOriginal(JSON.stringify(p));
    setPreview('');
    setHistory(null);
  };
  const update = (p: Partial<Prompt>) => draft && setDraft({ ...draft, ...p });
  const visible = useMemo(() => items.filter(p => (!search || `${p.name} ${p.description} ${p.body}`.toLowerCase().includes(search.toLowerCase())) && (!category || p.category === category) && (!task || p.task_kind === task) && (!tag || p.genre_tags.includes(tag)) && (!scope || (scope === 'builtin' ? p.builtin : scope === 'global' ? !p.novel_id && !p.builtin : p.novel_id === novelId))), [items, search, category, task, tag, scope, novelId]);
  const save = (copy = false) => run(async () => {
    if (!draft?.name.trim() || !draft.body.trim()) throw new Error('请填写名称和提示词正文。');
    const creating = copy || !draft.id || draft.builtin;
    const payload = { ...draft, genre_tags: tags.split(/[,，]/).map(v => v.trim()).filter(Boolean), ...(creating ? { name: copy ? `${draft.name} · 副本` : draft.name, builtin: false, source_label: '自定义' } : {}) } as Partial<Prompt>;
    if (creating) {
      delete payload.id;
      delete payload.revision;
    }
    const saved = await api<Prompt>(creating ? '/prompts' : `/prompts/${draft.id}`, { method: creating ? 'POST' : 'PATCH', ...json(payload) });
    setDraft(saved);
    setTags(saved.genre_tags.join(', '));
    setOriginal(JSON.stringify(saved));
    await load();
    onChanged();
    setNotice('提示词已保存。');
  });
  const exportAll = () => run(async () => {
    const data = await api('/prompts/export');
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = '纸间-提示词库.json';
    link.click();
    URL.revokeObjectURL(url);
  });
  return <section className="section-card studio">
    <Header title="提示词库" text="按任务组织可复用的创作指令，题材标签独立于分类。内置模板可另存后调整。">
      <button className="button outline small" disabled={busy} onClick={exportAll}>导出</button>
      <label className="button outline small studio-file">导入 JSON<input
        type="file"
        accept="application/json,.json"
        disabled={busy}
        onChange={e => {
          const file = e.target.files?.[0];
          if (!file) return;
          run(async () => {
            const data = JSON.parse(await file.text());
            const result = await api('/prompts/import?dry_run=true', { method: 'POST', ...json(data) });
            setImportData(data);
            setReport(result);
          });
          e.target.value = '';
        }} />
      </label>
      <button className="button primary small" onClick={() => select(blank(novelId))}>新建提示词</button>
    </Header>
    <Feedback busy={busy} error={error} />{notice && <p className="studio-status" role="status">{notice}
    </p>
    }
    {report && <div className="studio-import">
      <h3>{importData ? '导入预检 · 尚未写入' : '导入结果'}
      </h3>
      <pre>{JSON.stringify(report, null, 2)}
      </pre>{importData && <p>实际导入只新增条目。存在冲突时整批不会写入，请修改文件后重新预检。</p>
      }
      <div className="studio-actions">{importData && <button
        className="button primary small"
        disabled={busy || !!report.conflicts?.length}
        onClick={() => run(async () => {
          const result = await api('/prompts/import?dry_run=false', { method: 'POST', ...json(importData) });
          setReport(result);
          setImportData(null);
          await load();
          onChanged();
        })}>确认实际导入</button>
      }
        <button className="button outline small" onClick={() => {
          setReport(null);
          setImportData(null);
        }}>关闭报告</button>
      </div>
    </div>
    }
    <div className="studio-filters">
      <input
        aria-label="搜索提示词"
        placeholder="搜索名称、说明或正文"
        value={search}
        onChange={e => setSearch(e.target.value)} />
      <select aria-label="分类筛选" value={category} onChange={e => setCategory(e.target.value)}>
        <option value="">全部分类</option>{Array.from(new Set(items.map(p => p.category))).map(c =>
          <option key={c}>{c}
          </option>
        )}
      </select>
      <select aria-label="任务筛选" value={task} onChange={e => setTask(e.target.value)}>
        <option value="">全部任务</option>{Object.entries(taskNames).map(([k, v]) =>
          <option key={k} value={k}>{v}
          </option>
        )}
      </select>
      <select aria-label="题材筛选" value={tag} onChange={e => setTag(e.target.value)}>
        <option value="">全部题材</option>{Array.from(new Set(items.flatMap(p => p.genre_tags))).map(t =>
          <option key={t}>{t}
          </option>
        )}
      </select>
      <select aria-label="范围筛选" value={scope} onChange={e => setScope(e.target.value)}>
        <option value="">全部范围</option>
        <option value="builtin">内置</option>
        <option value="global">全局自定义</option>{novelId && <option value="novel">当前作品</option>
        }
      </select>
      <button
        className="button outline small"
        disabled={busy}
        onClick={() => {
          if (dirty && !window.confirm('重新载入会放弃未保存修改，继续？')) return;
          run(async () => {
            const loaded = await load();
            if (draft?.id) {
              const fresh = loaded.find(p => p.id === draft.id);
              if (fresh) {
                setDraft(fresh);
                setTags(fresh.genre_tags.join(', '));
                setOriginal(JSON.stringify(fresh));
              }
            }
          });
        }}>重新载入</button>
    </div>
    <div className="studio-split">
      <div className="studio-list" aria-label="提示词列表">{visible.map(p =>
        <button
          key={p.id}
          className={`studio-list-item ${draft?.id === p.id ? 'active' : ''}`}
          onClick={() => select(p)}>
          <span className="studio-item-title">{p.name}
            <small>{p.enabled ? '已启用' : '已停用'}
            </small>
          </span>
          <span>{taskNames[p.task_kind]} · {p.category}
          </span>
          <small>{p.builtin ? '内置' : p.novel_id ? '作品专用' : '全局'} · {p.genre_tags.join(' / ') || '不限题材'}
          </small>
        </button>
      )}{!visible.length && <Empty>{busy ? '正在载入提示词…' : '没有符合条件的提示词。'}
      </Empty>
        }
      </div>
      {draft ?
        <div className="studio-detail">
          <div className="studio-detail-title">
            <h3>{draft.id ? draft.name : '新建提示词'}
            </h3>
            <span className="studio-badge">{draft.builtin ? '内置 · 只读' : dirty ? '未保存修改' : `版本 ${draft.revision}`}
            </span>
          </div>
          <fieldset disabled={draft.builtin || busy} className="studio-fields">
            <label>名称<input value={draft.name} onChange={e => update({ name: e.target.value })} />
            </label>
            <div className="studio-form-row">
              <label>分类<input
                list="prompt-categories"
                value={draft.category}
                onChange={e => update({ category: e.target.value })} />
                <datalist id="prompt-categories">{['创作规划', '正文创作', '文字加工', '审读分析'].map(c =>
                  <option key={c}>{c}
                  </option>
                )}
                </datalist>
              </label>
              <label>任务<select value={draft.task_kind} onChange={e => update({ task_kind: e.target.value })}>{Object.entries(taskNames).map(([k, v]) =>
                <option key={k} value={k}>{v}
                </option>
              )}
              </select>
              </label>
            </div>
            <label>题材标签（用逗号分隔）<input value={tags} onChange={e => setTags(e.target.value)} />
            </label>
            <label>适用范围<select value={draft.novel_id || ''} onChange={e => update({ novel_id: e.target.value || null })}>
              <option value="">全局</option>{novelId && <option value={novelId}>当前作品</option>
              }{draft.novel_id && draft.novel_id !== novelId && <option value={draft.novel_id}>其他作品</option>
              }
            </select>
            </label>
            <label>说明<textarea
              rows={2}
              value={draft.description}
              onChange={e => update({ description: e.target.value })} />
            </label>
            <label>正文<textarea
              className="studio-code"
              rows={12}
              value={draft.body}
              onChange={e => update({ body: e.target.value })} />
            </label>
            <small>可用变量：{'{{title}} / {{genre}} / {{style}} / {{instructions}}'}。仅替换这些安全变量。</small>
            <label className="studio-check">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={e => update({ enabled: e.target.checked })} />启用此模板</label>
          </fieldset>
          <div className="studio-actions">{!draft.builtin && <button className="button primary small" disabled={busy || !dirty} onClick={() => save()}>保存</button>
          }
            <button className="button outline small" disabled={busy} onClick={() => save(true)}>另存为自定义</button>{draft.id && <>
              <button
                className="button outline small"
                disabled={busy || dirty}
                onClick={() => run(async () => {
                  const h = await api<any>(`/prompts/${draft.id}/versions`);
                  setHistory(Array.isArray(h) ? h : h.versions || []);
                })}>版本历史</button>{!draft.builtin && <button
                  className="button outline small danger-text"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(`删除“${draft.name}”？`)) run(async () => {
                      await api(`/prompts/${draft.id}`, { method: 'DELETE' });
                      setDraft(null);
                      setOriginal('');
                      await load();
                      onChanged();
                    });
                  }}>删除</button>
              }</>}
          </div>{draft.id && <div className="studio-preview">
            <label>预览附加指令<input
              value={previewInstructions}
              onChange={e => setPreviewInstructions(e.target.value)}
              placeholder="可选，用于检查变量替换" />
            </label>
            <button
              className="button soft small"
              disabled={busy || dirty}
              onClick={() => run(async () => {
                const result = await api<any>(`/prompts/${draft.id}/preview`, { method: 'POST', ...json({ novel_id: novelId, instructions: previewInstructions }) });
                setPreview(result.rendered);
              })}>预览已保存版本</button>{preview && <pre>{preview}
              </pre>
            }
          </div>
          }{history && <div className="studio-history">
            <h3>版本历史</h3>{history.length ? history.map((h, i) =>
              <details key={h.id || i}>
                <summary>版本 {h.revision || i + 1} · {h.snapshot?.name || h.name || draft.name}
                </summary>
                <pre>{h.snapshot?.body || h.body || '历史正文不可用'}
                </pre>
                {!draft.builtin && h.snapshot?.body && <button
                  className="button outline small"
                  disabled={busy || dirty}
                  onClick={() => run(async () => {
                    const saved = await api<Prompt>(`/prompts/${draft.id}`, { method: 'PATCH', ...json(restorePromptFields(draft, h.snapshot)) });
                    setDraft(saved);
                    setTags(saved.genre_tags.join(', '));
                    setOriginal(JSON.stringify(saved));
                    setPreview('');
                    await load();
                    setHistory(await api<any[]>(`/prompts/${draft.id}/versions`));
                    onChanged();
                    setNotice(`已将版本 ${h.revision} 恢复为新修订，适用作品范围保持不变。`);
                  })}>恢复此版本为新修订</button>}
              </details>
            ) :
              <p className="muted">暂无历史版本。</p>
            }
          </div>
          }
        </div>
        :
        <Empty>选择一个提示词查看详情，或新建自己的模板。</Empty>
      }
    </div>
  </section>;
}
