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

## AINOVEL-20261101-MIGRATE188-02（关联 MIGRATE188-01）

- 时间：2026-11-01T23:15:58.195034+08:00 Asia/Shanghai；代理：/root。
- 目的与文件：补记Git交付及188开发工作树结果，更新DEPLOYMENT.md和CHANGELOG.md；业务代码及运行配置本轮未再改变。
- 实际结果：迁移提交285eef17b4245678fd5663d652d0c6dfde2dbda7已成功推送Gitee main（3243b5a→285eef1）。188初始化main开发工作树，origin为用户指定Gitee仓库；逐项源码同步后git status为空，HEAD与迁移提交相同。数据库转储与Git传输包保存在188项目忽略的backups目录；本机传输暂存均位于D盘。没有复制本机SSH私钥。
- 检查：Git bundle verify通过；188源码工作树干净；原API/网页镜像构建与真实工作流、重建持久化结果沿用01；未因纯文档收尾再次运行付费生成。152保持五容器停止，188五服务运行；未操作81。
- Git与部署：业务迁移提交已推送并部署；本条及部署文档作为收尾提交随后同步，运行镜像无需因文档变更重建。域名TLS与长篇质量验证仍未实施。

## AINOVEL-LAB-PREPARE-20261102T121805

- 时间：2026-11-02T12:18:05.862871+08:00 Asia/Shanghai；代理/root，子任务/root/lab_mumu、/root/lab_lite。
- 目的：按用户要求下载MuMuAINovel、Ai-Novel Lite、Show Me The Story、ainovel-cli，并在188的18020–18030部署独立试用；明确不添加API/密钥/模型服务，不运行付费生成。
- 文件：.gitignore、deploy/reference-lab/下的Compose/Dockerfile/网关/来源锁定/文档/检查；.reference-sources四仓库忽略且保持原样；私有评估登录/数据库/会话凭据在忽略目录private，未使用生产API配置。
- 实现：端口预定18020/21/22/23；网关Basic认证、原生独立账号、Cookie隔离、仅内部网络的应用与数据库；独立数据卷；CLI用非root浏览器终端；MuMu镜像内受固定哈希保护禁用向量模型初始化，原仓库不改；Lite采用上游SQLite评估配置且关闭匿名回退。
- 检查：188可用内存约1377MiB、无Swap，四端口空闲、目标目录不存在；计划独立768MiB串行构建器，未改默认构建器。子任务静态检查各5通过，Root复核各5通过；源SHA见sources.lock.json；部署构建/浏览器/持久化均待验收。
- 备份：D:\A_GPT\GPT-BackUp\GPT-AINovel\2026-11\GPT-AINovel__2026-11-02_121805__源码快照__参考项目试用部署前已提交源码.zip，SHA256 d91c91d9a169bbb652f2fdab85e10f23baf59744ca12031d5490a9cb6db484c0，仅已提交源码CRC/成员SHA通过，不含数据/秘密，非完整备份。
- 状态：尚未提交/推送本轮；188试用部署尚未执行；原18110及其他服务保留，152小说仍停止；没有81操作。

## AINOVEL-LAB-DEPLOY-20261102-01（关联 LAB-PREPARE-20261102T121805）

- 时间：2026-11-02T13:20:02+08:00 Asia/Shanghai；代理：/root，配置子任务 /root/lab_mumu、/root/lab_lite、/root/lab_form_auth；独立审查 /root/lab_deploy_review，诊断 /root/mumu_build_memory，文档 /root/lab_final_docs。
- 目的与文件：完成四个小说项目 Docker 评估，并落实源码下载本机、独立分文件夹保存。涉及 .gitignore、deploy/reference-lab/ 配置/构建/认证/检查/文档和 CHANGELOG.md；主应用 backend/frontend 未改。本机 .reference-sources/{mumu,lite,story,cli} 独立检出均核对来源锁 SHA、git status 干净，188 有相同构建检出；上游源码、私有配置和证据不并入 Gitee。
- 部署：188.68.41.4:/opt/ainovel-reference-lab，独立 Compose 八服务运行；18020 MuMu、18021 Lite、18022 Story、18023 CLI。普通表单及签名Cookie网关、原生账号、独立数据卷；无模型配置/密钥/模型服务/付费生成。应用只接内部网络、数据库无公开端口，不挂载生产数据/配置或Docker socket。CLI仅一客户端、非root原生终端；MuMu镜像内固定哈希补丁禁用向量初始化，原始源码未改。
- 构建修正：五镜像在188串行构建完成。Story首次因缺少docs静态资源失败，补COPY后通过；MuMu首次Node512MiB堆不足，专用构建器由768MiB调至1GiB、Node堆768MiB；Vite并发gzip统计接近限额，停止自己的构建器并关闭reportCompressedSize后成功。默认构建器未改，专用构建器现已停止、缓存保留。
- 认证修正：初版Basic不适配内置浏览器，改表单登录；修复Nginx绝对跳转泄露内部端口。同源Referrer-Policy、CSP nonce、JSON渐进登录、签名Cookie保留严格来源检查。实际点击曾被遗留原生Basic弹窗阻挡，取消弹窗后成功；未将尚未发生POST误记为已确认Origin:null。临时无凭据诊断日志配置已移除。
- 实际检查：Linux认证18/18、两组静态各5通过；独立审查Windows两轮17/18，拒绝未读请求体时WinError10053，其余含新增JSON用例通过，以实际Linux验证补足。浏览器四入口、MuMu/Lite原生登录与手写章节、Story手写角色/世界观、CLI未配置向导均成功；保存Lite截图，未点击模型生成/连接测试。
- 持久化：八容器实际force-recreate，待健康后HTTP11项通过，三个网页项目手写数据及MuMu TXT导出完全一致，指纹de62e2c4ebcb0b95fef67c773a4c718df051765dc65d223bdbdc1fe1da166977。首次紧接重建复验RemoteProtocolError，全部健康后通过。早期辅助脚本换行与重复客户端上下文失败已修复，不是数据丢失；未重复生成演示。一次文档收尾脚本GBK读UTF8失败，改UTF8后继续，无业务变更。
- 运行审计：八容器Running、无OOM，六个有健康检查的均healthy；网关/认证由HTTP验证。MuMu/Lite API/Story/CLI/认证实际公网连接均被阻止；各模型配置空，CLI未生成config.json。一次采样总内存约273MiB。18110健康200且未重建；152仅SSH中转，旧小说服务未启动；未操作81及无关项目。
- 证据：忽略的artifacts/reference-lab/verify-result.json、checkpoint.json、runtime-audit.json、mumu-handwritten.txt、lite-writing.jpg；本机.reference-sources/README.md为源码索引。私有值不写日志或仓库。
- 边界：IP/HTTP界面评估，无模型故不验收生成，MuMu向量功能禁用、CLI仅向导，不证明长篇质量。旧备份仅已提交源码，不包含本次运行卷、不称完整备份。
- Git与部署：本条写入时尚未提交/推送；188部署与验收已完成，随后提交部署配置及记录到用户指定Gitee，源码/私有文件/验收数据不提交。

## AINOVEL-LAB-DEPLOY-20261102-02（关联 DEPLOY-01）

- 时间：2026-11-02T13:21:43+08:00 Asia/Shanghai；代理 /root。
- 目的与文件：CHANGELOG.md 补记交付状态；未再变更业务、网关代码或运行配置。
- Git：部署提交 ef61150dde1cbf5482c32b8934809313e053ebec 已成功推送 Gitee main（a0330fb→ef61150）；31文件，不包含第三方源码、私有凭据或验收数据。提交前Python语法、两组静态各5项、初始化--help、暂存差异检查与实际私有值扫描通过；本条随后作为文档提交同步。
- 部署：188已同步29份公开部署文件并通过合并Compose config及nginx -t；私有配置保留。沿用DEPLOY-01的实际重建、11项HTTP、网络隔离及浏览器验收，不因文档再运行生成或重建。CLI终端连接已关闭，保留入口页供用户进入；四个最终演示标签保留。
- 剩余边界不变：无模型配置，MuMu向量功能禁用；原18110保留、152仅SSH中转、未操作81。

## AINOVEL-INTEGRATE-20261102-01

- 时间：2026-11-02T18:03:28+08:00 Asia/Shanghai；代理/root；架构 /root/novel_arch_astra（architect/Astra），只读来源调查 /root/prompt_evidence、/root/story_memory_evidence，归档配置 /root/retire_cli_config。
- 目的：按用户指定由Astra设计并直接开发部署三参考项目的提示词/Skill/伏笔/记忆/关系图；另按新增要求去除四个体验项目容器。
- 文件与行为：deploy/reference-lab/compose.yaml、gateway/nginx.conf、init_private.py、README.md；本机忽略源码索引补记退役。CLI服务加archived-cli profile，默认不启用，移除18023端口/代理，新环境登录文件不再生成CLI入口。其他三个服务配置保留仅供手动复现。主应用功能实现尚在准备。
- 备份：D:\A_GPT\GPT-BackUp\GPT-AINovel\2026-11\GPT-AINovel__2026-11-02_180009__源码快照__功能整合设计与停用CLI前.zip，SHA256 72a88ec1b3d856ecce434fb5ccec1ed0161c35678b2370fd4eb3c5c390d1694a；提交18cf4b69a503152cf961e0ba772b3a6e1df2aba3源码快照，CRC/成员SHA通过，无数据库/私有配置/参考检出，未应用恢复，非完整备份；D盘索引及管理记录已追加。
- 实际部署：188:/opt/ainovel-reference-lab执行compose down，全部8个专用容器及7个网络已移除；保留卷、镜像、源码、构建缓存。随后按Compose标签查询容器无输出，主项目18110健康HTTP200。未调用模型，未动主应用/无关项目，152仅作SSH中转，未访问81。
- 检查与状态：归档配置diff --check、CLI端口/监听/Profile静态断言和初始化脚本AST通过，未运行初始化或覆盖私有配置；架构与主应用开发/部署未完成，Git本轮尚未提交/推送。

## AINOVEL-INTEGRATE-20261102-02（关联 INTEGRATE-01）

- 时间：2026-11-02T18:36:43+08:00 Asia/Shanghai；代理/root；整体设计与只读复核 /root/novel_arch_astra（architect / gpt-6-astra）；后端 /root/integrate_backend，前端 /root/integrate_frontend。用户已明确授权Astra设计后直接开发部署。
- 目的与文件：整合分类提示词、独立Skill和故事知识；backend/app新prompts/skills/story/dependencies/migrations模块及db/main/services/worker；backend/tests；frontend/App/styles、新Studio组件与策略测试；scripts/verify_postgres.py、verify_live_workflow.py；README、DEPLOYMENT、docs/ARCHITECTURE、CHANGELOG；试用退役配置见01。第三方源码保持忽略且未修改，独立实现行为和原创默认模板。
- 行为：7个内置原创模板、任务分类/题材标签/小说范围、预览/导入预检/导出/历史恢复；五种Skill映射真实Job，模板版本快照及DB幂等键；提取候选不再自动定稿，人工审核原句并事务采纳。五张新表、Memory来源revision/引文/知情/非递归history、Novel上下文版本、关系及事件冻结memory_revision、追加式伏笔时间线和按章截止关系图。旧记忆标legacy不伪造证据，失效历史保留。原编辑/改写提案/导出仍保留，并新增始终可达的手动复制。
- 架构审查与修复：修复普通关系编辑错误恢复过期证据、错误apply非confirm任务的锁序风险、事实原位修改缺历史证据、删除等待锁后旧history覆盖；补针对测试。上下文事实整条纳入/舍弃，继续24k/48k字符预算，不伪称token预算或完整人物POV能力。
- 实际检查：主代理最终backend全量45通过/1跳过/1既有anyio弃用警告，frontend策略5通过；本机和188构建通过。188独立ainovel_verify PostgreSQL使用mock模型验证采纳/来源/图/伏笔、实际并发revision与幂等唯一约束、原流程及导出通过。没有用SQLite结果代替PG锁语义。
- 真实验收与失败记录：演示小说手写正文，真实提取前两次失败且无正式记忆写入；受控诊断定位kind=action不合法，改合法JSON示例/闭合枚举/行动归timeline提示，不放宽校验、不丢非法候选、不无限重试。复验提取成功，浏览器核对证据后采纳；总3调用/1708输入/1268输出token。未改变供应商/密钥/模型配置，未向退役试用项目添加API。
- 浏览器：独立栏目、模板版本与预览、Skill说明、候选采纳、有效记忆、伏笔进展、SVG关系图均查看；390宽截图无页面横向溢出。自动复制显示成功但会话剪贴板读取为空，未确认OS剪贴板；手动复制全文与selection全选已确认。TXT与存储内容核对，未因验证改写原用户作品。
- 备份与部署：API/Worker停止后备份D:\A_GPT\GPT-BackUp\GPT-AINovel\2026-11\GPT-AINovel__2026-11-02_182213__数据备份__提示词记忆升级前数据库.zip，SHA256 fd36b0d0f352f4ad5c82bbf1418c723b57cb25707e7c52e6503f13ef08d21a9c；pg_restore目录/ZIP CRC/成员SHA通过，原dump与镜像回退标签保留，应用恢复未验证、非完整备份。188显式离线迁移schema1，原4小说/6章/31记忆原字段校验一致，.env哈希不变。API/Worker/Web更新并实际再次force-recreate，提示词、记忆、伏笔、实体关系、任务结果与正文均与checkpoint相同；18110恢复健康。数据库/Redis未重建。152仅SSH中转，未操作81；体验8容器/7网络已移除、卷/源码/镜像保留。
- 证据：忽略的artifacts/studio-smoke/verify-result.json、persistence-checkpoint.json、handwritten-demo.txt、prompts-desktop.jpg、memory-review.jpg、skills-mobile.jpg、relations-desktop.jpg、manual-copy.jpg。源码和数据库D盘备份索引、管理记录已追加。私有值不入日志或Git。
- 边界：图谱/伏笔是人工维护及证据引用，非自动全文关系抽取；自动上下文使用Memory和既有小说资料，不额外注入全部图谱/计划；无向量模型、通用任意Skill执行器、完整POV推理或百万字质量保证。自动剪贴板在内置浏览器未独立核实，手动入口可用。
- Git：本条写入时本轮尚未提交/推送；运行镜像已部署，接下来提交并同步188开发源码工作树；最终Git同步另记。build暂存位于D盘和188独立构建目录，未在C盘生成大源码副本。

## AINOVEL-INTEGRATE-20261102-03（关联 INTEGRATE-02）

- 时间：2026-11-02T18:39:36+08:00 Asia/Shanghai；代理/root；文件CHANGELOG.md，仅补记交付状态，不再修改业务或模型配置。
- Git：功能提交563384fa675f6c1435e059990742a8b6f698c864已推送Gitee main（18cf4b6→563384f）；Git bundle校验通过，188:/opt/ainovel由a0330fb快进到同提交，工作树干净，没有复制SSH私钥。本条作为文档提交随后同步。
- 最终检查：主项目5容器Running且无OOM，API/DB/Redis各自health均healthy，公开健康200；Web/Worker无独立healthcheck，已由实际UI/任务验证。体验容器与网络均0，18020–18023连接均拒绝，7个试用卷及源码/镜像保留，自己的Buildx构建器已停止。
- 复制验收补充：最终手动复制入口已部署，浏览器文本框含完整当前正文、标题选项受尊重且selection全选为true；未触发保存或章节revision变化。自动剪贴板读回边界保持02所述。最终API/Worker/Web重建后，13项业务检查中的持久化核对通过；真实用量仍为3调用/1708输入/1268输出，没有额外付费复测。
- 证据：artifacts/studio-smoke/runtime-audit.json及verify-result.json；旧数据与私有配置保留。余项仅为明确未承诺的自动全文图谱、向量检索、通用Skill和完整POV能力，非本轮基础功能遗漏。未操作81，152只管理中转。

## AINOVEL-REFERENCE-PROMPTS-20261102-01

- 时间：2026-11-02T19:31:17+08:00 Asia/Shanghai；代理/root；只读调查/root/catalog_mumu、/root/catalog_lite，后端/root/catalog_backend，前端/root/catalog_frontend；使用smart-development及沿用frontend-design-codex工作流。
- 目的：按用户追加要求收录MuMu/Lite原有提示词内容，按用途分类，不再仅提供7原创；提示词与Skill继续分开，不新增原项目工具执行或模型配置。
- 文件：backend/app/db.py、migrations.py、prompts.py、新prompt_catalog.py及test_prompt_catalog.py；frontend/PromptLibrary/PromptSource/SkillLibrary/shared/studioPolicy/styles与策略测试；scripts/build_reference_prompt_catalog.py、test_reference_prompt_catalog.py；README、DEPLOYMENT、docs/REFERENCE_PROMPTS、CHANGELOG。本机忽略目录.secrets/reference-prompt-catalog/保存私有原文包、MuMu许可副本、NOTICE及summary；artifacts/reference-prompts/保存校验与截图。原始检出保持干净，未执行上游Python或Skill聚合器。
- 内容与实现：静态AST提取MuMu36模板、JSON/受限路径读取Lite7完整预设及66块；用途分10类，固定来源提交/文件/参数/原名/许可/原文SHA及块SHA。43条中16条保留写作规则并适配当前任务资料/输出合同，27条原文参考；各条原文均单独保留。第一次构建遇源Lite条件DSL被防护拒绝，随后将已审核的题材/去味条件转为明示适用条件说明，不执行DSL、不盲目激活全部分支。原文和块未改写。参考条目只能查看复制，不进入生成/Skill选择。
- 数据与API：schema1→2仅为PromptTemplate加source_info JSON；元数据经列表/历史/导出导入/副本/Job快照保留，引用原文SHA验证、UUID5身份和整批事务/锁；同包重复导入跳过，冲突拒绝整批。参考预览不解释源变量，任务选择前后端双重拒绝。原7原创和已有1自定义及其版本保持，当前51条；Skill仍原5条。
- 实际验证：backend全61通过/1跳过（Windows POSIX进程组）/1既有anyio弃用提示；新增16目录测试通过。frontend策略10通过，本机及188生产构建通过；root提取器5测试通过（不执行模块/Skill、路径穿越、原文含CRLF保留、条件失败关闭、适配输出合同剥离）。真实pack本机临时SQLite迁移/干跑/导入/重复全部通过，临时验证库在D盘；不当作历史备份。
- PostgreSQL与生产：独立ainovel_verify库验证原工作流、实际并发/幂等；两并发目录导入一个新增43、另一个跳过43，无冲突；生产干跑43新增、apply43新增、再次apply43跳过。公开API逐条核对43原文和66块hash、全部预览、8既有模板及历史、5Skill不变，参考提交任务422。API/Worker/Web实际force-recreate后同样通过，目录指纹fe858c2642b02cd71313b511c919e26f7aa2177e11985e52848e0108683b19de。
- 浏览器：来源/用途筛选实际MuMu36、Lite7，MuMu章节写作4；Lite v4完整原文14554字符readonly且selection全选；原24块含禁用说明块均保留；390宽页面无横向溢出。桌面/手机截图已保存，保留用户可直接浏览的主项目标签。未调用任何付费生成；未改变模型、密钥或登录配置。
- 备份：源码基线D:\A_GPT\GPT-BackUp\GPT-AINovel\2026-11\GPT-AINovel__2026-11-02_191248__源码快照__原提示词目录导入前基线.zip，SHA256 6c6e0f36a5d8b9a72ef76e49d669dab7434b90f1e0fafd350eb2121d79dee784，为本轮开始时提交dda1db6源码、不含本轮新代码/原文包/数据；数据库D:\A_GPT\GPT-BackUp\GPT-AINovel\2026-11\GPT-AINovel__2026-11-02_191807__数据备份__原提示词目录导入前数据库.zip，SHA256 4b4062fa40bc54e1e0188d8b46997622a717297cc139774d114d3af71d345e5b，API/Worker停止后pg_dump，pg_restore目录/ZIP CRC/成员SHA通过；均未应用恢复、非完整备份，D盘索引及管理记录已追加。旧小说/章节/记忆原字段hash一致，.env hash未变，镜像回退标签与dump保留。
- 部署与边界：188:/opt/ainovel已迁移/导入并运行；来源内容包不进Git或镜像，仅认证实例私有数据，MuMu许可/归属保留、Lite未附许可证状态不隐瞒。16适配是当前任务规则适配，并不运行完整原系统条件/注入引擎；27参考不伪称已接入工具。152仅SSH中转（本轮ssh -G复核为152.136.236.238/root），试用18020–18023保持关闭，未访问81或改无关项目。
- Git：本条写入时尚未提交/推送本轮；下一步提交导入器/索引文档/测试与UI，不包含原文内容包，并同步188开发工作树。构建与传输暂存均D盘/188独立构建目录。

## AINOVEL-REFERENCE-PROMPTS-20261102-02（关联 REFERENCE-PROMPTS-01）

- 时间：2026-11-02T19:35:41+08:00 Asia/Shanghai；代理/root；文件CHANGELOG.md，仅补记最终Git交付和运行检查，无业务改动。
- Git：功能提交a74b7f9cd0d5a82481b5761cd497b1f2fec1d585已成功推送Gitee main（dda1db6→a74b7f9），Git bundle验证通过，188开发工作树快进至同提交且干净；原文包/上游代码/凭据/备份未入Git。提交前实际私有值和完整来源原文/长块排除扫描、Python语法、差异检查通过。本条随后作为文档提交同步。
- 部署与验收：18110公开健康200，5主项目容器Running且无OOM，API/DB/Redis healthy；Web/Worker由实际UI/数据库检查补足，无伪称独立health。43来源条目重建后SHA及原文/66块、全部预览、旧8模板/版本、5Skill均核对通过；原文参考任务422。私有.env未变，自己的Buildx构建器已停止，试用服务与网络0、18020–18023仍关闭，7试用卷保留。
- 证据：artifacts/reference-prompts/verify-result.json、postgres-import.json、catalog-checkpoint.json、runtime-audit.json、catalog-desktop.jpg、catalog-mobile.jpg。未追加付费生成或变更登录，152仅SSH中转，未操作81。
