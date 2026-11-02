# 纸间 · AI 小说工作台

自托管小说写作服务：几句话生成大纲、按章写作、正文编辑、复制与 TXT/Markdown 导出，结合分类提示词、受限 Skill、带证据的正式记忆、伏笔台账、关系图和可恢复后台任务。

## 部署

需要 Docker Engine 与 Docker Compose。将模型令牌放入项目外的私密文件，用以下命令生成随机登录密码、密码哈希、数据库密码和运行配置：

```sh
python scripts/setup_env.py --key-file /private/model-key --base-url https://ark.cn-beijing.volces.com/api/v3 --model YOUR_ENABLED_MODEL_OR_ENDPOINT
```

生成的登录信息位于被 Git 忽略的 `.secrets/login.txt`，运行配置为 `.env`。密钥只能配置在后端环境中，不要提交这些文件。也可参考 `.env.example` 手动配置。

```sh
docker compose build
docker compose up -d
docker compose ps
```

默认访问 `http://服务器地址:18110`。通过 HTTPS 反向代理使用时，设置 `COOKIE_SECURE=true`。数据库、Redis 不公开端口。部署采用独立数据卷，不会修改其他应用。

## 写作流程

1. 登录，新建小说并输入几句话创意。
2. 生成大纲，修改保存后生成章节。
3. 编辑正文或按要求重写；生成结果先保存为草稿。
4. 提取记忆候选，在故事记忆中核对正文原句并采纳后，确认章节定稿。
5. 复制正文或导出小说。修改旧章节后检查失效记忆并重新定稿。

模型质量、输出长度与实际费用由所接入服务决定。生成时只组装必要的大纲、近期摘要和相关记忆，不发送整本小说。当前检索使用关键词与实体过滤；数据库镜像包含 pgvector，语义向量索引待配置嵌入模型后扩展。

提示词库按任务阶段分类，题材另用标签，支持全局/当前小说范围、变量预览、历史修订、恢复和 JSON 导入预检/导出。初始模板为本项目原创；选择模板后，任务冻结该版本，重试不会使用后来修改的正文。

Skill 是已有五种创作任务的操作入口，展示输入、步骤、产物和模型调用上限；不会安装软件或执行任意代码。提示词与 Skill 分栏。伏笔记录计划和追加式进展事件；关系图与实体/关系列表共用数据，可引用已审核记忆，并按章节过滤。图谱和伏笔目前供作者维护，模型自动上下文仍使用有效记忆，不自动读取全部图谱或计划。

记忆、关系与伏笔保留来源章节、正文版本及原句；修改旧事实后显示失效或待复核，历史证据可查看。旧版迁移的记忆不会被捏造证据：标为历史待复核，重新提取并采纳后再参与正文事实检索。人物知情字段采用保守筛选，尚不是完整的视角推理系统。整体设计见 `docs/ARCHITECTURE.md`。

后台任务每本书串行运行；同一次批量最多 20 章。修改章节会使本章及后续正式记忆失效，应按顺序重新确认。崩溃任务租约最长约 10 分钟后恢复；停止任务不能撤回已经发送给供应商的请求，但会丢弃尚未保存的结果。

上下文包限制 24,000 字符，完整模型请求限制 48,000 字符；这些是字符上限，不是精确 token 配额。手动导入过长章节须拆分后再做模型审稿或记忆提取。暂不包含 EPUB、多用户、GPU 本地模型、自动账单核对及硬性费用预算。

如果模型供应商返回 `unauthorized_client_error`、验证网页、401 或 403，应由供应商确认普通 API 调用权限或更换兼容接口。应用不会伪装成其他客户端来绕过供应商限制。更换供应商后修改 `.env` 并重建 API 与 Worker 容器；网页只允许修改原接口域名内的地址，以保护服务器密钥。

### AgentRouter 的真实客户端接入

该网关的官方使用文档提供 Claude Code 接入方式。服务已增加可选的真实 Claude Code 通道，启用以下专用 Docker 配置时会安装官方客户端；普通 API 部署保持轻量。

```dotenv
LLM_TRANSPORT=claude_cli
LLM_BASE_URL=https://agentrouter.org/v1
LLM_MODEL=deepseek-v4-flash
```

```sh
docker compose -f compose.yaml -f compose.cli.yaml up -d --build
```

该通道使用 Anthropic 协议，按平台支持列表选择 Claude、GLM 或 DeepSeek 模型。普通 OpenAI 通道仍保留为 `LLM_TRANSPORT=http`。客户端调用禁用工具、MCP、技能和 Hooks，每次使用独立临时目录，通过标准输入传入文本；密钥只在子进程环境中。输出 token 上限沿用写作任务，调用超时默认 180 秒，允许配置 `CLAUDE_CLI_TIMEOUT=1..240`。客户端通道不支持创作温度参数，模型候选列表来自配置，不能视为实时可用列表。

还需确保服务器能访问主网关。若所在网络无法访问，可在私密 `.env` 中配置自己获准使用的稳定 `HTTPS_PROXY`，并设置 `NO_PROXY=localhost,127.0.0.1,db,redis`。不应依赖固定短 TTL 的网关 IP，也不应把依赖个人电脑在线的临时测试桥接当作长期云部署。

### 火山方舟直接 API

普通模型 API 使用 `LLM_BASE_URL=https://ark.cn-beijing.volces.com/api/v3`，`LLM_TRANSPORT=http`，并填入账号已开通的 Model ID 或 Endpoint ID。模型目录包含尚未开通的模型，列表成功不代表账号有推理权限。收到 `ModelNotOpen` 时，请在方舟控制台开通相应模型，或使用已开通的 ID。服务使用 `max_completion_tokens` 控制完整输出预算；豆包 Seed 模型默认关闭深度思考，避免为小说正文生成额外思考内容。

## 数据与维护

正文、章节历史、记忆、任务和调用用量保存在 PostgreSQL；Redis 保存队列状态。备份不包含模型密钥，请另行安全保存 `.env`。

```sh
sh scripts/backup.sh
# 恢复会替换当前小说数据库，先备份，停止进行中的任务后运行：
sh scripts/restore.sh backups/ainovel-TIMESTAMP.dump
```

请勿运行 `docker compose down -v`，它会删除数据卷。普通更新使用 `docker compose up -d --build`。现存数据库升级需要显式迁移，不能仅用建表替代迁移。升级前备份并处理完活动任务，停止 API/Worker 后运行新镜像的迁移，再启动：

```sh
docker compose stop api worker
docker compose run --rm --no-deps api python -m app.migrations --apply
docker compose up -d --no-build
```

API/Worker 启动只检查现存库版本；不在启动时自动升级旧库。全新空库可以初始化。回滚镜像不能撤回新数据语义，必要时使用升级前的一致性数据库备份与对应源码，保留当前数据后再恢复。

## 安全

单用户工作台，登录会话使用 HttpOnly Cookie；模型密钥不会返回网页。公网访问建议配置 HTTPS。开发测试和截图不得包含 API Key。日志及错误提示只输出经过处理的错误信息。

## 开发

后端代码位于 `backend/`，前端位于 `frontend/`，部署配置为 `compose.yaml`。具体 API 见启动后的 `/docs`（若启用）和后端源码。

```sh
pip install -r backend/requirements-dev.txt
python -m pytest backend/tests -q
cd frontend
pnpm install --frozen-lockfile
pnpm build
```

`scripts/verify_postgres.py` 仅在独立的 `ainovel_verify` 数据库运行模拟模型流程与真实数据库并发验证，不调用付费模型，也不触碰正式小说数据。
