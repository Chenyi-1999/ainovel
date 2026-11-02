import { useEffect, useState } from 'react';
export type Api = <T = any>(path: string, init?: RequestInit) => Promise<T>;
export type PromptSourceBlock = { identifier?: string; name?: string; role?: string; enabled?: boolean; injection_order?: number; template_file?: string; body?: string; sha256?: string };
export type PromptSourceInfo = { project?: string; repository?: string; commit?: string; key?: string; path?: string; license?: string; original_name?: string; original_category?: string; original_body?: string; raw_sha256?: string; parameters?: string[]; blocks?: PromptSourceBlock[]; compatibility?: 'adapted' | 'reference_only'; adapter_note?: string };
export type Prompt = { id: string; name: string; category: string; task_kind: string; genre_tags: string[]; description: string; body: string; novel_id: string | null; enabled: boolean; builtin: boolean; source_label: string; source_info?: PromptSourceInfo; revision: number };
export type Entity = { id: string; name: string; kind: string; aliases: string[]; description: string; revision: number };
export type Memory = { id: string; kind: string; content: string; source_chapter_id?: string | null; source_revision?: number | null; evidence_quote?: string; provenance?: string; visibility?: string; known_by_entity_ids?: string[]; revision?: number; stale?: boolean; history?: Partial<Memory>[] };
export type Chapter = { id: string; number: number; title: string; revision?: number };
export type Job = { id: string; kind: string; status: string; result?: any; chapter_id?: string };
export const taskNames: Record<string, string> = { outline: '生成大纲', write: '续写章节', rewrite: '选段改写', audit: '审稿检查', confirm: '提取记忆候选' };
export const memoryNames: Record<string, string> = { setting: '设定', character: '人物', timeline: '时间线', foreshadow: '伏笔', summary: '章节摘要' };
export const json = (value: unknown) => ({ body: JSON.stringify(value) });
export const errorText = (e: unknown) => e instanceof Error ? e.message : String(e);
export function useUnsaved(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    const key = Symbol();
    unsaved.set(key, true);
    return () => {
      window.removeEventListener('beforeunload', handler);
      unsaved.delete(key);
    };
  }, [dirty]);
}
const unsaved = new Map<symbol, boolean>();
export const canLeaveStudio = () => !unsaved.size || window.confirm('当前资料有未保存修改，离开会放弃这些修改。仍要继续吗？');
export function Feedback({ error, busy }: { error?: string; busy?: boolean }) {
  return <>{busy && <p className="studio-status" role="status">正在处理…</p>
  }{error && <p className="studio-error" role="alert">{error} {error.includes('409') && '资料已被更新，请重新载入后核对再保存。'}
  </p>
    }</>;
}
export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="studio-empty">{children}
  </div>;
}
export function Header({ title, text, children }: { title: string; text: string; children?: React.ReactNode }) {
  return <div className="studio-heading">
    <div>
      <h2>{title}
      </h2>
      <p>{text}
      </p>
    </div>
    <div className="studio-actions">{children}
    </div>
  </div>;
}
export function useOperation() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await fn();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run, setError };
}
export function MemoryFields({ value, onChange, entities }: { value: Partial<Memory>; onChange: (value: Partial<Memory>) => void; entities: Entity[] }) {
  return <>
    <div className="studio-form-row">
      <label>类型<select
        value={value.kind || 'setting'}
        onChange={e => onChange({ ...value, kind: e.target.value })}>{Object.entries(memoryNames).map(([k, v]) =>
          <option key={k} value={k}>{v}
          </option>
        )}
      </select>
      </label>
      <label>知情范围<select
        value={value.visibility || 'author_only'}
        onChange={e => onChange({ ...value, visibility: e.target.value, known_by_entity_ids: e.target.value === 'characters' ? value.known_by_entity_ids || [] : [] })}>
        <option value="author_only">作者设定</option>
        <option value="public">公开信息</option>
        <option value="characters">指定人物知情</option>
        <option value="unknown">尚未标注</option>
      </select>
      </label>
    </div>
    <label>内容<textarea
      required
      rows={4}
      value={value.content || ''}
      onChange={e => onChange({ ...value, content: e.target.value })} />
    </label>{value.visibility === 'characters' && <fieldset className="studio-checks">
      <legend>知情人物</legend>{entities.filter(e => e.kind === 'character').map(e =>
        <label key={e.id}>
          <input
            type="checkbox"
            checked={(value.known_by_entity_ids || []).includes(e.id)}
            onChange={event => onChange({ ...value, known_by_entity_ids: event.target.checked ? [...(value.known_by_entity_ids || []), e.id] : (value.known_by_entity_ids || []).filter(id => id !== e.id) })} />{e.name}
        </label>
      )}{!entities.some(e => e.kind === 'character') && <small>先在关系图栏目添加人物实体。</small>
      }
    </fieldset>
    }</>;
}
