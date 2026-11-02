# 来源提示词目录

本目录功能在提示词库中管理，与 Skill 工作流保持分离。原有 7 条原创模板保留；另整理 MuMu 的 36 条静态系统模板及 Lite 的 7 组预设，共 43 组来源资产。Lite 的 66 个组成块保留顺序、角色、启用状态、文件路径与逐块哈希，不把每个片段计算为一组独立写作提示词。

| 用途 | 来源条目数 |
| --- | ---: |
| 灵感与立意 | 9 |
| 世界与职业设定 | 2 |
| 人物与组织 | 7 |
| 大纲与细纲 | 6 |
| 章节规划 | 1 |
| 章节写作 | 6 |
| 润色与改写 | 4 |
| 情节分析 | 1 |
| 拆书与反推 | 2 |
| 封面与工具 | 5 |

16 组有当前任务适配版：MuMu 的大纲创建/续写/展开、四种章节模式、章节/局部重写、情节分析；Lite 的大纲、两个章节版本、润色和正文优化。其余 27 组为原文参考，包含当前没有独立入口的灵感、世界/角色设定、规划、拆书、封面与 MCP 等流程；不进入生成和 Skill 的模板选择器。

每条记录可查看来源项目、固定提交、原名、原分类、参数、文件、许可、完整原文和 SHA256。有适配版的条目另显示当前可执行正文；原文不被改写覆盖。原文区始终提供只读文本框与全选复制，不依赖自动剪贴板权限。

## 来源与适配边界

来源版本以 `deploy/reference-lab/sources.lock.json` 为准：

- MuMu：`xiamuceer-j/MuMuAINovel`，`743e5abec18beb8d73426527e6579538053bc6fd`；保留 GPL-3.0 全文及作者归属。
- Lite：`inliver233/Ai-Novel` 的 `lite` 分支，`d3bce7437861402083edd77af3cc50b088026b7d`；固定检出未附许可证。

原文内容包位于忽略的 `.secrets/reference-prompt-catalog/`，并导入当前认证实例的数据库；不放入公开 Git 仓库，也不随镜像分发。Git 只记录提取器、导入器、合成测试和元信息。数据库备份包含实际实例内容，应继续按私有数据保存。来源原文可由用户在工作台查看、复制和导出，导出同时携带来源元信息。

MuMu 提取只解析 Python AST 的字符串常量与静态元数据，不 import 上游模块、不调用会混入 Skill 的聚合函数。Lite 只读取 JSON 和约束在资源目录内的 Markdown。提取会核对本机检出提交和工作树，并分别计算原文及各块的哈希。

适配版保留创作方法与质量要求，改用当前工作台资料及最终输出合同：

- MuMu 的数据注入区与旧输出合同不直接执行，保留在来源原文中；安全变量只使用 `title/genre/style/instructions`。
- Lite 采用预设中已启用的角色、写作规则与润色块；题材和深度处理条件转为明确的适用条件说明，不运行 Lite 的模板 DSL。
- 缺少的原系统职业、MCP 或其他资料不冒充已提供；当前任务合同优先，不自动获得工具权限。
- 原文参考不渲染源系统变量或条件语法，不能伪装为已经接入的模型任务。

## 可重复导入

先在本机保存好两个固定检出，生成私有内容包：

```sh
python scripts/build_reference_prompt_catalog.py
python scripts/test_reference_prompt_catalog.py
```

在服务器把包保存在仅管理员可访问的项目目录，先备份数据库、处理完活动任务，再停止 API/Worker，使用新镜像显式迁移到 schema 2。将单个内容文件只读挂载进临时容器：

```sh
docker compose stop api worker
docker compose run --rm --no-deps api python -m app.migrations --apply
docker compose run --rm --no-deps -v /absolute/private/catalog.json:/run/catalog.json:ro api python -m app.prompt_catalog --pack /run/catalog.json --dry-run
docker compose run --rm --no-deps -v /absolute/private/catalog.json:/run/catalog.json:ro api python -m app.prompt_catalog --pack /run/catalog.json --apply
docker compose up -d --no-build
```

首次预期新增 43 条；再次导入全部跳过，不重复创建版本。UUIDv5 身份、原文/块哈希、兼容状态和所有条目在写入前一起校验；冲突会拒绝整批，不覆盖用户模板。导入使用单个事务与 PostgreSQL 锁；重建容器后仍由数据库保留内容，无需重新导入。
