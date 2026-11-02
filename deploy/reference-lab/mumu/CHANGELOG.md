# CHANGELOG

## MUMU-LAB-20261102-1215-01

- 时间：2026-11-02 12:15:00 Asia/Shanghai。
- 代理：/root/lab_mumu。
- 目的：为主代理准备 MuMuAINovel 无 API、无模型服务的独立 Docker 页面评估配置。
- 影响文件：本目录 Dockerfile、compose-fragment.yml、patch_ui_only.py、test_config.py、README.md、CHANGELOG.md；忽略目录 `.reference-sources/mumu` 为官方仓库只读源码检出，main 固定至 `743e5abec18beb8d73426527e6579538053bc6fd`，未修改上游文件。
- 行为：内部服务 mumu:8000 与 mumu-db:5432，无宿主机端口；两独立 internal 网络，数据库仅接 mumu_db_net。应用 384 MiB、数据库 128 MiB，无 swap 扩容；独立命名卷。保留上游 PostgreSQL 初始化和 Alembic 迁移入口。要求私密提供数据库密码、原生管理员密码与会话密钥，不提供默认密码。
- 评估补丁：仅在镜像构建副本中，按 LF 标准化 SHA256 验证后关闭启动时 Chroma/ONNX 初始化及导入，向量调用明确报不可用；移除五个仅向量模块使用的直接依赖。不下载 embedding，不伪造模型/生成结果。上游 GPL v3 LICENSE 原样复制进镜像。所有模型 API 凭据、URL、默认模型为空；OAuth、邮件关闭，工坊云地址指向闭合回环端口，运行期所有应用网络必须保持 internal。
- 实际检查：读取根 CHANGELOG 与 git status；确认克隆 HEAD；静态追踪入口、迁移、原生登录、签名 Cookie、向量导入和依赖。`python deploy/reference-lab/mumu/test_config.py -v` 五项通过，覆盖补丁守卫、依赖过滤、禁用向量显式失败、空凭据、内部网络及无宿主机端口；只执行自编评估代理类，未导入/执行上游业务代码。`git diff --check -- deploy/reference-lab/mumu` 通过；上游 `git status --short` 为空。首次哈希检查发现 Windows CRLF 与规范化读取不同，已统一 LF 哈希并通过测试。
- 余项与边界：本机无 Docker CLI，未构建/运行镜像，未验证实际迁移、登录、页面、内存或重启持久化。主代理需检查合并后网络、网关 Basic Auth、清除 X-Instance-ID/X-User-ID 代理身份头。原生 Cookie 为 session_token / session_expire_at，与主代理确认的生产 ainovel_session 不同。原生密码首次登录后持久化到本项目数据库。向量功能、付费生成等不属于评估验收。内部内存限额低于上游 2 GiB 最低建议，需实际测量。
- Git：未提交、未推送。部署：未操作服务器；未访问 81 或其他服务器；主代理将在 188 构建与验证后记录实际结果。
