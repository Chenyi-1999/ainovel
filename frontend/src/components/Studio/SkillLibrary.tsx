import { matchingPrompts } from './studioPolicy';
import { useEffect, useState } from 'react';
import { Api, Chapter, Empty, Feedback, Header, Prompt, taskNames, useOperation } from './shared';
type Skill = { id: string; name: string; description: string; job_kind: string; inputs: any; outputs: any; steps: any[]; max_calls: number; permissions: string[]; requires_review: boolean };
const inputNames: Record<string, string> = { novel: '当前作品', instructions: '附加指令', chapter: '目标章节', count: '章节数', target_words: '每章字数', selection: '待改写原文', outline: '可编辑大纲', draft_chapters: '章节草稿', rewrite_proposal: '待审核改写', report: '审稿报告', memory_candidates: '待审核记忆候选' };
const describe = (value: any): string => Array.isArray(value) ? value.map(describe).join('、') : typeof value === 'string' ? inputNames[value] || value : JSON.stringify(value);
export default function SkillLibrary({ api, novelId, chapters, chapterId, prompts, busy: jobBusy, onRun }: { api: Api; novelId?: string; chapters: Chapter[]; chapterId?: string; prompts: Prompt[]; busy: boolean; onRun: (kind: string, payload: any) => void }) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selected, setSelected] = useState('outline');
  const [instructions, setInstructions] = useState('');
  const [template, setTemplate] = useState('');
  const [target, setTarget] = useState(chapterId || '');
  const [selection, setSelection] = useState('');
  const [words, setWords] = useState(1800);
  const [count, setCount] = useState(1);
  const { busy, error, run } = useOperation();
  useEffect(() => {
    run(async () => setSkills((await api<Skill[]>('/skills')).filter(s => Object.prototype.hasOwnProperty.call(taskNames, s.job_kind))));
  }, []);
  useEffect(() => {
    setTarget(chapterId || chapters[0]?.id || '');
  }, [chapterId, novelId]);
  const skill = skills.find(s => s.id === selected) || skills[0];
  const kind = skill?.job_kind || selected;
  const chapterRequired = ['rewrite', 'audit', 'confirm'].includes(kind);
  return <section className="section-card studio">
    <Header title="Skill 工作流" text="每个工作流连接实际创作任务。先选择用途，再核对参数与模型调用范围。" />
    <Feedback busy={busy} error={error} />
    <div className="studio-split">
      <div className="studio-list">{skills.map(s =>
        <button
          key={s.id}
          className={`studio-list-item ${skill?.id === s.id ? 'active' : ''}`}
          onClick={() => {
            setSelected(s.id);
            setTemplate('');
          }}>
          <b>{s.name}
          </b>
          <span>{s.description}
          </span>
          <small>最多 {s.max_calls} 次模型调用{s.requires_review ? ' · 需要人工审核' : ''}
          </small>
        </button>
      )}{!skills.length && <Empty>暂无可用工作流。</Empty>
        }
      </div>{skill && <div className="studio-detail">
        <h3>{skill.name}
        </h3>
        <p>{skill.description}
        </p>
        <ol className="studio-steps">{skill.steps.map((step, i) =>
          <li key={i}>{describe(step)}
          </li>
        )}
        </ol>
        <div className="studio-meta">
          <p>
            <b>必要输入</b> {describe(skill.inputs)}
          </p>
          <p>
            <b>产出</b> {describe(skill.outputs)}
          </p>
          <p>
            <b>调用上限</b> {skill.max_calls} 次 · {skill.permissions.includes('model.generate') ? '使用已配置模型' : skill.permissions.join('、')}
          </p>
        </div>
        <form
          className="studio-fields"
          onSubmit={e => {
            e.preventDefault();
            if (!novelId || !Object.prototype.hasOwnProperty.call(taskNames, kind) || (chapterRequired && !target)) return;
            const selectedTemplate = matchingPrompts(prompts, kind, novelId).find(p => p.id === template);
            onRun(kind, { skill_id: skill.id, prompt_template_id: selectedTemplate?.id || null, instructions, target_words: words, count, ...(chapterRequired ? { chapter_id: target } : {}), ...(kind === 'rewrite' ? { selection } : {}) });
          }}>
          <p className="studio-callout">点击执行会调用已配置的模型并计入用量。{kind === 'confirm' && '只提取候选；请到故事记忆中审核、编辑并采纳后定稿。'}{kind === 'rewrite' && '改写结果需在正文编辑页查看后替换。'}
          </p>{!novelId && <p className="studio-error">请先从书架选择一部作品。</p>
          }{chapterRequired && <label>目标章节<select required value={target} onChange={e => setTarget(e.target.value)}>
            <option value="">选择章节</option>{chapters.map(c =>
              <option key={c.id} value={c.id}>第 {c.number} 章 · {c.title}
              </option>
            )}
          </select>
          </label>
          }
          <label>提示词模板<select value={template} onChange={e => setTemplate(e.target.value)}>
            <option value="">使用默认提示词</option>{matchingPrompts(prompts, kind, novelId).map(p =>
              <option key={p.id} value={p.id}>{p.name}
              </option>
            )}
          </select>
          </label>{kind === 'write' && <div className="studio-form-row">
            <label>章节数<input
              type="number"
              min={1}
              max={20}
              value={count}
              onChange={e => setCount(Number(e.target.value))} />
            </label>
            <label>每章目标字数<input
              type="number"
              min={300}
              max={6000}
              step={100}
              value={words}
              onChange={e => setWords(Number(e.target.value))} />
            </label>
          </div>
          }{kind === 'rewrite' && <label>待改写原文<textarea
            required
            rows={5}
            value={selection}
            onChange={e => setSelection(e.target.value)}
            placeholder="粘贴所选章节中的连续原文" />
          </label>
          }
          <label>附加指令<textarea
            rows={4}
            value={instructions}
            onChange={e => setInstructions(e.target.value)}
            placeholder="可选，说明本次工作的具体要求" />
          </label>
          <button
            className="button primary"
            disabled={jobBusy || !novelId || (chapterRequired && !target) || (kind === 'rewrite' && !selection.trim())}>使用模型执行 · {taskNames[kind]}
          </button>
        </form>
      </div>
      }
    </div>
  </section>;
}
