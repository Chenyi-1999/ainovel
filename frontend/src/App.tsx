import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  CircleHelp,
  Clipboard,
  Clock3,
  Download,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquarePen,
  Trash2,
  X,
  Check,
  LoaderCircle,
  CircleAlert,
  BookMarked,
  Coins,
  ListChecks,
  UsersRound,
  WandSparkles,
} from "lucide-react";

type Novel = {
  id: string;
  title?: string;
  premise?: string;
  genre?: string;
  style?: string;
  planned_chapters?: number;
  outline?: any;
  updated_at?: string;
};
type Chapter = {
  id: string;
  novel_id: string;
  number: number;
  title: string;
  content: string;
  status: "draft" | "confirmed";
  memory_dirty?: boolean;
  revision?: number;
  updated_at?: string;
};
type Job = {
  id: string;
  kind: string;
  status: string;
  chapter_id?: string;
  payload?: any;
  current?: number;
  count?: number;
  progress?: { current?: number; count?: number } | any;
  error?: string;
  result?: any;
  created_at?: string;
};
type Memory = {
  id: string;
  kind: string;
  content: string;
  source_chapter_id?: string;
  stale?: boolean;
};
type Page =
  | "manuscript"
  | "outline"
  | "memory"
  | "tasks"
  | "settings"
  | "usage";

const api = async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
  const res = await fetch(`/api${path}`, {
    credentials: "include",
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      detail = j.detail || j.error || detail;
    } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") || "";
  return (type.includes("json") ? await res.json() : await res.blob()) as T;
};
const labelKind = (kind: string) =>
  ({
    outline: "生成大纲",
    write: "续写章节",
    rewrite: "选段改写",
    audit: "审稿检查",
    confirm: "确认定稿",
  })[kind] || kind;
const statusLabel = (status: string) =>
  ({
    pending: "排队中",
    running: "生成中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已取消",
  })[status] || status;

function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [loginBusy, setLoginBusy] = useState(false);
  const [novels, setNovels] = useState<Novel[]>([]);
  const [novel, setNovel] = useState<Novel | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [page, setPage] = useState<Page>("manuscript");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [exportFrom, setExportFrom] = useState("");
  const [exportTo, setExportTo] = useState("");
  const [newPremise, setNewPremise] = useState("");
  const [newGenre, setNewGenre] = useState("");
  const [newStyle, setNewStyle] = useState("");
  const [editorTitle, setEditorTitle] = useState("");
  const [editorText, setEditorText] = useState("");
  const [instructions, setInstructions] = useState("");
  const [targetWords, setTargetWords] = useState("1800");
  const [chapterCount, setChapterCount] = useState("1");
  const [copyTitle, setCopyTitle] = useState(true);
  const [copyFallback, setCopyFallback] = useState("");
  const [selection, setSelection] = useState("");
  const [rewritePrompt, setRewritePrompt] = useState("");
  const [rewriteResult, setRewriteResult] = useState<string | null>(null);
  const [rewriteTarget, setRewriteTarget] = useState<{
    chapterId: string;
    revision?: number | string;
  } | null>(null);
  const [outlinePrompt, setOutlinePrompt] = useState("");
  const [outlineDraft, setOutlineDraft] = useState("");
  const [settings, setSettings] = useState<any>({});
  const [usage, setUsage] = useState<any>(null);
  const [models, setModels] = useState<string[]>([]);
  const [modelSource, setModelSource] = useState("provider");
  const [memoryDraft, setMemoryDraft] = useState({
    kind: "setting",
    content: "",
  });
  const [versions, setVersions] = useState<any[]>([]);
  const [showVersions, setShowVersions] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const saveTimer = useRef<number | undefined>(undefined);
  const jobStates = useRef<Record<string, string>>({});
  const dirtyRef = useRef(false);
  const chapterIdRef = useRef<string | undefined>(undefined);
  const novelIdRef = useRef<string | undefined>(undefined);

  const refreshNovels = useCallback(async () => {
    const data: any = await api("/novels");
    setNovels(Array.isArray(data) ? data : data.novels || []);
  }, []);
  const refreshForNovel = useCallback(async (id: string) => {
    const [n, c, j, m] = await Promise.all([
      api<Novel>(`/novels/${id}`),
      api<any>(`/novels/${id}/chapters`),
      api<any>(`/novels/${id}/jobs`),
      api<any>(`/novels/${id}/memories`),
    ]);
    if (novelIdRef.current !== id || dirtyRef.current) return;
    setNovel(n);
    setOutlineDraft(n.outline ? JSON.stringify(n.outline, null, 2) : "");
    const cs = Array.isArray(c) ? c : c.chapters || [];
    setChapters(cs);
    setJobs(Array.isArray(j) ? j : j.jobs || []);
    setMemories(Array.isArray(m) ? m : m.memories || []);
    const selectedId = chapterIdRef.current;
    const fresh = selectedId
      ? cs.find((x: Chapter) => x.id === selectedId)
      : cs[0];
    setChapter(fresh || null);
  }, []);
  useEffect(() => {
    api("/me")
      .then(async () => {
        setAuthenticated(true);
        await refreshNovels();
      })
      .catch(() => setAuthenticated(false));
  }, [refreshNovels]);
  useEffect(() => {
    if (!authenticated) return;
    api<any>("/settings")
      .then(setSettings)
      .catch((e) => setError(e.message));
    api<any>("/models")
      .then((x) => {
        setModels(x.models || []);
        setModelSource(x.source || "provider");
      })
      .catch(() => {});
  }, [authenticated]);
  useEffect(() => {
    if (novel) refreshForNovel(novel.id).catch((e) => setError(e.message));
  }, [novel?.id]);
  useEffect(() => {
    if (!novel) return;
    const novelId = novel.id;
    const timer = window.setInterval(
      () =>
        api<any>(`/novels/${novelId}/jobs`)
          .then(async (x) => {
            if (novelIdRef.current !== novelId) return;
            const next: Job[] = Array.isArray(x) ? x : x.jobs || [];
            setJobs(next);
            const finished = next.some(
              (j) =>
                j.status === "succeeded" &&
                jobStates.current[j.id] !== "succeeded",
            );
            if (finished && !dirtyRef.current) {
              const [c, m, n]: any[] = await Promise.all([
                api(`/novels/${novelId}/chapters`),
                api(`/novels/${novelId}/memories`),
                api<Novel>(`/novels/${novelId}`),
              ]);
              if (novelIdRef.current !== novelId || dirtyRef.current) return;
              const cs = Array.isArray(c) ? c : c.chapters || [];
              const ms = Array.isArray(m) ? m : m.memories || [];
              const outlineFinished = next.some(
                (j) =>
                  j.kind === "outline" &&
                  j.status === "succeeded" &&
                  jobStates.current[j.id] !== "succeeded",
              );
              setChapters(cs);
              setMemories(ms);
              setNovel(n);
              if (outlineFinished)
                setOutlineDraft(
                  n.outline ? JSON.stringify(n.outline, null, 2) : "",
                );
              const activeChapterId = chapterIdRef.current;
              const fresh = activeChapterId
                ? cs.find((item: Chapter) => item.id === activeChapterId)
                : cs[0];
              if (fresh) {
                setChapter(fresh);
                setEditorTitle(fresh.title || `第${fresh.number}章`);
                setEditorText(fresh.content || "");
              }
              next.forEach((j) => (jobStates.current[j.id] = j.status));
            }
          })
          .catch(() => {}),
      2500,
    );
    return () => clearInterval(timer);
  }, [novel?.id]);
  useEffect(() => {
    setVersions([]);
    setShowVersions(false);
    setRewriteResult(null);
    setRewriteTarget(null);
    if (chapter) {
      setEditorTitle(chapter.title || `第${chapter.number}章`);
      setEditorText(chapter.content || "");
    } else {
      setEditorTitle("");
      setEditorText("");
    }
  }, [chapter?.id]);
  useEffect(() => {
    if (novel && page === "usage")
      api<any>(`/novels/${novel.id}/usage`)
        .then(setUsage)
        .catch((e) => setError(e.message));
  }, [novel?.id, page]);
  useEffect(
    () => () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    },
    [],
  );
  const activeJobs = jobs.filter((j) =>
    ["pending", "running"].includes(j.status),
  );
  const editingLocked = activeJobs.length > 0;
  const currentChapterIndex = chapters.findIndex((x) => x.id === chapter?.id);
  const dirty =
    !!chapter &&
    (editorText !== (chapter.content || "") ||
      editorTitle !== (chapter.title || ""));
  dirtyRef.current = dirty;
  chapterIdRef.current = chapter?.id;
  novelIdRef.current = novel?.id;
  const outlineText = useMemo(
    () => JSON.stringify(novel?.outline || {}, null, 2),
    [novel?.outline],
  );
  const outlineObject = useMemo(() => {
    try {
      return JSON.parse(outlineDraft || outlineText || "{}");
    } catch {
      return {};
    }
  }, [outlineDraft, outlineText]);
  const updateOutlineField = (key: string, value: string) =>
    setOutlineDraft(
      JSON.stringify({ ...outlineObject, [key]: value }, null, 2),
    );

  const login = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoginBusy(true);
    setError("");
    try {
      await api("/login", {
        method: "POST",
        body: JSON.stringify({ password }),
      });
      setAuthenticated(true);
      await refreshNovels();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoginBusy(false);
    }
  };
  const logout = async () => {
    try {
      await api("/logout", { method: "POST" });
    } catch {}
    setAuthenticated(false);
    setNovel(null);
    setNovels([]);
  };
  const openNovel = async (n: Novel) => {
    if (busy) return;
    if (n.id === novel?.id) {
      setPage("manuscript");
      setMobileOpen(false);
      return;
    }
    if (
      dirty &&
      !confirm("当前章节有未保存的修改，切换作品会放弃这些修改。仍要切换吗？")
    )
      return;
    setError("");
    setOutlineDraft("");
    setJobs([]);
    setChapters([]);
    setNovel(n);
    setChapter(null);
    setPage("manuscript");
    setMobileOpen(false);
  };
  const createNovel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPremise.trim()) return;
    setBusy(true);
    setError("");
    try {
      const n = await api<Novel>("/novels", {
        method: "POST",
        body: JSON.stringify({
          premise: newPremise,
          genre: newGenre || undefined,
          style: newStyle || undefined,
        }),
      });
      await refreshNovels();
      setNovel(n);
      setChapter(null);
      setShowNew(false);
      setPage("outline");
      setOutlinePrompt("");
      setNotice("小说已建立，接下来可以生成大纲。");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const newBlankChapter = async () => {
    if (!novel || editingLocked) return;
    setBusy(true);
    setError("");
    try {
      if (dirty && chapter) {
        const saved = await api<Chapter>(`/chapters/${chapter.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            title: editorTitle,
            content: editorText,
            revision: chapter.revision,
          }),
        });
        setChapters((xs) => xs.map((c) => (c.id === saved.id ? saved : c)));
        setChapter((current) => (current?.id === saved.id ? saved : current));
      }
      const created = await api<Chapter>(`/novels/${novel.id}/chapters`, {
        method: "POST",
        body: JSON.stringify({ content: "" }),
      });
      setChapters((xs) => [...xs, created]);
      setChapter(created);
      setNotice("已新建空白章节，可以粘贴或输入正文。");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const createJob = async (kind: string, extra: any = {}) => {
    if (!novel) return;
    if (activeJobs.length) {
      setError("当前已有生成任务，请等待完成或先停止任务。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      if (dirty && chapter) {
        const updated = await api<Chapter>(`/chapters/${chapter.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            title: editorTitle,
            content: editorText,
            revision: chapter.revision,
          }),
        });
        setChapter(updated);
        setChapters((x) => x.map((c) => (c.id === updated.id ? updated : c)));
      }
      const job = await api<Job>(`/novels/${novel.id}/jobs`, {
        method: "POST",
        body: JSON.stringify({ kind, ...extra }),
      });
      setJobs((x) => [job, ...x]);
      setPage("tasks");
      setNotice(`${labelKind(kind)}任务已加入队列。`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const saveChapter = async () => {
    if (!chapter || editingLocked) return;
    const targetId = chapter.id;
    setBusy(true);
    setError("");
    try {
      const updated = await api<Chapter>(`/chapters/${targetId}`, {
        method: "PATCH",
        body: JSON.stringify({
          title: editorTitle,
          content: editorText,
          revision: chapter.revision,
        }),
      });
      setChapter((current) => (current?.id === updated.id ? updated : current));
      setChapters((x) => x.map((c) => (c.id === updated.id ? updated : c)));
      setNotice("章节已保存。");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const scheduleSave = () => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
  };
  const saveOutline = async () => {
    if (!novel || busy) return;
    const id = novel.id;
    setBusy(true);
    try {
      const outline = JSON.parse(outlineDraft || outlineText);
      if (!outline || typeof outline !== "object" || Array.isArray(outline))
        throw new Error("大纲内容格式不正确。");
      const n = await api<Novel>(`/novels/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ outline, title: outline.title || novel.title }),
      });
      if (novelIdRef.current === id) {
        setNovel(n);
        setNotice("大纲已保存。");
      }
      await refreshNovels();
    } catch (e: any) {
      setError(
        e instanceof SyntaxError
          ? "完整大纲数据格式有误，请检查后保存。"
          : e.message,
      );
    } finally {
      setBusy(false);
    }
  };
  const selectChapter = (c: Chapter) => {
    if (busy || c.id === chapter?.id) return;
    if (
      dirty &&
      !confirm("当前章节有未保存的修改，切换章节会放弃这些修改。仍要切换吗？")
    )
      return;
    setChapter(c);
    setPage("manuscript");
  };
  const copyText = async () => {
    const heading = chapter
      ? `第${chapter.number}章${editorTitle ? ` ${editorTitle}` : ""}`
      : editorTitle;
    const text = `${copyTitle && heading ? heading + "\n\n" : ""}${editorText}`;
    try {
      await navigator.clipboard.writeText(text);
      setCopyFallback("");
      setNotice("正文已复制，可以粘贴到发布平台。");
    } catch {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      area.style.pointerEvents = "none";
      document.body.appendChild(area);
      area.focus();
      area.select();
      let copied = false;
      try {
        copied = document.execCommand("copy");
      } catch {}
      area.remove();
      if (copied) {
        setCopyFallback("");
        setNotice("正文已复制，可以粘贴到发布平台。");
      } else {
        setCopyFallback(text);
        setNotice("浏览器未允许自动复制，请从下方框中手动复制。");
      }
    }
  };
  const loadVersions = async () => {
    if (!chapter) return;
    const targetId = chapter.id;
    try {
      const data: any = await api(`/chapters/${targetId}/versions`);
      if (chapterIdRef.current !== targetId) return;
      setVersions(Array.isArray(data) ? data : data.versions || []);
      setShowVersions((v) => !v);
    } catch (e: any) {
      if (chapterIdRef.current === targetId) setError(e.message);
    }
  };
  const exportNovel = async (format: "txt" | "md") => {
    if (!novel) return;
    try {
      const params = new URLSearchParams({ format });
      if (exportFrom) params.set("from_chapter", exportFrom);
      if (exportTo) params.set("to_chapter", exportTo);
      const blob = await api<Blob>(`/novels/${novel.id}/export?${params}`);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${novel.title || "小说"}${exportFrom || exportTo ? `-${exportFrom || 1}-${exportTo || chapters.length}` : ""}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
      setShowExport(false);
    } catch (e: any) {
      setError(e.message);
    }
  };
  const selectedText = () => {
    const el = textarea.current;
    if (!el) return;
    const value = el.value.slice(el.selectionStart, el.selectionEnd);
    setSelection(value);
    setRewriteResult(null);
  };
  const jobAction = async (id: string, action: string) => {
    try {
      const j = await api<Job>(`/jobs/${id}/${action}`, { method: "POST" });
      setJobs((xs) => xs.map((x) => (x.id === id ? j : x)));
    } catch (e: any) {
      setError(e.message);
    }
  };
  const applyRewrite = async () => {
    if (!chapter || rewriteResult === null || !rewriteTarget) return;
    if (dirty) {
      setError("请先保存当前章节，再应用改写稿。");
      return;
    }
    if (
      rewriteTarget.chapterId !== chapter.id ||
      (rewriteTarget.revision !== undefined &&
        rewriteTarget.revision !== chapter.revision)
    ) {
      setError("这份改写基于较早版本或其他章节，请重新生成后再应用。");
      return;
    }
    setEditorText(rewriteResult);
    setRewriteResult(null);
    setNotice("改写稿已放入编辑器，保存后生效。");
  };
  const applyJobResult = (job: Job) => {
    if (job.kind === "rewrite" && job.result?.content) {
      const target =
        job.chapter_id || job.payload?.chapter_id || job.result.chapter_id;
      if (!chapter || (target && target !== chapter.id)) {
        setError("请先打开生成改写时对应的章节，再查看这份改写稿。");
        return;
      }
      if (dirty) {
        setError("请先保存当前章节，再查看改写稿。");
        return;
      }
      if (
        job.result.expected_revision !== undefined &&
        job.result.expected_revision !== chapter.revision
      ) {
        setError("当前章节已有更新，这份改写已过期。请重新生成。");
        return;
      }
      setRewriteTarget({
        chapterId: chapter.id,
        revision: job.result.expected_revision,
      });
      setRewriteResult(job.result.content);
      setSelection("");
      setPage("manuscript");
    } else if (job.kind === "outline" && job.result) {
      setNovel((v) => (v ? { ...v, outline: job.result } : v));
      setOutlineDraft(JSON.stringify(job.result, null, 2));
      setPage("outline");
    }
  };
  const saveSettings = async () => {
    setBusy(true);
    try {
      const next = await api("/settings", {
        method: "PATCH",
        body: JSON.stringify(settings),
      });
      setSettings(next);
      setNotice("模型设置已保存。");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (authenticated === null)
    return (
      <div className="loading-screen">
        <span className="brand-mark">
          <BookOpen />
        </span>
        <p>正在打开你的书桌…</p>
      </div>
    );
  if (!authenticated)
    return (
      <main className="login-page">
        <div className="login-card">
          <div className="brand-lockup">
            <span className="brand-mark">
              <BookOpen />
            </span>
            <div>
              <b>纸间</b>
              <small>小说工作台</small>
            </div>
          </div>
          <div className="login-art">
            <div className="art-line">
              留住灵感，
              <br />
              <em>写成故事。</em>
            </div>
            <div className="leaf-mark">✳</div>
          </div>
          <h1>欢迎回来</h1>
          <p className="muted">输入工作台密码，继续你的创作。</p>
          <form onSubmit={login}>
            <label htmlFor="password">访问密码</label>
            <input
              autoComplete="current-password"
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button className="button primary wide" disabled={loginBusy}>
              {loginBusy ? (
                <LoaderCircle className="spin" />
              ) : (
                <ShieldCheck size={17} />
              )}
              进入工作台
            </button>
            {error && <div className="error-line">{error}</div>}
          </form>
          <p className="privacy-note">
            <ShieldCheck size={14} />
            作品保存在你的私人工作区
          </p>
        </div>
      </main>
    );

  const navItem = (key: Page, label: string, Icon: any, count?: number) => (
    <button
      className={`nav-item ${page === key ? "selected" : ""}`}
      key={key}
      onClick={() => {
        setPage(key);
        setMobileOpen(false);
      }}
    >
      <Icon size={17} />
      <span>{label}</span>
      {count ? <i className="nav-count">{count}</i> : null}
    </button>
  );
  return (
    <div className="app-shell">
      {mobileOpen && (
        <button
          className="scrim"
          aria-label="关闭导航"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
        <div className="brand-lockup">
          <span className="brand-mark">
            <BookOpen size={19} />
          </span>
          <div>
            <b>纸间</b>
            <small>小说工作台</small>
          </div>
          <button
            className="icon-button sidebar-close"
            aria-label="关闭导航"
            onClick={() => setMobileOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <button
          className="new-book"
          onClick={() => {
            setShowNew(true);
            setMobileOpen(false);
          }}
        >
          <Plus size={17} />
          新建小说
        </button>
        <div className="side-heading">
          <span>我的书架</span>
          <button
            className="icon-button tiny"
            aria-label="新建小说"
            onClick={() => setShowNew(true)}
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="book-list">
          {novels.length ? (
            novels.map((n) => (
              <button
                key={n.id}
                className={`book-item ${novel?.id === n.id ? "active" : ""}`}
                onClick={() => openNovel(n)}
              >
                <BookMarked size={16} />
                <span>
                  {n.title || n.premise?.slice(0, 18) || "未命名小说"}
                </span>
                {novel?.id === n.id && <span className="book-dot" />}
              </button>
            ))
          ) : (
            <div className="empty-shelf">
              你的书架还是空的。
              <br />
              从几句话开始吧。
            </div>
          )}
        </div>
        <div className="side-heading workspace-heading">
          <span>工作区</span>
        </div>
        <nav className="nav-list">
          {navItem("manuscript", "正文编辑", SquarePen)}
          {navItem("outline", "故事大纲", LayoutDashboard)}
          {navItem("memory", "故事记忆", UsersRound)}
          {navItem("tasks", "生成任务", ListChecks, activeJobs.length)}
        </nav>
        <div className="side-bottom">
          <div className="usage-mini">
            <div className="usage-mini-icon">
              <Coins size={16} />
            </div>
            <div>
              <b>创作统计</b>
              <small>
                {novels.length} 部作品 · {chapters.length} 个章节
              </small>
            </div>
          </div>
          <nav className="nav-list">
            {navItem("settings", "模型设置", Settings2)}
            {navItem("usage", "用量记录", Clock3)}
          </nav>
          <button className="profile-row" onClick={logout}>
            <span className="avatar">作</span>
            <span className="profile-copy">
              <b>我的工作区</b>
              <small>安全退出</small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <main className="main-area">
        <header className="topbar">
          <div className="top-left">
            <button
              className="icon-button mobile-menu"
              aria-label="打开导航"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={20} />
            </button>
            <span className="breadcrumb">我的书架</span>
            <span className="crumb-slash" aria-hidden="true">
              /
            </span>
            <b>{novel?.title || "创作空间"}</b>
          </div>
          <div className="top-right">
            <span className="autosave">
              <span className="live-dot" />
              {dirty ? "有未保存更改" : "已同步"}
            </span>
            <button
              className="icon-button"
              title="帮助"
              aria-label="帮助"
              onClick={() =>
                setNotice(
                  "先创建小说，再生成大纲与章节。修改正文后点击保存；确认定稿会更新故事记忆。复制和导出可用于发布。",
                )
              }
            >
              <CircleHelp size={18} />
            </button>
            <span className="avatar small-avatar">作</span>
          </div>
        </header>
        <div className="page-scroll">
          <div className="content-wrap">
            {copyFallback && (
              <div className="copy-fallback">
                <label htmlFor="copy-fallback-text">手动复制正文</label>
                <textarea
                  id="copy-fallback-text"
                  readOnly
                  value={copyFallback}
                  onFocus={(e) => e.currentTarget.select()}
                />
                <button
                  className="button outline small"
                  onClick={() => setCopyFallback("")}
                >
                  关闭
                </button>
              </div>
            )}
            {error && (
              <div className="alert error-alert">
                <CircleAlert size={17} />
                <span>{error}</span>
                <button onClick={() => setError("")} aria-label="关闭错误">
                  <X size={16} />
                </button>
              </div>
            )}
            {notice && (
              <div className="alert success-alert">
                <Check size={16} />
                <span>{notice}</span>
                <button onClick={() => setNotice("")} aria-label="关闭提示">
                  <X size={16} />
                </button>
              </div>
            )}
            {page === "settings" && (
              <section className="section-card settings-page">
                <div className="section-intro">
                  <div className="section-icon">
                    <Settings2 size={20} />
                  </div>
                  <div>
                    <h2>模型设置</h2>
                    <p>
                      配置模型服务和不同创作环节使用的模型。密钥仅由服务端保管。
                    </p>
                  </div>
                </div>
                <div className="security-callout">
                  <ShieldCheck size={18} />
                  <div>
                    <b>API 密钥已在服务器端配置</b>
                    <span>
                      {settings.has_api_key
                        ? "密钥已保存，不会显示在此页面。"
                        : "尚未检测到密钥，请在服务器环境配置后再生成。"}
                    </span>
                  </div>
                </div>
                <label htmlFor="base-url">接口地址</label>
                <input
                  id="base-url"
                  value={settings.base_url || ""}
                  onChange={(e) =>
                    setSettings({ ...settings, base_url: e.target.value })
                  }
                  placeholder="https://api.example.com/v1"
                />
                <div className="settings-grid">
                  {[
                    ["outline_model", "大纲模型"],
                    ["writing_model", "正文模型"],
                    ["review_model", "审稿模型"],
                    ["memory_model", "记忆模型"],
                  ].map(([key, label]) => (
                    <div key={key}>
                      <label htmlFor={key}>{label}</label>
                      <input
                        list="models"
                        id={key}
                        value={settings[key] || ""}
                        onChange={(e) =>
                          setSettings({ ...settings, [key]: e.target.value })
                        }
                        placeholder="输入模型名称"
                      />
                    </div>
                  ))}
                </div>
                <datalist id="models">
                  {models.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
                <div className="settings-grid">
                  <div>
                    <label htmlFor="temperature">
                      {settings.transport === "claude_cli"
                        ? "创作温度（客户端通道不适用）"
                        : "创作温度"}
                    </label>
                    <input
                      id="temperature"
                      disabled={settings.transport === "claude_cli"}
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={settings.temperature ?? 0.8}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          temperature: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div>
                    <label htmlFor="price-in">输入价格 / 百万 tokens</label>
                    <input
                      id="price-in"
                      type="number"
                      min="0"
                      step="0.01"
                      value={settings.input_price_per_million ?? ""}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          input_price_per_million: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                  <div>
                    <label htmlFor="price-out">输出价格 / 百万 tokens</label>
                    <input
                      id="price-out"
                      type="number"
                      min="0"
                      step="0.01"
                      value={settings.output_price_per_million ?? ""}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          output_price_per_million: Number(e.target.value),
                        })
                      }
                    />
                  </div>
                </div>
                <div className="save-settings">
                  <span>
                    {settings.transport === "claude_cli"
                      ? "当前通过真实 Claude Code 客户端调用。候选名称来自配置，实际可用模型以平台列表为准。"
                      : modelSource === "catalog"
                        ? "当前使用直接 API 调用。目录中的模型不代表已开通，请填写账号已开通的 Model ID 或 Endpoint ID。"
                        : "当前使用直接 API 调用。模型名称可以根据服务商控制台填写。"}
                  </span>
                  <button
                    className="button primary"
                    onClick={saveSettings}
                    disabled={busy}
                  >
                    <Save size={16} />
                    保存设置
                  </button>
                </div>
              </section>
            )}
            {page === "settings" ? null : !novel ? (
              <section className="welcome-panel">
                <div className="welcome-copy">
                  <span className="eyebrow">写作，从一句话开始</span>
                  <h1>
                    把脑海里的故事，
                    <br />
                    <em>慢慢写出来。</em>
                  </h1>
                  <p>
                    先说说你想写什么。纸间帮你搭起故事骨架，再陪你写完每一章。
                  </p>
                  <button
                    className="button primary"
                    onClick={() => setShowNew(true)}
                  >
                    <Sparkles size={17} />
                    开始一部新小说
                  </button>
                  <div className="welcome-proof">
                    <span>
                      <Check size={14} />
                      大纲可随时修改
                    </span>
                    <span>
                      <Check size={14} />
                      章节自动保存
                    </span>
                    <span>
                      <Check size={14} />
                      一键复制发布
                    </span>
                  </div>
                </div>
                <div className="welcome-illustration">
                  <div className="paper-sheet">
                    <div className="paper-stamp">
                      STORY
                      <br />
                      NO. 01
                    </div>
                    <span className="paper-label">灵感碎片</span>
                    <div className="paper-script">
                      那天雨下得
                      <br />
                      很大，整个城
                      <br />
                      市都在等一个
                      <br />
                      <i>不会回来的人。</i>
                    </div>
                    <div className="paper-rule" />
                    <div className="paper-rule short" />
                    <div className="paper-foot">从这里，开始一个故事</div>
                  </div>
                  <div className="sprig">✳</div>
                </div>
              </section>
            ) : (
              <>
                <div className="novel-heading">
                  <div>
                    <div className="eyebrow">
                      {novel.genre || "我的作品"}{" "}
                      <span className="eyebrow-dot" aria-hidden="true">
                        ·
                      </span>{" "}
                      {chapters.length} 个章节
                    </div>
                    <h1>
                      {novel.title ||
                        novel.premise?.slice(0, 42) ||
                        "未命名小说"}
                    </h1>
                    <p>{novel.premise}</p>
                  </div>
                  <div className="heading-actions">
                    {page === "manuscript" && (
                      <>
                        <label className="generate-option">
                          每次{" "}
                          <select
                            aria-label="每次生成章节数"
                            value={chapterCount}
                            onChange={(e) => setChapterCount(e.target.value)}
                          >
                            {[1, 2, 3, 5, 10, 20].map((n) => (
                              <option key={n} value={n}>
                                {n} 章
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="generate-option">
                          每章约{" "}
                          <input
                            aria-label="每章目标字数"
                            type="number"
                            min="300"
                            max="6000"
                            step="100"
                            value={targetWords}
                            onChange={(e) => setTargetWords(e.target.value)}
                          />{" "}
                          字
                        </label>
                        {chapter && (
                          <button
                            className="button outline"
                            onClick={() =>
                              createJob("audit", { chapter_id: chapter.id })
                            }
                            disabled={busy || editingLocked}
                          >
                            <ShieldCheck size={16} />
                            审稿检查
                          </button>
                        )}
                      </>
                    )}
                    <button
                      className="button soft"
                      onClick={() => setShowExport(true)}
                    >
                      <Download size={16} />
                      导出
                    </button>
                    <button
                      className="button primary"
                      onClick={() =>
                        page === "outline"
                          ? createJob("outline", {
                              instructions: outlinePrompt,
                            })
                          : createJob("write", {
                              count: Number(chapterCount) || 1,
                              instructions,
                              target_words: Number(targetWords) || 1800,
                            })
                      }
                      disabled={busy || activeJobs.length > 0}
                    >
                      <WandSparkles size={16} />
                      {page === "outline" ? "生成大纲" : "写下一章"}
                    </button>
                  </div>
                </div>
                <div className="tabs">
                  {(["manuscript", "outline", "memory", "tasks"] as Page[]).map(
                    (p) => (
                      <button
                        key={p}
                        className={page === p ? "tab active" : "tab"}
                        onClick={() => setPage(p)}
                      >
                        {p === "manuscript"
                          ? "正文编辑"
                          : p === "outline"
                            ? "故事大纲"
                            : p === "memory"
                              ? "故事记忆"
                              : `生成任务${activeJobs.length ? ` · ${activeJobs.length}` : ""}`}
                      </button>
                    ),
                  )}
                </div>
                {page === "manuscript" && (
                  <div className="editor-layout">
                    <aside className="chapter-rail">
                      <div className="rail-title">
                        <b>章节目录</b>
                        <div>
                          <button
                            className="text-button new-chapter-button"
                            title="新建空白章"
                            disabled={editingLocked || busy}
                            onClick={newBlankChapter}
                          >
                            空白章
                          </button>
                          <button
                            className="icon-button tiny"
                            aria-label="生成下一章"
                            title="生成下一章"
                            disabled={editingLocked}
                            onClick={() =>
                              createJob("write", {
                                count: Number(chapterCount) || 1,
                                instructions,
                                target_words: Number(targetWords) || 1800,
                              })
                            }
                          >
                            <Plus size={16} />
                          </button>
                        </div>
                      </div>
                      <div className="chapter-list">
                        {chapters.length ? (
                          chapters.map((c) => (
                            <button
                              key={c.id}
                              onClick={() => selectChapter(c)}
                              className={`chapter-row ${chapter?.id === c.id ? "active" : ""}`}
                            >
                              <span className="chapter-index">
                                {String(c.number).padStart(2, "0")}
                              </span>
                              <span className="chapter-name">
                                <b>{c.title || `第${c.number}章`}</b>
                                <small>
                                  {c.status === "confirmed" ? "已定稿" : "草稿"}
                                  {c.memory_dirty ? " · 记忆待更新" : ""}
                                </small>
                              </span>
                            </button>
                          ))
                        ) : (
                          <div className="empty-chapters">
                            <FileText size={22} />
                            <span>
                              大纲生成后，
                              <br />
                              这里会出现章节。
                            </span>
                          </div>
                        )}
                      </div>
                    </aside>
                    <section className="editor-card">
                      <div className="editor-toolbar">
                        <div className="doc-label">
                          <span className="doc-icon">
                            <FileText size={17} />
                          </span>
                          <span>
                            <b>
                              {chapter ? `第 ${chapter.number} 章` : "尚未开始"}
                            </b>
                            <small>
                              {chapter
                                ? chapter.status === "confirmed"
                                  ? "已确认定稿"
                                  : `第 ${chapter.revision || 1} 版草稿`
                                : "先生成大纲，再开始写作"}
                            </small>
                          </span>
                        </div>
                        <div className="toolbar-actions">
                          <label className="copy-option">
                            <input
                              type="checkbox"
                              checked={copyTitle}
                              onChange={(e) => setCopyTitle(e.target.checked)}
                            />
                            复制标题
                          </label>
                          <button
                            className="button outline small"
                            disabled={!chapter || !editorText}
                            onClick={copyText}
                          >
                            <Clipboard size={15} />
                            复制正文
                          </button>
                          <button
                            className="button primary small"
                            disabled={!dirty || busy}
                            onClick={saveChapter}
                          >
                            <Save size={15} />
                            {busy ? "保存中" : "保存"}
                          </button>
                        </div>
                      </div>
                      {chapter ? (
                        <>
                          <div className="title-input-wrap">
                            <label htmlFor="chapter-title">章节标题</label>
                            <input
                              id="chapter-title"
                              disabled={editingLocked}
                              value={editorTitle}
                              onChange={(e) => {
                                setEditorTitle(e.target.value);
                                scheduleSave();
                              }}
                              placeholder="为这一章起个标题"
                            />
                          </div>
                          <textarea
                            ref={textarea}
                            disabled={editingLocked}
                            className="manuscript"
                            aria-label="章节正文"
                            value={editorText}
                            onChange={(e) => {
                              setEditorText(e.target.value);
                              scheduleSave();
                            }}
                            onMouseUp={selectedText}
                            onKeyUp={selectedText}
                            placeholder="从这里开始写下这一章……"
                          />
                          <div className="editor-foot">
                            <span>
                              {editorText.length.toLocaleString()} 字符 · 约{" "}
                              {Math.max(1, Math.ceil(editorText.length / 450))}{" "}
                              分钟阅读
                              {editingLocked
                                ? " · 任务进行中，暂时锁定编辑"
                                : ""}
                            </span>
                            <div>
                              <button
                                className="text-button"
                                onClick={loadVersions}
                              >
                                <Clock3 size={15} />
                                历史版本
                              </button>
                              <button
                                className="text-button"
                                onClick={() =>
                                  createJob("audit", { chapter_id: chapter.id })
                                }
                                disabled={busy || editingLocked}
                              >
                                <ShieldCheck size={15} />
                                审稿检查
                              </button>
                              <button
                                className="text-button"
                                onClick={() =>
                                  createJob("confirm", {
                                    chapter_id: chapter.id,
                                  })
                                }
                                disabled={
                                  (chapter.status === "confirmed" &&
                                    !chapter.memory_dirty) ||
                                  busy ||
                                  editingLocked
                                }
                              >
                                <Check size={15} />
                                {chapter.memory_dirty
                                  ? "更新故事记忆"
                                  : "确认定稿"}
                              </button>
                              <button
                                className="text-button"
                                onClick={() => {
                                  setRewritePrompt("");
                                  setPage("manuscript");
                                  document
                                    .getElementById("rewrite-panel")
                                    ?.scrollIntoView({ behavior: "smooth" });
                                }}
                                disabled={editingLocked}
                              >
                                <WandSparkles size={15} />
                                选段改写
                              </button>
                            </div>
                          </div>
                          {showVersions && (
                            <div className="version-list">
                              <div className="version-head">
                                <b>章节历史</b>
                                <button
                                  className="icon-button tiny"
                                  aria-label="关闭历史版本"
                                  onClick={() => setShowVersions(false)}
                                >
                                  <X size={16} />
                                </button>
                              </div>
                              {versions.length ? (
                                versions.map((v: any, i: number) => (
                                  <div className="version-row" key={v.id || i}>
                                    <div>
                                      <b>第 {v.revision || i + 1} 版</b>
                                      <small>
                                        {v.created_at
                                          ? new Date(
                                              v.created_at,
                                            ).toLocaleString("zh-CN")
                                          : ""}
                                      </small>
                                    </div>
                                    <button
                                      className="button outline small"
                                      onClick={() => {
                                        setEditorTitle(v.title || editorTitle);
                                        setEditorText(v.content || "");
                                        setShowVersions(false);
                                        setNotice(
                                          "历史版本已载入编辑器，保存后生效。",
                                        );
                                      }}
                                    >
                                      载入
                                    </button>
                                  </div>
                                ))
                              ) : (
                                <div className="empty-state">
                                  还没有历史版本。
                                </div>
                              )}
                            </div>
                          )}
                          <div className="rewrite-panel" id="rewrite-panel">
                            <div>
                              <b>
                                <Sparkles size={16} />
                                局部改写
                              </b>
                              <span>选中正文片段后写下修改要求。</span>
                            </div>
                            <div className="rewrite-selected">
                              {selection || "还没有选中内容，将改写整章。"}
                            </div>
                            <div className="rewrite-controls">
                              <input
                                aria-label="改写要求"
                                value={rewritePrompt}
                                onChange={(e) =>
                                  setRewritePrompt(e.target.value)
                                }
                                placeholder="例如：节奏更紧凑，保留人物语气"
                              />
                              <button
                                className="button soft small"
                                disabled={busy}
                                onClick={() =>
                                  createJob("rewrite", {
                                    chapter_id: chapter.id,
                                    selection: selection || undefined,
                                    instructions: rewritePrompt,
                                  })
                                }
                              >
                                <WandSparkles size={15} />
                                生成改写
                              </button>
                            </div>
                            {rewriteResult !== null && (
                              <div className="rewrite-result">
                                <label>改写建议</label>
                                <textarea
                                  value={rewriteResult}
                                  onChange={(e) =>
                                    setRewriteResult(e.target.value)
                                  }
                                />
                                <div className="result-actions">
                                  <button
                                    className="button outline small"
                                    onClick={() => setRewriteResult(null)}
                                  >
                                    舍弃
                                  </button>
                                  <button
                                    className="button primary small"
                                    onClick={applyRewrite}
                                  >
                                    <Check size={15} />
                                    放入正文
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        </>
                      ) : (
                        <div className="editor-empty">
                          <div className="empty-icon">
                            <SquarePen size={22} />
                          </div>
                          <h3>故事还在等第一行</h3>
                          <p>先写几句话生成大纲，再从第一章开始。</p>
                          <button
                            className="button primary"
                            onClick={() => setPage("outline")}
                          >
                            <LayoutDashboard size={16} />
                            查看故事大纲
                          </button>
                        </div>
                      )}
                    </section>
                  </div>
                )}
                {page === "outline" && (
                  <section className="section-card outline-page">
                    <div className="section-intro">
                      <div className="section-icon">
                        <LayoutDashboard size={20} />
                      </div>
                      <div>
                        <h2>故事大纲</h2>
                        <p>
                          先搭好故事的骨架，再按章节慢慢展开。你可以直接编辑大纲内容。
                        </p>
                      </div>
                    </div>
                    <label htmlFor="outline-instruction">生成要求</label>
                    <textarea
                      id="outline-instruction"
                      className="prompt-box"
                      value={outlinePrompt}
                      onChange={(e) => setOutlinePrompt(e.target.value)}
                      placeholder="例如：分为三卷，每卷设置一个反转；感情线克制，结尾留一个开放式悬念。"
                    />
                    <div className="section-toolbar">
                      <span>
                        {novel.outline
                          ? "直接编辑书名、梗概和故事设定"
                          : "还没有大纲，输入要求后生成"}
                      </span>
                      <div>
                        <button
                          className="button outline small"
                          onClick={saveOutline}
                          disabled={!novel.outline}
                        >
                          保存修改
                        </button>
                        <button
                          className="button primary small"
                          onClick={() =>
                            createJob("outline", {
                              instructions: outlinePrompt,
                            })
                          }
                          disabled={busy || activeJobs.length > 0}
                        >
                          <Sparkles size={15} />
                          生成大纲
                        </button>
                      </div>
                    </div>
                    {novel.outline ? (
                      <>
                        <div className="outline-fields">
                          <div>
                            <label htmlFor="outline-title">书名</label>
                            <input
                              id="outline-title"
                              value={outlineObject.title || ""}
                              onChange={(e) =>
                                updateOutlineField("title", e.target.value)
                              }
                            />
                          </div>
                          <div>
                            <label htmlFor="outline-synopsis">故事简介</label>
                            <textarea
                              id="outline-synopsis"
                              value={outlineObject.synopsis || ""}
                              onChange={(e) =>
                                updateOutlineField("synopsis", e.target.value)
                              }
                            />
                          </div>
                          <div>
                            <label htmlFor="outline-world">世界观</label>
                            <textarea
                              id="outline-world"
                              value={outlineObject.world || ""}
                              onChange={(e) =>
                                updateOutlineField("world", e.target.value)
                              }
                            />
                          </div>
                          <div>
                            <label htmlFor="outline-conflict">主线冲突</label>
                            <textarea
                              id="outline-conflict"
                              value={outlineObject.main_conflict || ""}
                              onChange={(e) =>
                                updateOutlineField(
                                  "main_conflict",
                                  e.target.value,
                                )
                              }
                            />
                          </div>
                        </div>
                        <div className="outline-summary-grid">
                          <div>
                            <h3>主要人物</h3>
                            {(outlineObject.characters || []).map(
                              (c: any, i: number) => (
                                <article key={i}>
                                  <b>
                                    {c.name} · {c.role}
                                  </b>
                                  <span>{c.motivation || c.arc}</span>
                                </article>
                              ),
                            )}
                          </div>
                          <div>
                            <h3>分卷规划</h3>
                            {(outlineObject.volumes || []).map(
                              (v: any, i: number) => (
                                <article key={i}>
                                  <b>{v.title || `第${i + 1}卷`}</b>
                                  <span>{v.summary || v.arc}</span>
                                </article>
                              ),
                            )}
                          </div>
                        </div>
                        <details className="outline-advanced">
                          <summary>编辑完整大纲数据</summary>
                          <textarea
                            aria-label="完整大纲 JSON"
                            className="outline-editor"
                            value={outlineDraft || outlineText}
                            onChange={(e) => setOutlineDraft(e.target.value)}
                          />
                          <small>
                            高级编辑使用 JSON 格式，保存前会校验结构。
                          </small>
                        </details>
                      </>
                    ) : (
                      <div className="empty-state">
                        <LayoutDashboard size={22} />
                        <span>
                          生成后，书名、简介、人物和分卷规划会显示在这里。
                        </span>
                      </div>
                    )}
                    <p className="help-note">
                      修改内容后选择“保存修改”。重新生成只会产生新建议，保存后才会更新现有大纲。
                    </p>
                  </section>
                )}
                {page === "memory" && (
                  <section className="section-card">
                    <div className="section-intro">
                      <div className="section-icon">
                        <UsersRound size={20} />
                      </div>
                      <div>
                        <h2>故事记忆</h2>
                        <p>
                          人物、设定、时间线和伏笔会在章节之间延续。重要信息可以手动补充或修正。
                        </p>
                      </div>
                    </div>
                    <form
                      className="memory-add"
                      onSubmit={async (e) => {
                        e.preventDefault();
                        if (editingLocked) return;
                        try {
                          const m = await api<Memory>(
                            `/novels/${novel.id}/memories`,
                            {
                              method: "POST",
                              body: JSON.stringify(memoryDraft),
                            },
                          );
                          setMemories((x) => [m, ...x]);
                          setMemoryDraft((v) => ({ ...v, content: "" }));
                          setNotice("故事记忆已添加。");
                        } catch (e: any) {
                          setError(e.message);
                        }
                      }}
                    >
                      <label>新增记忆</label>
                      <div className="memory-form-row">
                        <select
                          aria-label="记忆类型"
                          disabled={editingLocked}
                          value={memoryDraft.kind}
                          onChange={(e) =>
                            setMemoryDraft((v) => ({
                              ...v,
                              kind: e.target.value,
                            }))
                          }
                        >
                          <option value="setting">设定</option>
                          <option value="character">人物</option>
                          <option value="timeline">时间线</option>
                          <option value="foreshadow">伏笔</option>
                        </select>
                        <input
                          aria-label="记忆内容"
                          disabled={editingLocked}
                          value={memoryDraft.content}
                          onChange={(e) =>
                            setMemoryDraft((v) => ({
                              ...v,
                              content: e.target.value,
                            }))
                          }
                          placeholder="例如：林照从不在雨天使用火系法术"
                        />
                        <button
                          className="button primary small"
                          disabled={editingLocked}
                        >
                          <Plus size={15} />
                          添加
                        </button>
                      </div>
                    </form>
                    <div className="memory-list">
                      {memories.length ? (
                        memories.map((m) => (
                          <article className="memory-card" key={m.id}>
                            <div className="memory-badge">
                              {{
                                setting: "设定",
                                character: "人物",
                                timeline: "时间线",
                                foreshadow: "伏笔",
                                summary: "摘要",
                              }[m.kind] || m.kind}
                            </div>
                            <p>{m.content}</p>
                            {m.stale && (
                              <small className="job-error">
                                来源章节已修改，这条记忆已失效，请重新确认章节。
                              </small>
                            )}
                            <button
                              aria-label="删除记忆"
                              className="icon-button danger-icon"
                              disabled={editingLocked}
                              onClick={async () => {
                                if (confirm("删除这条故事记忆？")) {
                                  await api(`/memories/${m.id}`, {
                                    method: "DELETE",
                                  });
                                  setMemories((xs) =>
                                    xs.filter((x) => x.id !== m.id),
                                  );
                                }
                              }}
                            >
                              <Trash2 size={16} />
                            </button>
                          </article>
                        ))
                      ) : (
                        <div className="empty-state">
                          <BookOpen size={22} />
                          <span>
                            目前还没有故事记忆。确认章节后，人物与情节记忆会逐步建立。
                          </span>
                        </div>
                      )}
                    </div>
                  </section>
                )}
                {page === "tasks" && (
                  <section className="section-card">
                    <div className="section-intro">
                      <div className="section-icon">
                        <ListChecks size={20} />
                      </div>
                      <div>
                        <h2>生成任务</h2>
                        <p>
                          每一章按顺序生成并保存。任务完成后可查看结果，失败任务可以重试。
                        </p>
                      </div>
                    </div>
                    {activeJobs.length > 0 && (
                      <div className="queue-banner">
                        <LoaderCircle className="spin" size={17} />
                        <span>
                          有 {activeJobs.length}{" "}
                          个任务正在进行，写作区会暂时锁定，保证内容安全。
                        </span>
                      </div>
                    )}
                    <div className="job-list">
                      {jobs.length ? (
                        jobs.map((j) => (
                          <article className="job-card" key={j.id}>
                            <div className={`job-status ${j.status}`}>
                              <span />
                              {statusLabel(j.status)}
                            </div>
                            <div className="job-main">
                              <b>{labelKind(j.kind)}</b>
                              <small>
                                {j.created_at
                                  ? new Date(j.created_at).toLocaleString(
                                      "zh-CN",
                                    )
                                  : "最近提交"}{" "}
                                {j.current || j.progress?.current
                                  ? ` · ${j.current || j.progress?.current}/${j.count || j.progress?.count || "—"}`
                                  : ""}
                              </small>
                              {j.error && (
                                <p className="job-error">{j.error}</p>
                              )}
                              {j.result?.report && (
                                <p className="job-report">{j.result.report}</p>
                              )}
                            </div>
                            <div className="job-actions">
                              {j.status === "succeeded" &&
                                (j.kind === "rewrite" ||
                                  j.kind === "outline") && (
                                  <button
                                    className="button outline small"
                                    onClick={() => applyJobResult(j)}
                                  >
                                    查看结果
                                  </button>
                                )}
                              {["pending", "running"].includes(j.status) && (
                                <button
                                  className="button outline small"
                                  onClick={() => jobAction(j.id, "cancel")}
                                >
                                  停止
                                </button>
                              )}
                              {j.status === "failed" && (
                                <button
                                  className="button outline small"
                                  onClick={() => jobAction(j.id, "retry")}
                                >
                                  <RefreshCw size={14} />
                                  重试
                                </button>
                              )}
                            </div>
                          </article>
                        ))
                      ) : (
                        <div className="empty-state">
                          <ListChecks size={22} />
                          <span>
                            还没有生成任务。写下一章或生成大纲后，任务会显示在这里。
                          </span>
                        </div>
                      )}
                    </div>
                  </section>
                )}
                {page === "usage" && (
                  <section className="section-card">
                    <div className="section-intro">
                      <div className="section-icon">
                        <Coins size={20} />
                      </div>
                      <div>
                        <h2>用量记录</h2>
                        <p>
                          按这部小说查看模型调用量。费用是根据你填写的模型价格估算。
                        </p>
                      </div>
                    </div>
                    <div className="metrics-grid">
                      <div className="metric">
                        <span>输入 tokens</span>
                        <b>{(usage?.input_tokens || 0).toLocaleString()}</b>
                      </div>
                      <div className="metric">
                        <span>输出 tokens</span>
                        <b>{(usage?.output_tokens || 0).toLocaleString()}</b>
                      </div>
                      <div className="metric">
                        <span>调用次数</span>
                        <b>{(usage?.requests || 0).toLocaleString()}</b>
                      </div>
                      <div className="metric">
                        <span>估算费用</span>
                        <b>
                          {settings.input_price_per_million ||
                          settings.output_price_per_million
                            ? Number(usage?.estimated_cost || 0).toFixed(2)
                            : "未配置单价"}
                        </b>
                      </div>
                    </div>
                    <div className="section-toolbar">
                      <b>调用明细</b>
                      <span>{usage?.records?.length || 0} 条记录</span>
                    </div>
                    <div className="usage-records">
                      {usage?.records?.length ? (
                        usage.records.map((r: any, i: number) => (
                          <div key={r.id || i}>
                            <span>
                              {r.model || "模型"} · {r.kind || "生成"}
                            </span>
                            <b>
                              {(r.input_tokens || 0).toLocaleString()} /{" "}
                              {(r.output_tokens || 0).toLocaleString()}
                            </b>
                            <small>
                              {r.created_at
                                ? new Date(r.created_at).toLocaleString("zh-CN")
                                : ""}
                            </small>
                          </div>
                        ))
                      ) : (
                        <div className="empty-state">
                          <Coins size={22} />
                          <span>这部小说还没有调用记录。</span>
                        </div>
                      )}
                    </div>
                  </section>
                )}
              </>
            )}
          </div>
        </div>
      </main>
      {showNew && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setShowNew(false);
          }}
        >
          <section
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="new-title"
          >
            <button
              className="icon-button modal-close"
              aria-label="关闭"
              onClick={() => setShowNew(false)}
            >
              <X size={18} />
            </button>
            <span className="modal-kicker">
              <Sparkles size={15} />
              新建作品
            </span>
            <h2 id="new-title">你的故事是什么？</h2>
            <p>用几句话说出核心想法，之后还能随时修改大纲。</p>
            <form onSubmit={createNovel}>
              <label htmlFor="premise">故事灵感</label>
              <textarea
                autoFocus
                id="premise"
                value={newPremise}
                onChange={(e) => setNewPremise(e.target.value)}
                required
                placeholder="例如：一位被逐出宗门的药师，靠辨识古药寻找身世。偏悬疑，感情线克制，计划写五卷。"
              />
              <div className="settings-grid">
                <div>
                  <label htmlFor="genre">题材（可选）</label>
                  <input
                    id="genre"
                    value={newGenre}
                    onChange={(e) => setNewGenre(e.target.value)}
                    placeholder="仙侠、悬疑……"
                  />
                </div>
                <div>
                  <label htmlFor="style">风格（可选）</label>
                  <input
                    id="style"
                    value={newStyle}
                    onChange={(e) => setNewStyle(e.target.value)}
                    placeholder="克制、幽默……"
                  />
                </div>
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="button outline"
                  onClick={() => setShowNew(false)}
                >
                  先等等
                </button>
                <button
                  className="button primary"
                  disabled={busy || !newPremise.trim()}
                >
                  {busy ? (
                    <LoaderCircle className="spin" />
                  ) : (
                    <Sparkles size={16} />
                  )}
                  建立故事
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
      {showExport && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setShowExport(false);
          }}
        >
          <section
            className="modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="export-title"
          >
            <button
              className="icon-button modal-close"
              aria-label="关闭"
              onClick={() => setShowExport(false)}
            >
              <X size={18} />
            </button>
            <span className="modal-kicker">
              <Download size={15} />
              导出作品
            </span>
            <h2 id="export-title">下载可发布的正文</h2>
            <p>可以导出整本小说，也可以指定章节范围。</p>
            <div className="export-range">
              <div>
                <label htmlFor="export-from">起始章节</label>
                <input
                  id="export-from"
                  type="number"
                  min="1"
                  max={chapters.length || 1}
                  value={exportFrom}
                  onChange={(e) => setExportFrom(e.target.value)}
                  placeholder="1"
                />
              </div>
              <span>至</span>
              <div>
                <label htmlFor="export-to">结束章节</label>
                <input
                  id="export-to"
                  type="number"
                  min="1"
                  max={chapters.length || 1}
                  value={exportTo}
                  onChange={(e) => setExportTo(e.target.value)}
                  placeholder={String(chapters.length || "全部")}
                />
              </div>
            </div>
            <div className="modal-actions">
              <button
                className="button outline"
                onClick={() => exportNovel("txt")}
              >
                <Download size={15} />
                导出 TXT
              </button>
              <button
                className="button primary"
                onClick={() => exportNovel("md")}
              >
                <Download size={15} />
                导出 Markdown
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
