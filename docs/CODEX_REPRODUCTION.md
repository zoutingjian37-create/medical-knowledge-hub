# Codex 复现与接管手册

这份文档用于让另一台 Windows 电脑上的 Codex 从空目录复现 Medical Knowledge Hub。权威行为由自动化测试和以下状态机共同定义。

## 不可改变的产品边界

- 支持微信、知乎、B站、小红书、抖音公开链接；五个平台统一进入 `KnowledgeJobQueue`。
- 公众号订阅和文献订阅必须是两个独立导航模块；底层仍共享 `Subscription` 存储。支持 `wechat_account`、`journal`、`feed`、`literature_query`，新克隆必须为空白状态，个人配置只能位于 `CONTENT_HUB_STATE_DIR`。
- 微信默认使用本地视觉状态机操作已登录的微信电脑版发现公开链接，再由 OpenCLI 解析单篇链接；其他四个平台复用 OpenCLI，不复制爬虫。
- Codex 只生成预览；只有本地服务的 `/approve` 在用户确认后可以写 Vault。
- 不收集平台密码、Cookie、Token、聊天数据库或微信个人资料。
- 原始正文只进入 `D:\Codex\cache\medical-knowledge-hub`，确认或拒绝后删除，不能提交 Git。
- `微信公众号/`、`证据卡/`、`系统/` 是受管目录，不能成为 Codex 建议的 Wiki 更新目标。
- 文献 PDF 留在 Zotero；只有摘要时必须标为 `abstract` 或“摘要级证据”，不得伪装成全文解析。

## 数据流和状态机

```text
公开 URL / 公众号名称
  → URL 平台识别 / 微信视觉发现与日期归一化
  → 复制公开链接 / OpenCLI 内容读取
  → 平台无关 MarkdownDocument
  → 广告清理与去重
  → pending
  → 本机 Codex CLI + distill-medical-wechat
  → preview_ready
  → 用户查看
     ├─ approve → Obsidian 证据卡/Wiki/日志 → 删除缓存
     └─ trash   → 回收站 → restore 或到期/手动永久删除
```

活动任务接口默认排除 `trashed` 和兼容旧版本的 `rejected` 状态。“查看与保存”采用复选框加顶部工具条，统一提供全选、预览、保存和删除；回收站采用复选框加顶部工具条，统一提供全选、恢复和永久删除。回收站保留期默认 7 天，合法范围为 1–30 天；软删除阶段不得删除缓存或预览，永久删除阶段只允许清理本地任务、缓存、handoff 和 preview，不得删除 Zotero 或 Obsidian 内容。

订阅链路是另一条入口，但与手动链接共用同一提炼和审批边界：

```text
Windows 单任务 / 手动立即运行
  → 已启用订阅
  → RSS/Atom 或 Europe PMC
  → Crossref/OpenAlex 元数据补全
  → 合法全文解析链：Europe PMC → Unpaywall → 医学预印本 → citation_pdf_url
  → DOI / PMID / OpenAlex ID / 规范化 URL 去重
  → Zotero 官方 Connector
     ├─ 开放获取：保存题录与可用 PDF
     └─ 需要权限：等待用户登录并用 Connector 保存
  → KnowledgeJobQueue → Codex Skill → preview_ready
  → 用户 approve 后才写 Obsidian
```

## 从零安装

前置条件：Windows 10/11、Python 3.11+、Node.js 20+、Git、GitHub CLI、Codex CLI、Obsidian Vault、Zotero 9 与官方 Connector。`gh auth status` 和 `codex login status` 必须成功。

```powershell
New-Item -ItemType Directory -Force D:\Codex | Out-Null
gh repo clone zoutingjian37-create/medical-knowledge-hub D:\Codex\medical-knowledge-hub
Set-Location D:\Codex\medical-knowledge-hub

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 `
  -InstallRoot D:\Codex\medical-knowledge-hub `
  -VenvRoot D:\Codex\venvs\medical-knowledge-hub `
  -VaultPath "D:\你的Obsidian目录" `
  -CodexCli "D:\Codex\codex-cli\codex.exe" `
  -CreateDesktopShortcut

powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-platform-engines.ps1
```

在浏览器安装并连接 OpenCLI Browser Bridge；在需要的平台网页保持正常登录。微信电脑版也必须由用户预先登录。编辑 `.env`，确认 `OBSIDIAN_VAULT_PATH`、`OPENCLI_RUNTIME_DIR`、`CONTENT_HUB_CODEX_CLI` 都指向真实路径。需要 Unpaywall DOI 开放全文回退时，另外设置 `CONTENT_HUB_UNPAYWALL_EMAIL`；不要把真实 `.env` 提交 Git。

启动 Zotero，打开本地 API，并用 Connector 完成一次测试保存。`CONTENT_HUB_STATE_DIR` 默认是 `D:\Codex\state\medical-knowledge-hub`；订阅、运行记录、登录接力和预览都在这里，不得加入 Git。`CONTENT_HUB_MANAGE_TASK_SCHEDULER=1` 允许应用同步唯一的当前用户任务 `Medical Knowledge Hub Daily`。

双击桌面 `Medical Knowledge Hub`。快捷方式必须直接指向安装目录的 `start.bat`；不要改回“隐藏 PowerShell”目标，一些 Windows 安全策略会静默移除这种快捷方式。

## 自动验收

```powershell
Set-Location D:\Codex\medical-knowledge-hub
$python = "D:\Codex\venvs\medical-knowledge-hub\Scripts\python.exe"

& $python -m pip check
& $python -m compileall -q app.py routes routes_ext extensions
& $python -m unittest discover -s tests -v
node --test tests\static_assets.test.js
git diff --check

Invoke-RestMethod http://127.0.0.1:5000/api/health
Invoke-RestMethod http://127.0.0.1:5000/api/ext/platforms
Invoke-RestMethod http://127.0.0.1:5000/api/ext/subscriptions
Invoke-RestMethod http://127.0.0.1:5000/api/ext/zotero/status
```

## 订阅链路验收

1. 在 Zotero 中创建并选中测试目录；订阅配置使用完全相同的目录名。
2. 添加一个有 RSS 的开放获取医学期刊，或添加一个 Europe PMC 检索要求。
3. 保持自动化总开关关闭，点击“立即运行”；这一步仍应执行。
4. 检查运行状态依次经过发现、过滤、Zotero 保存、提炼并停在 `waiting_confirmation`。
5. Zotero 必须有题录；有开放 PDF 时附件的 `linkMode` 应为 `imported_url`/导入附件，而不是 `linked_url`。预览的 `evidence_level` 必须反映真实输入层级；PDF 失败必须在运行记录给出原因。
6. 确认前 Vault 不得出现新文件。只有用户在“查看与保存”中批准后才能归档。
7. 对一篇需要权限的文献验证 `waiting_school_login`：软件打开出版社页面，用户自行登录并点 Connector；随后“继续”必须同时检测到 DOI/PMID 题录和 Zotero 受管理 PDF 附件。只有题录时不得进入提炼。
8. 关闭总开关后计划任务不得自动处理；暂停单条订阅生效；删除订阅不得删除已有 Zotero 或 Obsidian 内容。
9. 在公众号订阅文本框中修改并保存虚构测试号；确认个人配置只写入项目外的 `CONTENT_HUB_STATE_DIR`，仓库仍为空白默认值。

## 真实链接验收

1. 打开 `/inbox.html`，粘贴任一受支持公开链接。
2. 页面必须自动识别平台并调用 `POST /api/ext/platforms/queue`。
3. 等待 Codex 完成；任务必须进入 `preview_ready`。
4. 确认前记录 Vault 的 `.md` 数量，前后必须不变。
5. 预览应有 PECO、方法概览、主要结论、创新雷达、迁移元素、潜在选题和 Wiki 建议；不得包含课程、社群、关注或咨询引流。
6. `wiki_updates` 不得指向受管目录，也不得为单篇文章随意新建范式页。
7. 仅在测试 Vault 或用户明确确认后点击归档；随后检查 `证据卡/`、宽主题 Wiki、`系统/log.md` 与缓存删除。

## 代码导航

- `routes_ext/platforms.py`：统一链接 API 和旧微信兼容入口。
- `extensions/platforms/url_router.py`：纯 URL 平台识别。
- `extensions/platforms/opencli/adapter.py`：四个平台共享适配器。
- `extensions/platforms/wechat/vision.py`：微信日期归一化、文章行识别和具体日期去重规则。
- `extensions/platforms/wechat/windows_session.py`：默认的当前微信视觉状态机与公开链接复制。
- `extensions/platforms/wechat/discovery.py`：视觉发现默认入口与显式公开搜索兼容入口。
- `extensions/platforms/wechat/parser.py`：微信公开链接解析。
- `extensions/processing/job_queue.py`：广告清理、去重与入队。
- `extensions/processing/compiler.py`：Codex 预览、路径校验和确认写入。
- `extensions/subscriptions/`：订阅存储、发现、去重、Zotero、流水线、调度和运行状态。
- `extensions/subscriptions/fulltext.py`：Europe PMC、Unpaywall、预印本和开放页面 PDF 的有序解析链。
- `routes_ext/subscriptions.py`：订阅 CRUD、自动化、运行、登录接力与 Zotero 状态 API。
- `static/inbox.html`：五平台手动链接 UI。
- `static/wechat-subscriptions.html`：公众号名称批量编辑、启停与立即运行 UI。
- `static/literature-subscriptions.html`：期刊、RSS/Atom、文献检索和 Zotero UI。
- `static/review.html`：公众号文章与文献的统一勾选、预览、确认和软删除 UI。
- `static/trash.html`：回收站保留期、批量恢复和永久删除 UI。
- `static/subscriptions.html`：兼容旧地址，只重定向到公众号订阅。
- `skills/distill-medical-literature/`：可复用医学文献提炼契约。
- `skills/distill-medical-wechat/`：公众号和其他公开平台医学讲解提炼契约。

## 常见失败的定位顺序

1. 桌面图标消失：重新运行安装器；检查快捷方式目标是否为 `start.bat`。
2. 服务不起：看 `D:\Codex\state\medical-knowledge-hub\logs\server.err.log`。
3. 链接不支持：核对域名和内容 URL 形态，不要放宽到任意域名。
4. 微信视觉发现失败：确认微信已登录且主窗口可见，再查看 `D:\Codex\state\medical-knowledge-hub\diagnostics` 的最新截图。不要把个人截图提交 Git。
5. OpenCLI 不可用：检查 `/api/ext/platforms/{platform}/health`、Browser Bridge 和网页登录状态；已复制的微信公开链接也可以在“粘贴链接”中重试。
6. Codex 失败：检查 `.env` 的 CLI 路径、`login status` 和 Skill 安装目录。
7. Vault 不写：确认任务是 `preview_ready`、用户点击了确认、Vault 路径是根目录。
8. RSS 失败：确认 URL 是公开的 HTTP(S) Feed；内网、回环、链路本地地址会被 SSRF 防护拒绝。
9. Zotero 等待目录：在 Zotero 左侧选择与订阅完全同名的目录。官方本地 API 只读，应用不会静默创建目录。
10. 学校权限等待：由用户在浏览器登录并点击官方 Connector；不得把学校 Cookie 或 Token 加到 `.env`。

## 给接管 Codex 的执行指令

先阅读本文件、README、设计文档和测试。优先修复现有适配边界，不引入第二套平台爬虫或通用期刊爬虫。公众号日常发现必须优先使用 `mode=wechat_ui`，并保持视觉发现、公开链接解析和知识提炼三层独立；医学文献优先 RSS/Atom、Europe PMC、Crossref/OpenAlex；Computer Use 只用于人工诊断，不是生产采集器。任何代码修改先写失败测试，再实现；完成前必须执行全量测试、一条真实公众号公开链接和一条真实开放获取文献到 `preview_ready` 的验收。不得提交 `.env`、缓存、订阅、任务状态、原文、Cookie、Token、Vault 文件、诊断截图或发布压缩包。
