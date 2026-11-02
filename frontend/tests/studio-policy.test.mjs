import test from 'node:test';
import assert from 'node:assert/strict';
import { appendEvent, filterPrompts, matchingPrompts, memoryApplication, memoryAtRevision, promptSavePayload, promptSourceName, restorePromptFields, runnablePrompt, safeGithubRepository, selectPromptText } from '../src/components/Studio/studioPolicy.ts';

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

const sourceInfo = { project: 'MuMuAINovel', repository: 'https://github.com/owner/repo', commit: 'source-commit', path: 'prompts.py', original_body: '原始参数 {novel_title}\n<script>alert(1)</script>', parameters: ['novel_title'], compatibility: 'adapted', adapter_note: '适配说明', raw_sha256: 'hash' };
const catalogPrompt = { id: 'mumu', name: '规划', description: '说明', category: '情节规划', body: '{{title}}', source_info: sourceInfo, source_label: 'MuMu', task_kind: 'outline', genre_tags: ['科幻'], enabled: true, builtin: true, novel_id: null, revision: 3 };

test('catalog filters combine source, use, task, genre, scope and original text search', () => {
  const original = { ...catalogPrompt, id: 'original', source_info: {} };
  const copy = { ...catalogPrompt, id: 'copy', builtin: false, novel_id: 'book-a' };
  const lite = { ...catalogPrompt, id: 'lite', source_info: { project: 'Ai-Novel Lite', compatibility: 'reference_only' }, task_kind: 'reference' };
  const items = [catalogPrompt, original, copy, lite];
  assert.deepEqual(filterPrompts(items, { source: 'original' }).map(p => p.id), ['original']);
  assert.deepEqual(filterPrompts(items, { source: 'MuMuAINovel' }).map(p => p.id), ['mumu', 'copy']);
  assert.deepEqual(filterPrompts(items, { source: 'custom' }).map(p => p.id), ['copy']);
  assert.deepEqual(filterPrompts(items, { source: 'Ai-Novel Lite', compatibility: 'reference_only' }).map(p => p.id), ['lite']);
  assert.deepEqual(filterPrompts(items, { source: 'MuMuAINovel', category: '情节规划', task: 'outline', tag: '科幻', scope: 'novel', novelId: 'book-a', compatibility: 'adapted', search: 'novel_title' }).map(p => p.id), ['copy']);
  assert.equal(promptSourceName(copy), 'MuMuAINovel');
  assert.equal(filterPrompts(items, { tag: '奇幻' }).length, 0);
});

test('references and reference-only source copies never enter task selectors', () => {
  const reference = { ...catalogPrompt, task_kind: 'reference' };
  const disguisedCopy = { ...catalogPrompt, builtin: false, source_info: { ...sourceInfo, compatibility: 'reference_only' } };
  assert.equal(runnablePrompt(reference), false);
  assert.equal(runnablePrompt(disguisedCopy), false);
  assert.deepEqual(matchingPrompts([reference], 'reference'), []);
  assert.deepEqual(matchingPrompts([disguisedCopy], 'outline'), []);
  assert.deepEqual(matchingPrompts([{ ...catalogPrompt, task_kind: 'unknown' }], 'unknown'), []);
});

test('save-as and history restore retain source original independently from current revision', () => {
  const copy = promptSavePayload(catalogPrompt, '科幻， 冒险', true);
  assert.equal(copy.id, undefined); assert.equal(copy.revision, undefined); assert.equal(copy.builtin, false);
  assert.deepEqual(copy.genre_tags, ['科幻', '冒险']); assert.deepEqual(copy.source_info, sourceInfo);
  const oldSource = { ...sourceInfo, commit: 'historical-source', original_body: '旧来源原文' };
  const restored = restorePromptFields({ ...catalogPrompt, revision: 8, novel_id: 'book-a' }, { body: '旧适配', revision: 1, source_info: oldSource });
  assert.equal(restored.revision, 8); assert.equal(restored.novel_id, 'book-a'); assert.deepEqual(restored.source_info, oldSource);
  assert.equal(restorePromptFields(catalogPrompt, { body: '无metadata旧版本' }).source_info, sourceInfo);
  assert.equal(catalogPrompt.source_info.commit, 'source-commit');
});

test('only canonical HTTPS GitHub repositories can become source links', () => {
  assert.equal(safeGithubRepository('https://github.com/owner/repo'), 'https://github.com/owner/repo');
  for (const value of ['javascript:alert(1)', 'http://github.com/owner/repo', 'https://github.com.evil.test/owner/repo', 'https://github.com@evil.test/owner/repo', 'https://user:pass@github.com/owner/repo', 'https://github.com:443/owner/repo', 'https://github.com/owner/repo?next=evil', 'https://github.com/owner/repo#fragment', 'https://github.com/owner/%2e%2e', 'https://github.com/owner/repo/<script>', '//github.com/owner/repo']) assert.equal(safeGithubRepository(value), undefined, value);
});

test('manual original selection focuses and selects the read-only text without writing', () => {
  const actions = [];
  const field = { value: sourceInfo.original_body, focus: () => actions.push('focus'), select: () => actions.push('select') };
  selectPromptText(field);
  assert.deepEqual(actions, ['focus', 'select']); assert.equal(field.value, sourceInfo.original_body);
});
