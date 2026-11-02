import test from 'node:test';
import assert from 'node:assert/strict';
import { appendEvent, matchingPrompts, memoryApplication, memoryAtRevision, restorePromptFields } from '../src/components/Studio/studioPolicy.ts';

test('template choices honor task, enablement, and current novel scope', () => {
  const base = { enabled: true, task_kind: 'write', novel_id: null };
  const prompts = [{ ...base, id: 'global' }, { ...base, id: 'own', novel_id: 'book-a' }, { ...base, id: 'other', novel_id: 'book-b' }, { ...base, id: 'wrong-task', task_kind: 'rewrite' }, { ...base, id: 'disabled', enabled: false }];
  assert.deepEqual(matchingPrompts(prompts, 'write', 'book-a').map(p => p.id), ['global', 'own']);
  assert.deepEqual(matchingPrompts(prompts, 'write').map(p => p.id), ['global']);
});
test('memory adoption requires summary and evidence; ownership metadata is server supplied', () => {
  assert.throws(() => memoryApplication(3, [{ kind: 'setting', content: '设定', evidence_quote: '原句' }]), /章节摘要/);
  assert.throws(() => memoryApplication(3, [{ kind: 'summary', content: '摘要', evidence_quote: ' ' }]), /原句/);
  const result = memoryApplication(3, [{ kind: 'summary', content: '摘要', evidence_quote: '原句', visibility: 'public', known_by_entity_ids: ['person'], source_chapter_id: 'untrusted', provenance: 'manual' }]);
  assert.deepEqual(result, { expected_revision: 3, memories: [{ kind: 'summary', content: '摘要', evidence_quote: '原句', visibility: 'public', known_by_entity_ids: [] }] });
});
test('foreshadow appends retain exact old event and source revision without mutation', () => {
  const old = [{ id: 'old', state: 'planted', note: '旧事件', memory_id: 'memory', memory_revision: 7, basis: 'chapter', stale: false }];
  const next = { state: 'resolved', note: '回收', memory_id: null, basis: 'author' };
  const result = appendEvent(old, next);
  assert.equal(old.length, 1); assert.equal(result[0], old[0]); assert.equal(result[0].memory_revision, 7); assert.equal(result.length, 2);
  assert.throws(() => appendEvent(old, { ...next, basis: 'chapter' }), /有效记忆/);
  assert.deepEqual(appendEvent(old, { ...next, note: '' }), old);
});
test('source evidence resolves the frozen revision without substituting later facts', () => {
  const memory = { id: 'm', revision: 3, content: '改后的事实', evidence_quote: '新原句', history: [{ revision: 2, content: '原事实', evidence_quote: '旧原句' }] };
  assert.equal(memoryAtRevision(memory, 2).evidence_quote, '旧原句');
  assert.equal(memoryAtRevision(memory, 3).evidence_quote, '新原句');
  assert.equal(memoryAtRevision(memory, 1), undefined);
  assert.equal(memoryAtRevision(memory, null), undefined);
});
test('restoring a prompt creates a new revision within its current novel scope', () => {
  const current = { name: '当前', body: '当前正文', novel_id: 'book-a', revision: 7 };
  const restored = restorePromptFields(current, { name: '旧名', body: '旧正文', novel_id: 'book-b', revision: 2 });
  assert.equal(restored.body, '旧正文'); assert.equal(restored.name, '旧名');
  assert.equal(restored.novel_id, 'book-a'); assert.equal(restored.revision, 7);
});
