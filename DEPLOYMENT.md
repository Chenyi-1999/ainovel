# 当前部署与验证记录

部署服务器：`itemkeep-server`（152.136.236.238），目录 `/opt/ainovel`。

网页地址：http://152.136.236.238:18110 。当前使用 IP 和 HTTP；绑定域名并配置 HTTPS 后，设置 `COOKIE_SECURE=true`。

## 已完成

- 独立 Docker Compose 项目：网页、API、写作 Worker、PostgreSQL、Redis。
- 数据库和队列不公开端口，运行密钥只在服务器 `.env`；网页不会显示密钥。
- Linux 容器内 30 项后端回归测试通过（包括子进程后代超时清理）；前端生产构建通过。
- 真实 PostgreSQL 集成测试通过：模拟模型的大纲与顺序写作、定稿记忆、200/409 并发修改保护、记忆失效、版本与导出。
- 公网浏览器操作验证：登录、正文保存、复制、TXT 导出和手动添加记忆。
- 桌面与 390px 手机截图检查；修复手机横向溢出。
- API、Worker 与网页重启后，保存和导出的正文指纹完全一致。

## 模型接入诊断与当前配置

AgentRouter：普通 OpenAI/Anthropic HTTP 请求返回 `unauthorized_client_error`。使用官方 Claude Code 2.1.291，通过临时私有网络桥接，已真正调用 `deepseek-v4-flash`，完成大纲、452 字章节（含自动审稿）、11 条定稿记忆及 TXT 导出。四次实际请求返回统计为输入 5,379 token、输出 6,126 token。该验证运行在独立数据库，未使用模拟模型。

其主域名在云服务器存在解析异常与 TLS 重置；大陆备用域名返回验证网页。临时桥接依赖本机网络，仅用于诊断。长期使用 AgentRouter 仍需稳定且获准使用的网络出口。已提供 `compose.cli.yaml` 可选客户端方案，普通 API 镜像保持轻量。

用户随后提供火山方舟密钥：云服务器直连及鉴权成功，因此生产配置改为 `https://ark.cn-beijing.volces.com/api/v3`、HTTP 通道。候选默认 `doubao-seed-2-1-pro-260628`；但该账号对它和 `deepseek-v4-1-flash-260910` 均返回 `ModelNotOpen`，需要在控制台开通模型或提供已开通的 Model ID / Endpoint ID。模型目录不是账号授权列表；网页已明确提示。

火山方舟的实际章节生成尚待模型开通验收。一次样章验证也不能证明百万字连续性或长期文笔质量。

## 维护

```sh
ssh itemkeep-server
cd /opt/ainovel
docker compose ps
docker compose logs --tail=50 api worker
sh scripts/backup.sh
```

更新代码后使用 `docker compose up -d --build`。若服务器默认选择了其他项目的 Buildx Builder，可以只为本次命令设置 `BUILDX_BUILDER=default`；不需要改变全局构建器。构建下载源可通过 Dockerfile 的 `PIP_INDEX_URL` 和 `NPM_CONFIG_REGISTRY` 构建参数调整。

切换模型服务时修改服务器 `.env` 的 `LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL`，然后重新创建 API、Worker 容器。若已有网页保存的模型设置，还需在网页更新各用途模型；域名变更时删除旧地址设置或同步更新。

登录密码以哈希存放在服务器；最初生成的登录信息只保存在本机被 Git 忽略的 `.secrets/login.txt`，不在仓库中。
