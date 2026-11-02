import type { Memory, Prompt } from './shared';
// A template is selectable only for its frozen job kind and current book scope.
export const matchingPrompts = (prompts: Prompt[], kind: string, novelId?: string) =>
  prompts.filter(p => p.enabled && p.task_kind === kind && (!p.novel_id || p.novel_id === novelId));
// An edge/event cites the fact as it existed at its frozen revision, never a later edit.
export function memoryAtRevision(memory: Memory | undefined, revision?: number | null): Partial<Memory> | undefined {
  if (!memory || revision == null) return undefined;
  return memory.revision === revision ? memory : memory.history?.find(item => item.revision === revision);
}
export function restorePromptFields(current: Prompt, snapshot: Partial<Prompt>) {
  return { name: snapshot.name ?? current.name, category: snapshot.category ?? current.category, task_kind: snapshot.task_kind ?? current.task_kind, genre_tags: snapshot.genre_tags ?? current.genre_tags, description: snapshot.description ?? current.description, body: snapshot.body ?? current.body, enabled: snapshot.enabled ?? current.enabled, novel_id: current.novel_id, revision: current.revision };
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
