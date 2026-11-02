"""Original, declarative writing templates. Rendering never evaluates code."""
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text

from .auth import require_auth
from .db import Novel, PromptRevision, PromptTemplate, serialize
from .dependencies import database
from .services import get_or_404

router = APIRouter(prefix="/api/prompts", dependencies=[Depends(require_auth)])
TaskKind = Literal["outline", "write", "rewrite", "audit", "confirm"]
CATEGORIES = {"outline": "创作规划", "write": "正文创作", "rewrite": "文字加工", "audit": "审读分析", "confirm": "审读分析"}
VARIABLES = {"title", "genre", "style", "instructions"}


class PromptInput(BaseModel):
    name: str = Field(min_length=1, max_length=240)
    category: str = Field(default="", max_length=100)
    task_kind: TaskKind
    genre_tags: list[str] = Field(default_factory=list, max_length=30)
    description: str = Field(default="", max_length=5000)
    body: str = Field(min_length=1, max_length=20000)
    novel_id: str | None = None
    enabled: bool = True


class PromptPatch(BaseModel):
    revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=240)
    category: str | None = Field(default=None, max_length=100)
    task_kind: TaskKind | None = None
    genre_tags: list[str] | None = Field(default=None, max_length=30)
    description: str | None = Field(default=None, max_length=5000)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    novel_id: str | None = None
    enabled: bool | None = None


def validate_body(body):
    remaining = re.sub(r"{{\s*([A-Za-z_]+)\s*}}", lambda match: "" if match[1] in VARIABLES else match[0], body)
    if "{{" in remaining or "}}" in remaining:
        raise HTTPException(422, "模板仅支持 title、genre、style、instructions 双花括号变量")


def render(body, variables):
    validate_body(body)
    return re.sub(r"{{\s*([A-Za-z_]+)\s*}}", lambda match: str(variables.get(match[1], "")), body)


def prompt_data(row):
    return {key: value for key, value in serialize(row).items() if key != "deleted"}


def snapshot(db, row):
    db.flush()
    db.add(PromptRevision(prompt_id=row.id, revision=row.revision, snapshot=prompt_data(row)))


def seed_prompts(db):
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(18110, 2)"))
    originals = [
        ("outline", "连载故事骨架", "从核心困境展开《{{title}}》。题材：{{genre}}；风格：{{style}}。让人物目标、阻碍与代价相互推动，分卷安排递进的选择，给后续连载留下空间。作者补充：{{instructions}}"),
        ("write", "场景推动正文", "为《{{title}}》续写有具体行动的场景。题材：{{genre}}，文风：{{style}}。用人物选择推动事件，以可感知的细节呈现变化，让结尾产生新的行动理由。作者要求：{{instructions}}"),
        ("rewrite", "保意精修", "精修《{{title}}》的文字，保留事实、叙事视角与情节结果。删去重复解释，调整句式节奏，让动作和对白体现人物。文风：{{style}}。专项要求：{{instructions}}"),
        ("audit", "连续性审读", "检查《{{title}}》当前章节：人物是否拥有行动所需的信息，时间地点是否衔接，冲突是否产生实际变化。逐条定位问题并建议小范围修正。作者关注：{{instructions}}"),
        ("confirm", "有据记忆提取", "为《{{title}}》整理本章已发生事实。每条记忆须附正文中的连续原句作为证据；区分公开事实和人物有限知情，不推断未写出的结果。作者关注：{{instructions}}"),
        ("write", "悬疑线索场景", "创作《{{title}}》的悬疑场景。用观察、误判与可回溯线索推进调查；关键信息必须在文本中出现，人物的推理不越过已知事实。保持{{style}}，遵循：{{instructions}}"),
        ("rewrite", "对白与动作润色", "润色《{{title}}》的对白与动作。保留信息量与事件次序，为不同人物安排有差异的措辞和反应，用动作停顿替代笼统情绪标签。风格：{{style}}。要求：{{instructions}}"),
    ]
    for index, (kind, name, body) in enumerate(originals):
        identity = f"builtin-{kind}-{index + 1}"
        if db.get(PromptTemplate, identity):
            continue
        row = PromptTemplate(id=identity, name=name, task_kind=kind, category=CATEGORIES[kind],
                             body=body, builtin=True, source_label="本项目原创", genre_tags=["悬疑"] if index == 5 else [])
        db.add(row)
        snapshot(db, row)


def selected_snapshot(db, prompt_id, novel, kind, instructions):
    if not prompt_id:
        return None
    row = get_or_404(db, PromptTemplate, prompt_id)
    if row.deleted or not row.enabled or row.task_kind != kind or row.novel_id not in (None, novel.id):
        raise HTTPException(422, "模板不可用、任务类型不匹配或不属于本书")
    variables = {"title": novel.title, "genre": novel.genre, "style": novel.style, "instructions": instructions}
    return {"id": row.id, "revision": row.revision, "body": row.body, "rendered": render(row.body, variables), "variables": variables}


@router.get("")
def list_prompts(db=Depends(database)):
    return [prompt_data(row) for row in db.scalars(select(PromptTemplate).where(PromptTemplate.deleted.is_(False)).order_by(PromptTemplate.name))]


@router.post("")
def create_prompt(body: PromptInput, db=Depends(database)):
    data = body.model_dump()
    validate_body(body.body)
    if body.novel_id:
        get_or_404(db, Novel, body.novel_id)
    data["category"] = body.category or CATEGORIES[body.task_kind]
    row = PromptTemplate(**data)
    db.add(row)
    snapshot(db, row)
    db.commit()
    return prompt_data(row)


@router.get("/export")
def export_prompts(db=Depends(database)):
    return {"schema_version": 1, "prompts": [prompt_data(row) for row in db.scalars(select(PromptTemplate).where(PromptTemplate.deleted.is_(False)))]}


class PromptImport(BaseModel):
    schema_version: Literal[1]
    prompts: list[dict] = Field(max_length=200)


@router.post("/import")
def import_prompts(body: PromptImport, dry_run: bool = True, db=Depends(database)):
    prepared, conflicts = [], []
    seen = set()
    for index, raw in enumerate(body.prompts):
        try:
            entry = PromptInput.model_validate(raw)
            validate_body(entry.body)
            if entry.novel_id:
                get_or_404(db, Novel, entry.novel_id)
            key = (entry.novel_id, entry.name)
            existing = db.scalar(select(PromptTemplate.id).where(PromptTemplate.novel_id == entry.novel_id,
                                 PromptTemplate.name == entry.name, PromptTemplate.deleted.is_(False)))
            if existing or key in seen or (raw.get("id") and db.get(PromptTemplate, raw["id"])):
                conflicts.append({"index": index, "name": entry.name, "reason": "同作用域名称或ID已存在"})
            else:
                prepared.append(entry)
                seen.add(key)
        except (ValueError, HTTPException) as exc:
            conflicts.append({"index": index, "reason": exc.detail if isinstance(exc, HTTPException) else "模板格式无效"})
    if not dry_run and conflicts:
        raise HTTPException(409, {"message": "存在冲突，未导入任何模板", "conflicts": conflicts})
    imported = []
    if not dry_run:
        for entry in prepared:
            data = entry.model_dump()
            data["category"] = entry.category or CATEGORIES[entry.task_kind]
            row = PromptTemplate(**data)
            db.add(row)
            snapshot(db, row)
            imported.append(prompt_data(row))
        db.commit()
    return {"dry_run": dry_run, "valid_count": len(prepared), "conflicts": conflicts, "imported": imported}


def get_prompt(db, prompt_id):
    row = get_or_404(db, PromptTemplate, prompt_id)
    if row.deleted:
        raise HTTPException(404, "模板不存在")
    return row


@router.get("/{prompt_id}")
def get_one(prompt_id: str, db=Depends(database)):
    return prompt_data(get_prompt(db, prompt_id))


@router.patch("/{prompt_id}")
def patch_prompt(prompt_id: str, body: PromptPatch, db=Depends(database)):
    row = get_prompt(db, prompt_id)
    db.refresh(row, with_for_update=True)
    if row.builtin:
        raise HTTPException(409, "内置模板请另存为自定义模板")
    if row.revision != body.revision:
        raise HTTPException(409, "模板已更新，请刷新")
    data = body.model_dump(exclude_unset=True, exclude={"revision"})
    if "body" in data and data["body"] is not None:
        validate_body(data["body"])
    if data.get("novel_id"):
        get_or_404(db, Novel, data["novel_id"])
    for key, value in data.items():
        if value is not None or key == "novel_id":
            setattr(row, key, value)
    row.category = row.category or CATEGORIES[row.task_kind]
    row.revision += 1
    snapshot(db, row)
    db.commit()
    return prompt_data(row)


@router.delete("/{prompt_id}")
def delete_prompt(prompt_id: str, db=Depends(database)):
    row = get_prompt(db, prompt_id)
    db.refresh(row, with_for_update=True)
    if row.builtin:
        raise HTTPException(409, "不能删除内置模板")
    row.deleted, row.enabled = True, False
    db.commit()
    return {"deleted": True}


@router.get("/{prompt_id}/versions")
def versions(prompt_id: str, db=Depends(database)):
    get_or_404(db, PromptTemplate, prompt_id)
    return [serialize(row) for row in db.scalars(select(PromptRevision).where(PromptRevision.prompt_id == prompt_id).order_by(PromptRevision.revision.desc()))]


class PreviewInput(BaseModel):
    novel_id: str | None = None
    instructions: str = Field(default="", max_length=6000)


@router.post("/{prompt_id}/preview")
def preview(prompt_id: str, body: PreviewInput, db=Depends(database)):
    row = get_prompt(db, prompt_id)
    book = get_or_404(db, Novel, body.novel_id) if body.novel_id else None
    if row.novel_id and (not book or book.id != row.novel_id):
        raise HTTPException(422, "模板不属于本书")
    variables = {"title": book.title if book else "", "genre": book.genre if book else "", "style": book.style if book else "", "instructions": body.instructions}
    return {"rendered": render(row.body, variables), "variables": variables, "revision": row.revision}
