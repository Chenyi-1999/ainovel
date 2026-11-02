# 三个小说项目的独立界面试用

体验环境已全部退役。配置、源码和独立数据卷均保留，可按下文手动复现；生产小说工作台 `18110` 不受影响。本目录只提供评估部署，不替换现有小说代码。

| 原入口（已关闭） | 项目 | 形态 |
| --- | --- | --- |
| http://188.68.41.4:18020/ | MuMuAINovel | 网页；另需原生管理员登录 |
| http://188.68.41.4:18021/ | Ai-Novel Lite | 网页；另需原生管理员登录 |
| http://188.68.41.4:18022/ | Show Me The Story | 网页 |

三个入口均使用普通表单登录，并以签名 Cookie 维持网关会话。网关用户名为 `viewer`；MuMu 原生用户名为 `admin`，Lite 原生用户名为 `lab-admin`。密码请查看忽略的 `private/access.json`，不要复制到文档或提交。运行数据库和应用登录配置在忽略的 `private/runtime.env`，不使用生产配置；不要把这些文件加入 Git。

ainovel-cli 试用入口已退役。CLI 源码、镜像构建定义和 `cli_workspace`、`cli_config` 卷保留在188，源码检出也保留在本机，可供后续恢复；默认恢复只启动三个网页评估项目，不包含 CLI，也不再发布其浏览器终端入口。手动运行 `sh lab.sh --profile archived-cli up -d cli` 可启动隔离的 CLI 服务，但不会对外暴露入口；CLI 不纳入后续主应用。

## 当前评估范围

- 不配置任何模型 API 密钥、模型服务或远端生成通道，不运行模型测试或付费生成。此评估环境没有 API 或模型配置。
- 应用只连接各自的内部 Docker 网络；只有统一登录网关发布 18020–18022。数据库没有公开端口。
- 数据保存到单独的命名卷，不挂载生产小说数据或 Docker socket。
- MuMu 评估镜像禁用导入时的向量模型初始化，不下载 ONNX 模型。向量记忆、知识索引等依赖该组件的操作不可用；具体补丁见 `mumu/`。
- Lite 使用上游支持的 SQLite、单进程、开发模式 HTTP Cookie，关闭匿名开发用户回退；它是隔离的界面评估配置，非上游正式生产配置。
- Show Me The Story 使用未修改的 Go 程序及空白 API 配置。
- 手写演示数据明确标注为非 AI 生成，只用于观察编辑、导出和持久化。

仓库及准确提交记录在 `sources.lock.json`。本机原始源码分别位于项目根目录 `.reference-sources/{mumu,lite,story,cli}/`，188 有相同结构的独立检出；上游源码保持原样，不并入本仓库，便于后续分析。原许可证保留；Lite 固定提交未发现许可证文件。

新环境可先运行 `python init_private.py --help` 查看私有登录配置初始化选项。初始化脚本仅用于没有现存配置的新环境，发现已有文件时会拒绝覆盖。

## 操作

以下命令仅用于需要时手动恢复三个网页评估项目，不会恢复已退役的 CLI：

```sh
cd /opt/ainovel-reference-lab/deploy/reference-lab
sh lab.sh config --quiet
sh lab.sh ps
sh lab.sh up -d --no-build
sh lab.sh logs --tail=60
sh lab.sh stop
```

`lab.sh` 合并基础配置、MuMu 和 Lite 片段。停止或删除试用容器时保留命名卷；不要使用 `down -v`。

188 构建使用专用 `ainovel-reference-lab` Buildx 构建器，内存上限 1 GiB、CPU 配额一核、BuildKit 并行度 1，不切换服务器的默认构建器。各镜像依次构建以控制峰值资源；MuMu 前端设置 768 MiB Node 堆。前端的 `reportCompressedSize:false` 仅跳过 gzip 大小统计，不改变业务产物或应用行为。运行容器在构建完成后启动：

```sh
sh lab.sh --progress plain build --builder ainovel-reference-lab story
sh lab.sh --progress plain build --builder ainovel-reference-lab lite-api
sh lab.sh --progress plain build --builder ainovel-reference-lab lite
sh lab.sh --progress plain build --builder ainovel-reference-lab mumu
docker buildx stop ainovel-reference-lab
```

## 验收记录

历史验收记录：Linux 认证测试 18 项通过；两组静态检查各 5 项通过；HTTP 表单登录、手写内容保存及导出通过。四个服务曾构建并运行。浏览器曾验证四个入口、MuMu/Lite 原生登录和手写章节、Story 手写角色与世界观、CLI 首次配置向导；八个容器重新创建后，11 项 HTTP 验收通过，三个网页项目的数据及 MuMu TXT 导出保持一致。运行容器均未发生 OOM；应用及认证服务实际出网测试被阻止，专用构建器已停止，原 18110 健康检查为 200。CLI 入口现已退役；上述记录描述退役前状态。静态检查不会访问模型或导入上游应用。
