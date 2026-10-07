# 纸间 · AI 小说工作台

自托管小说写作服务：几句话生成大纲、按章写作、正文编辑、复制与 TXT/Markdown 导出，结合章节摘要、正式剧情记忆和可恢复后台任务。

## 部署

需要 Docker Engine 与 Docker Compose。将模型令牌放入项目外的私密文件，用以下命令生成随机登录密码、密码哈希、数据库密码和运行配置：

```sh
python scripts/setup_env.py --key-file /private/model-key --base-url https://agentrouter.org/v1 --model YOUR_MODEL
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
4. 确认定稿，将摘要、人物状态、时间线和伏笔同步到正式记忆。
5. 复制正文或导出小说。修改旧章节后检查失效记忆并重新定稿。

模型质量、输出长度与实际费用由所接入服务决定。生成时只组装必要的大纲、近期摘要和相关记忆，不发送整本小说。当前检索使用关键词与实体过滤；数据库镜像包含 pgvector，语义向量索引待配置嵌入模型后扩展。

后台任务每本书串行运行；同一次批量最多 20 章。修改章节会使本章及后续正式记忆失效，应按顺序重新确认。崩溃任务租约最长约 10 分钟后恢复；停止任务不能撤回已经发送给供应商的请求，但会丢弃尚未保存的结果。

上下文包限制 24,000 字符，完整模型请求限制 48,000 字符；这些是字符上限，不是精确 token 配额。手动导入过长章节须拆分后再做模型审稿或记忆提取。暂不包含 EPUB、多用户、GPU 本地模型、自动账单核对及硬性费用预算。

如果模型供应商返回 `unauthorized_client_error`、验证网页、401 或 403，应由供应商确认普通 API 调用权限或更换兼容接口。应用不会伪装成其他客户端来绕过供应商限制。更换供应商后修改 `.env` 并重建 API 与 Worker 容器；网页只允许修改原接口域名内的地址，以保护服务器密钥。

## 数据与维护

正文、章节历史、记忆、任务和调用用量保存在 PostgreSQL；Redis 保存队列状态。备份不包含模型密钥，请另行安全保存 `.env`。

```sh
sh scripts/backup.sh
# 恢复会替换当前小说数据库，先备份，停止进行中的任务后运行：
sh scripts/restore.sh backups/ainovel-TIMESTAMP.dump
```

请勿运行 `docker compose down -v`，它会删除数据卷。普通更新使用 `docker compose up -d --build`。未来数据库结构升级需要迁移脚本，不能仅用建表替代迁移。

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
