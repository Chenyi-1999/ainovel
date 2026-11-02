# 四个小说项目的独立界面试用

目标服务器 `188.68.41.4`，目录 `/opt/ainovel-reference-lab`。四个评估服务均已构建并运行；生产小说工作台仍在 `18110`。本目录只提供评估部署，不替换现有小说代码。

| 入口 | 项目 | 形态 |
| --- | --- | --- |
| http://188.68.41.4:18020/ | MuMuAINovel | 网页；另需原生管理员登录 |
| http://188.68.41.4:18021/ | Ai-Novel Lite | 网页；另需原生管理员登录 |
| http://188.68.41.4:18022/ | Show Me The Story | 网页 |
| http://188.68.41.4:18023/ | ainovel-cli | 说明页及 `/terminal/` 原生终端 |

四个入口均使用普通表单登录，并以签名 Cookie 维持网关会话。网关用户名为 `viewer`；MuMu 原生用户名为 `admin`，Lite 原生用户名为 `lab-admin`。密码请查看忽略的 `private/access.json`，不要复制到文档或提交。运行数据库和应用登录配置在忽略的 `private/runtime.env`，不使用生产配置；不要把这些文件加入 Git。

## 当前评估范围

- 不配置任何模型 API 密钥、模型服务或远端生成通道，不运行模型测试或付费生成。此评估环境没有 API 或模型配置。
- 应用只连接各自的内部 Docker 网络；只有统一登录网关发布 18020–18023。数据库没有公开端口。
- 数据保存到单独的命名卷，不挂载生产小说数据或 Docker socket。
- MuMu 评估镜像禁用导入时的向量模型初始化，不下载 ONNX 模型。向量记忆、知识索引等依赖该组件的操作不可用；具体补丁见 `mumu/`。
- Lite 使用上游支持的 SQLite、单进程、开发模式 HTTP Cookie，关闭匿名开发用户回退；它是隔离的界面评估配置，非上游正式生产配置。
- Show Me The Story 使用未修改的 Go 程序及空白 API 配置。
- ainovel-cli 原生没有网页创作工作台，浏览器终端只可运行其首次原生配置向导。未配置模型时不能进入实际生成流程；只允许一个终端连接，不提供系统 shell。
- 手写演示数据明确标注为非 AI 生成，只用于观察编辑、导出和持久化。

仓库及准确提交记录在 `sources.lock.json`。本机原始源码分别位于项目根目录 `.reference-sources/{mumu,lite,story,cli}/`，188 有相同结构的独立检出；上游源码保持原样，不并入本仓库，便于后续分析。原许可证保留；Lite 固定提交未发现许可证文件。

新环境可先运行 `python init_private.py --help` 查看私有登录配置初始化选项。初始化脚本仅用于没有现存配置的新环境，发现已有文件时会拒绝覆盖。

## 操作

```sh
cd /opt/ainovel-reference-lab/deploy/reference-lab
sh lab.sh config --quiet
sh lab.sh ps
sh lab.sh up -d --no-build
sh lab.sh logs --tail=60
sh lab.sh stop
```

`lab.sh` 合并基础配置、MuMu 和 Lite 片段。停止或删除试用容器时保留命名卷；不要使用 `down -v`。

188 构建使用专用 `ainovel-reference-lab` Buildx 构建器，内存上限 1 GiB、CPU 配额一核、BuildKit 并行度 1，不切换服务器的默认构建器。各镜像依次构建以控制峰值资源；MuMu 前端设置 768 MiB Node 堆。前端的 `reportCompressedSize:false` 仅跳过 gzip 大小统计，不改变业务产物或应用行为。各镜像依次构建，运行容器在构建完成后启动：

```sh
sh lab.sh --progress plain build --builder ainovel-reference-lab cli
sh lab.sh --progress plain build --builder ainovel-reference-lab story
sh lab.sh --progress plain build --builder ainovel-reference-lab lite-api
sh lab.sh --progress plain build --builder ainovel-reference-lab lite
sh lab.sh --progress plain build --builder ainovel-reference-lab mumu
docker buildx stop ainovel-reference-lab
```

## 验收记录

已完成：Linux 认证测试 18 项通过；两组静态检查各 5 项通过；HTTP 表单登录、手写内容保存及导出通过。四个服务已构建并运行。真实浏览器已验证四个入口、MuMu/Lite 原生登录和手写章节、Story 手写角色与世界观、CLI 首次配置向导；八个容器实际重新创建后，11 项 HTTP 验收通过，三个网页项目的数据及 MuMu TXT 导出保持一致。运行容器均未发生 OOM；应用及认证服务实际出网测试被阻止，专用构建器已停止，原 18110 健康检查为 200。静态检查不会访问模型或导入上游应用。
