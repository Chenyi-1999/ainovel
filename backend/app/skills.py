"""A fixed capability registry: no scripts, tool discovery, or arbitrary execution."""
SKILLS = [
    {"id": kind, "name": name, "description": description, "job_kind": kind,
     "inputs": inputs, "outputs": outputs, "steps": steps, "max_calls": calls,
     "permissions": ["model.generate"], "requires_review": review}
    for kind, name, description, inputs, outputs, steps, calls, review in [
        ("outline", "故事规划", "生成可编辑的连载大纲", ["novel", "instructions"], ["outline"], ["生成结构化大纲"], 1, False),
        ("write", "续写章节", "每次尝试按篇幅逐节生成并审读修正：每章最多9次调用，最多20章、180次；重试另计。正文字数须在目标±10%内", ["novel", "count", "target_words", "instructions"], ["draft_chapters"], ["按动态预算逐节生成草稿", "审读与一次篇幅修正", "校验字数并保存草稿"], 180, False),
        ("rewrite", "正文精修", "产生改写提案，由作者保存", ["chapter", "selection", "instructions"], ["rewrite_proposal"], ["生成改写提案", "等待作者保存"], 1, True),
        ("audit", "章节审读", "生成一致性与语言建议", ["chapter", "instructions"], ["report"], ["审读并给出建议"], 1, False),
        ("confirm", "定稿与记忆", "提取带正文证据的候选，等待作者复核", ["chapter", "instructions"], ["memory_candidates"], ["提取候选", "等待作者复核", "验证来源并应用定稿"], 1, True),
    ]
]
