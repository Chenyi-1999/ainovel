# 当前部署与验证记录

部署服务器：`itemkeep-server`（152.136.236.238），目录 `/opt/ainovel`。

网页地址：http://152.136.236.238:18110 。当前使用 IP 和 HTTP；绑定域名并配置 HTTPS 后，设置 `COOKIE_SECURE=true`。

## 已完成

- 独立 Docker Compose 项目：网页、API、写作 Worker、PostgreSQL、Redis。
- 数据库和队列不公开端口，运行密钥只在服务器 `.env`；网页不会显示密钥。
- 12 项后端回归测试通过；前端生产构建通过。
- 真实 PostgreSQL 集成测试通过：模拟模型的大纲与顺序写作、定稿记忆、200/409 并发修改保护、记忆失效、版本与导出。
- 公网浏览器操作验证：登录、正文保存、复制、TXT 导出和手动添加记忆。
- 桌面与 390px 手机截图检查；修复手机横向溢出。
- API、Worker 与网页重启后，保存和导出的正文指纹完全一致。

## 尚未通过的真实模型测试

按照用户提供的说明，接口配置为 `https://agentrouter.org/v1`，默认模型 `deepseek-v4-flash`，也测试了 `gpt-5.6-sol`。

普通 HTTP 客户端收到网关的 HTTP 401 `unauthorized_client_error`（`unauthorized client detected`）。服务器本身到主域名的连接也失败；官方大陆备用入口返回网页验证内容，未获得模型结果。必须由网关提供允许普通 API 调用的接入方式，或更换可用兼容接口，才能完成真实大纲和章节生成验收。程序不会伪装其他客户端绕过限制。

上述模拟模型测试只证明软件流程正确，不能作为真实模型可用、文笔质量或百万字连续性的证明。

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
