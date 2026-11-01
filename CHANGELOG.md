# CHANGELOG

## AINOVEL-20261101-OPENAI-VERIFY-01

- 时间：2026-11-01 18:25:15 Asia/Shanghai
- 代理：/root
- 目的：核验用户授权给本项目使用的 OpenAI API 项目密钥，以及现有云端部署的接入条件。
- 影响文件：CHANGELOG.md；Git 忽略的本地私有诊断脚本与凭据文件。未修改业务代码、模型配置或数据库。
- 行为与实际检查：官方模型列表请求 HTTP 200；本机 gpt-4.1-mini 最小生成返回 OK，输入 11 token、输出 1 token；152.136.236.238 主机访问官方 API 失败，提示 Connection refused。远端临时凭据文件已删除。未访问 81 服务器。
- 待解决：现有云端应用访问官方 API 的网络条件；不将本机验证等同于云端可用或完整小说流程验收。
- Git：本条记录尚未提交、未推送。
- 部署：未部署更新、未重启应用；原工作台为 http://152.136.236.238:18110/。
## AINOVEL-20261101-OPENAI-VERIFY-02（关联 01）

- 时间：2026-11-01 18:26:00 Asia/Shanghai
- 代理：/root
- 目的：补充实际应用容器内的网络验证结果。
- 影响文件：CHANGELOG.md；远端临时无凭据网络检查脚本已从应用容器删除。
- 实际检查：152.136.236.238 上 ainovel-api-1 容器访问 api.openai.com 返回 Network is unreachable；与主机失败结果共同表明当前线上环境尚不能直接调用官方 API。本机最小生成成功的结论保持不变。
- 待解决：可访问官方 API 且位于受支持地区的模型调用部署环境。
- Git：未提交、未推送。部署：未修改运行配置，未重启服务，未执行全量测试（无业务代码变更）。
## AINOVEL-20261101-GERMAN188-VERIFY-01

- 时间：2026-11-01 22:35:59 Asia/Shanghai
- 代理：/root
- 目的：按用户要求，从历史聊天及指定本机凭据目录查找德国 188 服务器，测试 SSH 登录及 OpenAI 官方 API。
- 影响文件：CHANGELOG.md；Git 忽略的本地诊断脚本 .secrets/test_german_server.py、隔离依赖 .secrets/ssh-tools（Paramiko 4.0.0）；本机 SSH known_hosts 新增目标公钥记录。未修改业务代码或依赖清单。
- 目标与路径：188.68.41.4:22，用户 root；SSH 经已确认的 152.136.236.238 中转，未访问 81 服务器。密码仅从用户指定的现有文件读入内存，未复制或记录其值；API 密钥经加密 SSH stdin 提供给远程进程，未写入德国服务器文件。
- 实际检查：本机直连 SSH 在认证前被关闭；中转后现有 SSH 密钥未获授权，随后使用指定文件中的密码认证成功。Windows Paramiko 的管道转发发生兼容性错误，已改用仅本机监听的临时 TCP 转发。
- 最终结果：root 登录成功；德国服务器显式禁用环境代理并禁止 HTTP 重定向，直接访问 OpenAI 模型列表 HTTP 200，共 130 个模型；gpt-4.1-mini 实际生成 HTTP 200，返回 OK。两次德国文本测试均输入 11 token、输出 1 token。临时转发进程已关闭，检查剩余匹配进程为 0。
- 剩余事项：本轮只完成登录与 API 验证，尚未迁移小说服务、部署应用、检查 Docker 容量或验证完整小说流程。没有修改远端已有项目或服务配置。
- Git：未提交、未推送。部署：未部署、未重启；现有小说工作台仍在 http://152.136.236.238:18110/，188 服务器尚无本项目部署地址。
## AINOVEL-20261101-MIGRATE188-01

- 时间：2026-11-01T23:13:44.277804+08:00 Asia/Shanghai；代理：/root，文档子任务 /root/migration_docs，独立只读审查 /root/migration_review。
- 目的：按用户要求停止152小说服务，迁移德国188并验证OpenAI在小说工作流中的适用性；只操作本项目，未访问81服务器。
- 影响文件：DEPLOYMENT.md、scripts/setup_env.py、scripts/verify_live_workflow.py、CHANGELOG.md；私密诊断脚本、登录地址及188的.env不入库。新参数--public-url去除生成登录说明的152硬编码；验收脚本按原始字节保存TXT，防止Windows换行转换。
- 备份：D:\A_GPT\GPT-BackUp\GPT-AINovel\2026-11\GPT-AINovel__2026-11-01_225934__修改前备份__152迁移至188.zip；SHA256 c967b2ad8311425b5ad49cc777530ad270bc16b0399b80656630dcdf2ac6f888。D盘直接打包并通过CRC/成员SHA/pg_restore目录校验，运行配置为DPAPI加密；不含Git/依赖/缓存，不称完整备份。188实际恢复原库1小说/0章/2失败任务并可登录；源数据卷保留。
- 部署：152:/opt/ainovel五容器全部停止；188.68.41.4:/opt/ainovel独立Compose五服务已构建启动并健康。官方API https://api.openai.com/v1，四角色gpt-4.1-mini，HTTP通道；密钥.env权限600。SSH管理经152中转，188运行时直接联网，无本机桥接依赖；其他应用未修改。
- 实际检查：后端29通过/1跳过（Windows无POSIX进程组）；前端德国生产构建通过。完整真实工作流通过大纲、两章、定稿记忆、选段改写与保存、历史版本、记忆失效/重新定稿、审稿及TXT导出；成功轮9调用/19811输入/5835输出token。前一轮生成均成功，但本地文本保存换行导致字节检查失败，证据和作品保留；修复后复验成功。两轮合计18调用/38149输入/10428输出，不将页面单价未设的0估算当免费。
- 持久化：重新创建API/Worker/网页后3小说/4章、记忆、修订状态及导出SHA保持一致；汇总指纹a51abc7f3219bfac4e52b1eded00f2fb8c1d82b35faf0a2ea546eb2df2cfbb21，模型列表130项。实际TXT逐章全文匹配；公网浏览器显示188登录页。复制按钮本次未重新登录浏览器验证，沿用同版前端既有测试。
- 证据：artifacts/germany-smoke/ainovel-smoke-20261101T150755Z.json、对应TXT、restart-result.json及artifacts/migration-backend-tests.xml（Git忽略）。只读审查无阻断问题；补充第一章改写全文导出断言并对现有线上导出逐章核对。语法、--help及git diff --check通过。
- 剩余边界：仍为IP/HTTP，未配置域名TLS；短篇测试不能证明百万字连续性或长期文笔质量；已测试gpt-4.1-mini，不宣称列表内全部模型可用。
- Git：本条写入时尚未提交/推送；下一步将含本条和相关变更提交Gitee，并在188初始化对应Git开发工作树。业务部署与实际验收已完成，Git同步结果另记。
