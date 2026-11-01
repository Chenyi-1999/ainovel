# 当前部署与验证记录

当前服务器：德国 `188.68.41.4`，项目目录 `/opt/ainovel`，网页地址 http://188.68.41.4:18110/ 。开发、构建和运行均以此服务器为目标。当前使用 IP 和 HTTP；配置域名与 HTTPS 后应设置 `COOKIE_SECURE=true`。

188 上已建立 `main` 分支的 Git 开发工作树，远程仓库为 `git@gitee.com:star1999/ainovel.git`；未向服务器复制本机 SSH 私钥。代码更新仍需重建相应镜像后生效。

模型配置为 `https://api.openai.com/v1`、`gpt-4.1-mini`、`LLM_TRANSPORT=http`，大纲、写作、审稿、记忆均使用该模型。服务器直接调用官方 API，运行不依赖本机或 152 的模型转发。密钥只保存在权限为 `600` 的服务器 `.env`，不提交仓库。网页登录密码沿用迁移前设置，本机私密登录文件 `.secrets/login.txt` 的地址已更新。

原 `152.136.236.238:/opt/ainovel` 的五个项目容器已全部停止，源码和数据卷保留。不要同时恢复旧站写作任务。迁移前一致性备份位于本机 `D:\A_GPT\GPT-BackUp\GPT-AINovel\2026-11\`，含源码、PostgreSQL 快照和 Windows DPAPI 加密运行配置；不含依赖、Git 内部目录或缓存，不称完整备份。

## 实际验证

- 德国服务器 SSH 登录成功；本机直连在认证前被关闭，当前维护 SSH 经 152 中转，仅用于管理连接。
- 已恢复原数据库，恢复时核对为 1 本小说、0 章、2 个失败任务；保留原作品和登录配置。
- 德国服务器上 API、网页镜像构建成功，独立 Compose 项目的五个服务运行正常；数据库与 Redis 不公开端口。
- 官方模型列表及最小文本生成成功。完整真实工作流通过：几句话生成大纲、第一章、定稿记忆、选段改写与保存、历史版本、记忆失效后重新定稿、第二章、审稿、TXT 导出和文件字节一致性。
- 成功验收一轮共 9 次 `gpt-4.1-mini` 调用，输入 19,811 token、输出 5,835 token。另一次流程已完成生成，在 Windows 本地验收文件写入时因换行转换导致字节比较失败；脚本改为保存原始响应字节后复验通过。两个测试作品保留，供查看文笔。
- 本机后端回归为 29 通过、1 跳过；跳过项为仅适用于 POSIX 的进程清理检查。完整验收记录和样章位于被 Git 忽略的 `artifacts/germany-smoke/`。
- 重新创建 API、Worker、网页容器后，3 本作品、4 章正文、记忆、章节修订状态和 TXT 导出指纹保持一致；模型配置与原登录仍有效。

当前未填写单价，页面估算费用 `0` 不代表免费，实际费用以供应商账单为准。短篇工作流验收不能证明百万字连续性、精确字数控制或长期文笔质量。本次公网浏览器确认了新站登录页；复制按钮的浏览器交互验证沿用迁移前同版前端结果，迁移后另做了正文与 TXT 内容核对。

## 新环境配置

以下命令仅用于创建新环境；脚本拒绝覆盖已有 `.env`，不要用它重置现有部署：

```sh
python scripts/setup_env.py --key-file PATH_TO_PROTECTED_KEY_FILE --base-url https://api.openai.com/v1 --model gpt-4.1-mini --transport http --public-url http://188.68.41.4:18110
```

`--public-url` 默认 `http://localhost:18110`，只写入生成的本机登录说明。模型密钥不应出现在命令参数或仓库中。

## 维护

在德国服务器执行：

```sh
cd /opt/ainovel
docker compose ps
docker compose logs --tail=50 api worker
docker compose build --builder default api web
docker compose up -d --no-build
sh scripts/backup.sh
```

只操作 `ainovel` 项目，保留服务器其他服务；不要执行 `docker compose down -v`。修改源码后需重建相应镜像。若更换模型供应商，修改私密 `.env` 并重新创建 API、Worker；网页中已保存的接口和四种用途模型也需要同步。

完整验收会创建测试作品并产生真实模型费用，可显式执行：

```sh
python scripts/verify_live_workflow.py --base-url http://188.68.41.4:18110 --password-file .secrets/login.txt --output-dir artifacts/germany-smoke
```

## 历史接入诊断

152 的网络无法直连 OpenAI 官方 API。此前 AgentRouter 普通 HTTP 请求受客户端限制，真实 Claude Code 通道只通过临时网络桥接完成过独立测试；火山方舟鉴权成功，但所测模型未对账号开通。这些是历史诊断，当前生产配置使用德国服务器直连 OpenAI。
