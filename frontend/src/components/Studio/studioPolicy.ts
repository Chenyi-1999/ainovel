import type { Memory, Prompt } from './shared';
// Prompt references never become executable jobs, including user copies with source metadata.
export const promptTaskNames: Record<string, string> = { outline: '生成大纲', write: '续写章节', rewrite: '选段改写', audit: '审稿检查', confirm: '提取记忆候选', reference: '原文参考（未接入任务）' };
export const runnablePrompt = (prompt: Prompt) => prompt.task_kind !== 'reference' && prompt.source_info?.compatibility !== 'reference_only' && ['outline', 'write', 'rewrite', 'audit', 'confirm'].includes(prompt.task_kind);
export const promptSourceName = (prompt: Prompt) => prompt.source_info?.project || (prompt.builtin ? '本项目原创' : '用户自定义');
export type PromptFilters = { search?: string; category?: string; task?: string; tag?: string; scope?: string; source?: string; compatibility?: string; novelId?: string };
export function filterPrompts(prompts: Prompt[], filters: PromptFilters) {
  const { search, category, task, tag, scope, source, compatibility, novelId } = filters;
  return prompts.filter(p => (!search || `${p.name} ${p.description} ${p.body} ${p.source_info?.original_name || ''} ${p.source_info?.original_body || ''}`.toLowerCase().includes(search.toLowerCase()))
    && (!category || p.category === category) && (!task || p.task_kind === task) && (!tag || p.genre_tags.includes(tag))
    && (!scope || (scope === 'builtin' ? p.builtin : scope === 'global' ? !p.novel_id && !p.builtin : p.novel_id === novelId))
    && (!source || (source === 'original' ? p.builtin && !p.source_info?.project : source === 'custom' ? !p.builtin : p.source_info?.project === source))
    && (!compatibility || runnablePrompt(p) === (compatibility === 'adapted')));
}
export function promptSavePayload(draft: Prompt, tags: string, copy = false): Partial<Prompt> {
  const creating = copy || !draft.id || draft.builtin;
  const payload: Partial<Prompt> = { ...draft, genre_tags: tags.split(/[,，]/).map(v => v.trim()).filter(Boolean), ...(creating ? { name: copy ? `${draft.name} · 副本` : draft.name, builtin: false, source_label: '自定义' } : {}) };
  if (creating) { delete payload.id; delete payload.revision; }
  return payload;
}
// Only a canonical HTTPS GitHub repository may be opened; every other source field is plain text.
export function safeGithubRepository(value?: string): string | undefined {
  if (!value || !/^https:\/\/github\.com\/[A-Za-z0-9_-][A-Za-z0-9_.-]*\/[A-Za-z0-9_-][A-Za-z0-9_.-]*\/?$/.test(value)) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.hostname === 'github.com' && !url.port && !url.username && !url.password && !url.search && !url.hash ? url.href : undefined;
  } catch { return undefined; }
}
export function selectPromptText(field: { focus: () => void; select: () => void }) {
  field.focus();
  field.select();
}
// A template is selectable only for its frozen job kind and current book scope.
export const matchingPrompts = (prompts: Prompt[], kind: string, novelId?: string) =>
  prompts.filter(p => runnablePrompt(p) && p.enabled && p.task_kind === kind && (!p.novel_id || p.novel_id === novelId));
// An edge/event cites the fact as it existed at its frozen revision, never a later edit.
export function memoryAtRevision(memory: Memory | undefined, revision?: number | null): Partial<Memory> | undefined {
  if (!memory || revision == null) return undefined;
  return memory.revision === revision ? memory : memory.history?.find(item => item.revision === revision);
}
export function restorePromptFields(current: Prompt, snapshot: Partial<Prompt>) {
  return { name: snapshot.name ?? current.name, category: snapshot.category ?? current.category, task_kind: snapshot.task_kind ?? current.task_kind, genre_tags: snapshot.genre_tags ?? current.genre_tags, description: snapshot.description ?? current.description, body: snapshot.body ?? current.body, source_info: snapshot.source_info ?? current.source_info ?? {}, enabled: snapshot.enabled ?? current.enabled, novel_id: current.novel_id, revision: current.revision };
}
// Apply only the reviewed candidate fields; chapter identity and provenance belong to the server.
export function memoryApplication(expectedRevision: number, candidates: Partial<Memory>[]) {
  if (!candidates.some(m => m.kind === 'summary')) throw new Error('必须采纳至少一条章节摘要。');
  if (candidates.some(m => !m.content?.trim() || !m.evidence_quote?.trim())) throw new Error('所选记忆必须有内容与正文原句。');
  return { expected_revision: expectedRevision, memories: candidates.map(m => ({ kind: m.kind, content: m.content, evidence_quote: m.evidence_quote, visibility: m.visibility || 'unknown', known_by_entity_ids: m.visibility === 'characters' ? m.known_by_entity_ids || [] : [] })) };
}
// Existing event snapshots are immutable, including the source memory revision.
export function appendEvent<T extends { basis: string; memory_id: string | null; note: string }>(events: T[], next: T): T[] {
  if (!next.note.trim()) return [...events];
  if (next.basis === 'chapter' && !next.memory_id) throw new Error('正文事件必须选择有效记忆作为来源。');
  return [...events, { ...next, memory_id: next.basis === 'author' ? null : next.memory_id }];
}
