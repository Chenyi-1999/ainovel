import { useRef, useState } from 'react';
import type { Prompt } from './shared';
import { promptSourceName, runnablePrompt, safeGithubRepository, selectPromptText } from './studioPolicy';

// Read-only, selectable text is always available, even when clipboard permissions are absent.
export function PromptText({ title, body }: { title: string; body: string }) {
  const field = useRef<HTMLTextAreaElement>(null);
  const [notice, setNotice] = useState('');
  return <div className="studio-source-text">
    <label>{title}<textarea ref={field} className="studio-code" aria-label={title} readOnly rows={10} value={body} spellCheck={false} /></label>
    <div className="studio-actions">
      <button className="button outline small" type="button" onClick={async () => {
        try {
          await navigator.clipboard.writeText(body);
          setNotice('已请求复制全文；也可点击全选正文后手动复制。');
        } catch { setNotice('自动复制不可用，请点击全选正文后手动复制。'); }
      }}>复制全文</button>
      <button className="button outline small" type="button" onClick={() => {
        if (field.current) selectPromptText(field.current);
        setNotice('已全选正文，可使用 Ctrl+C 或系统复制菜单。');
      }}>全选正文（手动复制）</button>
    </div>
    {notice && <small role="status">{notice}</small>}
  </div>;
}

export function PromptProvenance({ prompt }: { prompt: Prompt }) {
  const source = prompt.source_info;
  const repository = safeGithubRepository(source?.repository);
  return <div className="studio-source-meta">
    <div className="studio-actions">
      <span className="studio-badge">{promptSourceName(prompt)}{source?.project && !prompt.builtin ? ' · 用户副本' : ''}</span>
      <span className={`studio-badge ${runnablePrompt(prompt) ? '' : 'stale'}`}>{runnablePrompt(prompt) ? '可用于当前任务' : '原文参考（未接入任务）'}</span>
    </div>
    {source?.project && <>
      <dl>
        <div><dt>来源版本</dt><dd>{source.commit || '未提供'}</dd></div>
        <div><dt>原始名称 / 分类</dt><dd>{source.original_name || '未提供'} / {source.original_category || '未提供'}</dd></div>
        <div><dt>原文件</dt><dd>{source.path || '未提供'}</dd></div>
        <div><dt>来源标识</dt><dd>{source.key || '未提供'}</dd></div>
        <div><dt>许可</dt><dd>{source.license || '未提供'}</dd></div>
        <div><dt>来源仓库</dt><dd>{repository ? <a href={repository} target="_blank" rel="noopener noreferrer">{source.repository}</a> : source.repository || '未提供'}</dd></div>
      </dl>
      <p className="studio-callout">{source.adapter_note || '来源原文仅供查看和复制；是否可执行以适配状态为准。'}</p>
    </>}
  </div>;
}

export default function PromptSource({ prompt }: { prompt: Prompt }) {
  const source = prompt.source_info;
  if (!source?.project) return null;
  return <div className="studio-source">
    <p className="muted">以下内容按来源原样保留，仅作为文本展示，不执行源系统的指令语法或变量。</p>
    <div className="studio-source-parameters"><b>源系统变量（{source.parameters?.length || 0}）</b>
      <p>{source.parameters?.length ? source.parameters.join('、') : '无已记录变量'}</p>
      <small>这些变量属于源项目，不能直接在当前工作台替换。适配版仅支持 title、genre、style、instructions。</small>
    </div>
    {source.blocks?.length ? <section className="studio-source-blocks" aria-label="来源原文块">
      <h4>原预设的提示词块 · {source.blocks.length} 块</h4>
      <p className="muted">这些块共同组成一个预设，不是独立模板。按来源记录顺序展示，未启用的块也保留原文。</p>
      {source.blocks.map((block, index) => <details key={`${block.identifier || 'block'}-${index}`}>
        <summary>{index + 1}. {block.name || block.identifier || '未命名块'} · {block.role || '未标注角色'} · {block.enabled === true ? '已启用' : block.enabled === false ? '未启用' : '启用状态未标注'}</summary>
        <dl>
          <div><dt>标识</dt><dd>{block.identifier || '未提供'}</dd></div>
          <div><dt>注入顺序</dt><dd>{block.injection_order ?? '未标注'}</dd></div>
          <div><dt>原文件</dt><dd>{block.template_file || '未提供'}</dd></div>
          <div><dt>SHA256</dt><dd>{block.sha256 || '未提供'}</dd></div>
        </dl>
        <PromptText title={`第 ${index + 1} 块原文`} body={block.body || ''} />
      </details>)}
    </section> : null}
    <PromptText key={prompt.id} title="完整来源原文" body={source.original_body ?? prompt.body} />
    <small className="studio-source-hash">来源原文 SHA256：{source.raw_sha256 || '未提供'}</small>
  </div>;
}
