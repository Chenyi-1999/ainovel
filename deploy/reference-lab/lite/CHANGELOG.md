# CHANGELOG

## REF-LITE-20261102-121403-01

- 时间：2026-11-02 12:14:03 Asia/Shanghai。
- 代理：/root/lab_lite（主代理 /root 的受限子任务）。
- 目的：准备官方 Ai-Novel Lite 的无模型、无付费调用 Docker 界面评估配置，供主代理在 188 服务器独立部署。
- 影响范围：检出 `.reference-sources/lite/`，官方 `lite` 分支固定为 `d3bce7437861402083edd77af3cc50b088026b7d`；新增本目录 `compose-fragment.yml`、`Dockerfile.frontend`、`nginx.conf`、`nginx-main.conf`、`README.md`、`check_config.py`、`CHANGELOG.md`。上游工作树未修改；未找到上游 LICENSE，未另行授予许可证。
- 行为：两个内部服务 `lite:80` / `lite-api:8000`；独立 `lite_data` 卷与 `internal:true` 网络；没有宿主机端口。使用上游支持的 dev + SQLite WAL + 单 Uvicorn/inline worker，明确关闭 dev 匿名回退，管理员密码和独立会话签名密钥为必填私密环境变量；Cookie 名按项目隔离。上游原生 entrypoint 生成持久化加密密钥并自动迁移数据库。前端 Nginx 上游改为 `lite-api`，固定一个 Nginx worker；前端 Node 构建堆上限 384 MiB。运行时上限合计 416 MiB，未声称实际占用。
- 限制：本轮仅源码读取与配置文件编写；不连接服务器、不执行上游代码、不安装宿主机依赖、不构建镜像、不配置任何模型或 API 密钥、不执行生成。未操作 81 服务器。主代理需将 Basic Auth 网关接到 `lite_net` 并发布 18021；API 不得接入额外可出网网络。
- 实际检查：Git 固定 SHA 核验通过；上游 `git status --short` 无输出；Python/PyYAML 静态回归 5/5 通过（源码与路径、网络隔离、必需登录与 Cookie、SQLite/无模型配置、Nginx 代理与 SPA）。首轮断言把 `DATABASE_URL` 误归类为模型 `BASE_URL`，已缩小检查到 VECTOR/LINUXDO 前缀并复验通过。`git diff --check` 通过，仅有主代理已有 `.gitignore` 换行提示；shell entrypoint 的 CRLF 数为 0。
- 剩余事项：主代理合并 Compose 后验证、串行构建、实际健康状态、Basic Auth、原生登录和 Cookie、手工项目/角色/章节 CRUD、LLM 档案为空、运行时出网失败、重建持久化与实际内存。开发模式有详细错误与原生开放注册，依靠外层 Basic Auth 限制入口；HTTP 不具备传输加密。不能将这些待办记为已通过。
- Git：未提交、未推送。部署：未部署、未重启任何服务。
