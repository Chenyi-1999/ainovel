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


## AINOVEL-LENGTH-20261102-01

- 时间：2026-11-02T21:08:52.971527+08:00 Asia/Shanghai；代理/root；后端/root/length_backend_fix，前端/root/length_frontend_fix，只读诊断与复核/root/length_diagnosis；使用smart-development及frontend-design-codex。
- 目的与证据：用户设置4800但生成不足，生产只读核对最新写作任务payload确为4800，正文1313字符/排空白1279字仍succeeded。代码只检查100字符且审稿无篇幅约束；并非漏传该任务参数，无证据证明token上限截断。既有任务未记录首稿，不能凭usage token定位缩水阶段。
- 文件与行为：backend/app/length.py、worker.py、skills.py及test_length.py/test_workflow.py；frontend/App、SkillLibrary、styles、新wordCount.ts及测试；scripts/verify_postgres.py、README、docs/ARCHITECTURE、CHANGELOG。按正文非空白Unicode码点计数（含标点、不含标题），目标整数±10%；原有审稿调用负责扩压，最终返回及存储前硬校验，越界修订不覆盖合格首稿、报告说明。每章仍最多2次调用，批次已保存进度保留；新成功结果附last_length/lengths。正文/Skill共用设置，页面显示允许范围及实际计数；旧章节不自动重写，confirm/rewrite合同不变。
- 实际检查：后端targeted45通过，全量78通过/1 Windows POSIX跳过/1既有anyio警告；前端12通过，本机及188两镜像构建通过；独立只读审查无阻断。188独立ainovel_verify PostgreSQL（mock模型）通过批量写作/逐章实际计数与统计、记忆审核、来源失效、实际并发锁/幂等及导出；未操作用户作品。真实4800生成与浏览器/生产更新尚未执行，不伪称通过。
- 备份：D盘已提交基线5e642f3源码快照，ZIP CRC/成员SHA通过，SHA256 b186a6d6b390c8b7a7341e46118fd997d14ef53a90406a25be1b1023328a4d9b；任务开始时干净，不含进行中修复/私有配置/数据/来源包，应用恢复未测、非完整备份；归档索引/管理记录已追加。
- 状态：本轮尚未Git提交/推送或切换生产镜像；188专用暂存/构建器用于构建和独立PG验证，下一步一致性数据库备份后代码更新（无DDL/目录导入）与真实新测试书。152仅SSH管理中转，未操作81或无关服务。


## AINOVEL-LENGTH-20261102-02（关联 LENGTH-01）

- 时间：2026-11-02T21:28:27.109315+08:00 Asia/Shanghai；代理/root；只读架构及审查/root/length_generation_design（architect/Astra），分节实现/root/length_scene_fix。
- 实际部署与备份：188 API/Worker停止后pg_dump，D盘数据备份GPT-AINovel__2026-11-02_210854__数据备份__字数验收修复前数据库.zip，SHA256 f911821fe1c8296d5ec8e3f590751968d48e4d99a3665efcd92ebf2bcc2a7aa8；pg_restore目录/ZIP CRC/成员SHA通过，未实际恢复，非完整备份，源dump及镜像回退标签保留。01代码已部署，5小说/9章/32记忆原字段hash及.envhash不变，无DDL及目录导入。
- 失败与证据：独立新测试书4800字，第一次write+audit最终1468字，2调用7642输入/2188输出token，硬校验fail且无Chapter。并非token预算耗尽。Astra冻结分节JSON+按ID局部整体替换方案后第二次实测仍3488字，2调用17559输入/4308输出；实际write/audit均max18000、finish_reason=stop，首稿3338（733/636/553/463/408/545），审稿仅把首节改883，总3488，仍无Chapter。两次失败完整保留，不缩小目标或重复相同提示试运气；所有既有用户章节hash一致。合计4调用25201输入/6496输出token，失败可能计费，不伪称通过。
- 文件与行为：backend/app/length.py、worker.py、gateway.py、test_length.py/test_gateway_length.py/test_workflow.py/test_claude_cli.py；分节严格唯一完整ID、局部替换不追加、只有全章总±10硬验收；系统级篇幅/格式合同与审稿模板规则保留。新增日志只含字数/token数及白名单finish_reason，不记录正文/提示词/凭据。针对57通过，全118通过/1Windows POSIX跳过/既有anyio警告；Astra只读复核无阻断；188独立PG及构建通过，分节版本实际部署且chapters/memories/prompts完整表hash/.env一致。前端设置互通与失败显示已检查，390宽无页面横向溢出。
- 进一步调整：两调用不能稳定交付已被实测，已向用户明确说明改用有界逐节write+一次audit，4800每次尝试最多7、6000最多9、20章最多180，重试另计。Astra冻结固定节数、按已写实际动态分配剩余预算、每调用前行锁续租/取消检查、最终整章事务保存；不写中间用户Chapter、不提前把半章当完整。此逐节版正在实现，尚未部署/真实验证，不能将118测试结果归于未完成新版本。
- 运行与Git：第三阶段前端已13测试通过/本机构建通过，远端构建中；一次新暂存目录缺失导致前端上传失败，创建该专用目录后重试构建，不涉及生产变更。Git尚未提交/推送；证据artifacts/length-smoke/{attempt-1-failed,attempt-2-scenes,attempt-2-metadata}.json及失败截图，私有文件不入Git。188为目标，152仅SSH中转，未操作81/无关服务。


## AINOVEL-LENGTH-20261102-03（关联 LENGTH-02）

- 时间：2026-11-02T21:41:05.241423+08:00 Asia/Shanghai；代理/root；有界方案设计及只读复核/root/length_generation_design（architect/Astra），后端/root/length_scene_fix，前端/root/length_frontend_fix；根代理整合和独立PG/生产/浏览器验收。
- 最终文件与行为：backend/app/length.py、worker.py、skills.py、gateway.py；tests/test_length.py/test_gateway_length.py/test_workflow.py/test_claude_cli.py；frontend/App/SkillLibrary/styles/wordCount.ts及tests/word-count.test.mjs；scripts/verify_postgres.py、新verify_length_lease_postgres.py；README、DEPLOYMENT、docs/ARCHITECTURE、CHANGELOG。固定ceil(target/800)次单节write加一次audit，不循环补写；按已生成实数动态分配200..原目标预算，完整前节输入与首/中/末节约束保留；仅当前唯一ID、仅首标题采用、审稿按ID整体替换。字数仍全章±10硬验收，最终存储事务再次核对。每call前Job行锁校owner/status/cancel并续600秒租约，网络调用不持锁，不存中间Chapter。每次尝试4800最多7、6000最多9、20章最多180，重试/恢复另计；Skill和页面说明同步，字数与批次上限实时计算。旧章节/模板/原文/记忆不自动修改。
- 实际测试：最终后端targeted73通过、全量134通过/1Windows POSIX跳过/既有anyio警告；前端13通过，本机及188生产构建通过。Astra只读复核无阻断。188独立PG验证工作流/实际并发revision和幂等/计数统计通过；新增独立PG脚本验证续租阻止后续接管、renew与SKIP LOCKED实际竞态只有一个owner、旧owner不能续租或通过保存围栏，无模型调用，删除的仅脚本新建测试行。没有用SQLite控制流测试替代PG锁验证。
- 真实生成：同一独立测试作品/同一4800目标与冻结MuMu模板，唯一逐节尝试成功，正文5099（允许4320–5280），首稿即合格、审稿未修改；实际节长828/1190/866/1018/862/335，动态预算800/795/696/639/449/200，所有7次finish_reason=stop，max_tokens按预算5600..7400、审稿18000。6write+1audit共69139输入/5332输出token；含02两个失败累计11次调用94340输入/11828输出token，不遗漏失败用量。TXT含完整正文，所有此前用户章节hash一致且版本不变；测试书保留供查看。样本仅证明本次达标，修辞/悬念仍需作者审阅，不保证所有题材/模型每次成功或长期文学质量。
- 生产与数据：188:/opt/ainovel运行逐节版，无DDL/目录再导入，更新前后chapters/memories/prompt_templates完整表hash及.env一致。DB/Redis未重建，专用旧镜像/dump保留。前端最后修正桌面换行避免计数说明挤压书名，已独立重建Web；立即健康探测曾连接重置，随后公开健康200，不重复付费测试。152仅SSH管理中转，未操作81/无关服务，试用服务保持停用。
- 浏览器：桌面/390宽结果显示目标4800、实际5099、允许范围一致；编辑器计数5099；主编辑与Skill设置双向同步，4800显示7调用、5000显示8调用；完整手动复制正文与编辑器一致、readonly且全选，未追加OS自动剪贴板读回承诺。手机无页面横向溢出，控制台warning/error为空；最终CSS换行在生产桌面复核通过。证据artifacts/length-smoke/verify-result.json、attempt-3-sequential.json、attempt-3-metadata.json、chapter.txt及截图。备份沿用01/02，D盘索引和管理记录保留；非完整备份，应用恢复未测。
- Git状态：本条写入时本轮尚未提交/推送；接下来提交上述公开代码/测试/文档并同步188开发工作树、停止本次专用构建器和检查最终运行状态，不包含私有来源包、凭据、测试正文或归档。


## AINOVEL-LENGTH-20261102-04（关联 LENGTH-03）

- 时间：2026-11-02T21:43:14.093576+08:00 Asia/Shanghai；代理/root；文件CHANGELOG.md，仅补记交付状态，不再变更业务、模型配置或付费复测。
- Git：功能提交13f920386a430efd08f189855377081da6473b5b已推送Gitee main（5e642f3→13f9203）；19份公开文件。暂存范围/私有登录实际值/密钥形态排除及差异检查通过；无私有来源包、凭据、验收正文或归档。D盘bundle校验通过，188开发工作树快进到同提交且干净，.env哈希仍一致。本条随后以文档提交同步。
- 最终运行：188主项目5容器Running且无OOM，API/DB/Redis health均healthy，Web/Worker以实际UI及7调用任务验证，无伪称独立healthcheck；公开18110健康200。试用容器/网络0、18020–18023仍关闭，7卷保留，自己的Buildx已停止。未动152服务及81/无关项目。
- 最终浏览器：最后布局修正后重新加载，章节及5099字仍存在，桌面完整信息+换行操作栏通过，390宽scrollWidth375≤390，无横向溢出。复制全文一致/全选及调用提示沿用03实测；保留结果页可查看4800→5099。手机/桌面截图与runtime-audit.json已保存。本条未追加生成、数据库变更或新备份；业务/样本边界沿用03。

## AINOVEL-GITHUB-LINK-20261102-8fa5a084

- 时间：2026-11-02T21:58:23+08:00 Asia/Shanghai；代理 /root；本地只读检查 /root/repository_readiness。
- 目的：接收用户提供的 GitHub SSH 仓库地址，核对管理权限并关联当前项目；尚未收到明确的首次发布范围。
- 影响文件：本机 .git/config 新增 github 远程 git@github.com:Chenyi-1999/ainovel.git；CHANGELOG.md 追加本条。原 origin 仍为 Gitee，main 上游未改变；无业务代码变更。
- 实际检查：GitHub 连接账号 Chenyi-1999；目标 Chenyi-1999/ainovel 为 public、size=0、默认 main，返回 admin/maintain/push/pull 权限。操作前工作树干净，main 为 ee3eaba，共 12 条提交。已检查适用本地指令路径、最新日志、Git 忽略规则及跟踪文件名/大小；.env、.secrets、私有评估目录与来源检出均被忽略，未发现已跟踪的这些私有路径；未执行完整历史内容秘密扫描，不据此保证历史无敏感内容。
- SSH 检查：目标解析为 github.com，未配置 ProxyJump/ProxyCommand；22 端口在认证前关闭，git ls-remote 退出 128。备用 ssh.github.com:443 可到达但 StrictHostKeyChecking 因无已知 ED25519 主机键而拒绝，未关闭主机校验、未新增密钥或修改 SSH 配置。GitHub CLI 未安装，本机 Git 使用 manager 凭据助手；未读取/输出凭据。
- 验证与剩余事项：远程地址读取一致；文档差异检查在本条追加后执行。未运行应用测试（仅 Git 关联及记录）。GitHub 连接的管理权限已确认，本机 SSH 推送通道尚未验证成功；首次公开上传范围仍待用户指定。
- Git/部署：未提交、未推送；本条留在工作区。未部署、未访问任何项目服务器（包括 81、152、188），未变更远端源码、数据或仓库设置。

## AINOVEL-GITHUB-CLI-SETUP-20261102-eeeb2fc2

- 时间：2026-11-02T22:05:46+08:00 Asia/Shanghai；代理 /root；Codespaces 本地只读评估 /root/codespaces_readiness。
- 目的：按用户要求代办本机 GitHub CLI、HTTPS 认证及 Codespaces 访问准备，需要用户输入时提示。
- 影响范围：启动 winget 安装 GitHub.cli 2.103.3；CHANGELOG.md 追加本条。沿用上一条的 github 远程，当前尚未切换 HTTPS；没有业务代码或运行配置变更。
- 实际检查与进度：本机 gh 未安装、winget 1.29.380 可用；官方 GitHub CLI MSI 已下载且 winget 安装包哈希验证通过。安装进程仍运行，检测到 Windows consent 窗口“GitHub CLI 正在请求你的许可”，已请用户点击系统授权；此时未确认安装完成，未开始 OAuth 登录。
- Codespaces 评估：仅阅读公开配置及 .env.example；项目无 .devcontainer，现有 Compose 包含 web/api/worker/PostgreSQL/Redis，公开入口18110，完整运行需要独立的数据库/会话/登录配置及模型API配置。没有读取 .env/.secrets，没有启动环境或调用模型。
- 验证/剩余：等待 Windows 安装授权，然后核对CLI版本、GitHub账号/仓库权限、HTTPS连接和Codespaces可访问性；完整云端运行配置及创建尚未执行。应用测试未运行（本轮为工具与认证准备）。
- Git/部署：未提交、未推送，原有CHANGELOG修改保留；未创建/启动Codespace、未发布、未部署、未访问81/152/188等任何项目服务器。未写入或输出密码、Token、SSH私钥或登录授权码。

## AINOVEL-GITHUB-CLI-AUTH-20261102-3303217f

- 时间：2026-11-02T22:12:50+08:00 Asia/Shanghai；代理 /root；关联 GITHUB-CLI-SETUP-20261102-eeeb2fc2。
- 目的：用户已确认 Windows 安装许可，继续完成本机 GitHub HTTPS 与 Codespaces 授权准备。
- 影响范围：GitHub CLI 2.103.3 已安装至 C:\Program Files\GitHub CLI\gh.exe，winget 成功退出；本机 .git/config 的 github 远程改为 https://github.com/Chenyi-1999/ainovel.git，原 Gitee origin 及 main 上游保留；CHANGELOG.md 追加本条。
- 实际检查：CLI --version 返回 2.103.3；登录前 auth status 确认无已登录账号。已启动 GitHub 官方浏览器设备授权，选择 HTTPS 及 Git 凭据集成，额外申请 codespace 权限；已打开官方授权页并提示用户本人登录 Chenyi-1999。一次性设备码未写入本记录或项目文件。
- 当前状态：等待用户完成 GitHub 授权，尚未确认 OAuth 成功、凭据存储方式、HTTPS 推送权限或 Codespaces API 访问。地址回读通过，应用测试未运行（无应用变更）；后续将进行认证/API/Git 只读或 dry-run 验证。
- Git/部署：未提交、未推送、未发布；未创建/启动 Codespace、未部署、未访问任何项目服务器。未读取或输出密码、Token、SSH私钥；既有日志与工作区修改保留。

## AINOVEL-GITHUB-CLI-VERIFIED-20261102-eccd6c0a

- 时间：2026-11-02T22:23:55+08:00 Asia/Shanghai；代理 /root；关联 GITHUB-CLI-AUTH-20261102-3303217f、GITHUB-CLI-SETUP-20261102-eeeb2fc2。
- 目的：用户已完成 GitHub 官方授权，验证并完成本机 GitHub HTTPS、仓库管理与 Codespaces 访问配置。
- 影响范围：此前安装的 GitHub CLI 2.103.3、本机 CLI 的 github.com HTTPS 登录配置与系统凭据库；本机 .git/config 的 github 远程为 https://github.com/Chenyi-1999/ainovel.git；CHANGELOG.md 追加本条。原 Gitee origin 与 main 上游仍为 origin；应用代码和运行配置未变。
- 实际认证：auth login 成功退出；auth status 成功，当前账号 Chenyi-1999、Active=true、存储位置 keyring、Git 协议 https。授权范围为 codespace/gist/read:org/repo/workflow；没有打印、读取或写入项目中的Token/密码/私钥。现有 Git credential helper 为 manager，未另行替换全局其他主机配置。
- 实际检查：仓库API确认 Chenyi-1999/ainovel 为 public、非归档，admin/maintain/pull/push/triage 均为 true；git push --no-verify --dry-run github main:main 成功退出0，预演显示将新建main，未真实推送且跳过本地pre-push hook。仓库 Codespaces API 返回成功，total_count=0；仅确认访问权限，不代表已创建/启动环境或验证配额。最终 git ls-remote 成功且无refs，CLI协议回读https。
- 验证边界：尚无 .devcontainer，完整项目云端运行需后续准备独立开发配置；未运行应用测试/模型调用（仅认证配置）。本条追加后执行 git diff --check；本次不包含首次公开源码/历史上传。
- Git/部署：未提交、未推送、未发布Release；未创建/启动Codespace、未部署、未访问81/152/188等任何项目服务器。仅CHANGELOG保留工作区修改，已有记录未覆盖。


## AINOVEL-PUBLISH-20261102T223527-01

- 时间：2026-11-02T22:36:56.709904+08:00 Asia/Shanghai；代理/root；本地历史只读检查/root/publish_history_check（explorer）。目的：按用户“提交并发布”，提交既有GitHub关联/认证记录，并首次将当前项目完整main历史同步GitHub，继续保留Gitee和188。
- 文件：CHANGELOG.md。保留他轮已追加的四条GitHub配置/验证记录，新增本条；无业务代码、依赖、模型配置或数据库变更，原Gitee origin和main上游不改。GitHub HTTPS目标Chenyi-1999/ainovel实际为PUBLIC/empty，Gitee main为ee3eaba。
- 发布检查：检查ee3eaba可达12提交、230唯一对象/162blob，真实.env、.secrets、.reference-sources、deploy/reference-lab/private、artifacts、数据库及私钥文件路径未跟踪；指定令牌/私钥/长键赋值模式命中0。仅.env.example占位符及明确测试假值；无catalog.json/上游原文包。公开deploy/reference-lab代码/配置与来源索引为有意保留的项目文件，private目录不包含，不能将其误判为应删整个公开目录；未重写历史。模式扫描不保证穷尽所有秘密类别。新增CHANGELOG差异扫描及diff--check通过，仅既有换行提示。
- 188只读核对：/opt/ainovel HEAD=ee3eaba且干净，5主容器Running/noOOM，API/DB/Redis healthy，Web/Worker无独立healthcheck，公开18110健康200。仅文档变更，无需重建容器或重复此前134后端/13前端/真实5099字测试；本轮不运行新应用测试或模型调用，不改数据/凭据。
- 边界：未创建Codespace、GitHub Release或新版本tag；本次发布是现有源码main。未访问81；ssh-G核对itemkeep-server仍为152.136.236.238/root，152仅作188管理中转，不操作该服务器项目。D盘新专用publish-transfer目录用于后续Git bundle传输，不称新备份。
- Git/部署状态：本条写入时尚未提交/推送；下一步提交并推送main到Gitee及GitHub，之后记录实际发布结果并将最终文档快进同步188，不重建已在线应用。未打印/写入Token、密码或私钥。
