# Medical Knowledge Hub

由 **zoutingjian37-create** 设计和维护的本地医学知识提炼软件。它同时支持五个平台的公开链接和医学文献订阅：先用代码发现、过滤、去重并保存 Zotero，再只对入选内容调用 Codex Skill；只有用户确认后才写入 Obsidian。

仓库：<https://github.com/zoutingjian37-create/medical-knowledge-hub>

## 工作流程

```text
手动公开链接 / 公众号 / 期刊 / RSS / 文献检索要求
  → 微信视觉发现、OpenCLI、RSS/Atom 或 Europe PMC 获取候选内容
  → 日期、关键词、广告和重复项代码过滤
  → 文献题录与可用 PDF 保存到 Zotero
  → 创建临时提炼任务
  → Codex + 对应来源的提炼 Skill
  → 用户查看变更预览
  → 确认后写入 Obsidian
  → 删除临时正文；PDF 留在 Zotero
```

公众号名称查找默认操作用户已经登录的微信电脑版：识别搜索框、精确公众号、文章列表和日期，打开入选文章后点击“复制链接”。程序只保留公开的 `mp.weixin.qq.com` 链接，不读取 Cookie、Token、聊天数据库或账号密码。链接交给独立 OpenCLI 解析器后，仍会核对正文作者，避免同名或搜索误命中。

视觉发现借鉴 `pywechat` 将微信交互封装为代码驱动 RPA 的边界，但当前微信 4.1 的 UI Automation 树不可见，因此本项目改用本地中文 OCR、文字锚点、相对窗口位置和状态复核。`pywechat127` 仅保留为旧版微信兼容后端，不是默认路径。微信升级后如果文字或布局变化，程序会保存诊断截图并明确失败，不会继续盲点。

## 五分钟复现

### 1. 准备环境

- Windows 10/11
- Python 3.11 或更高版本
- Node.js 20 或更高版本
- Git、GitHub CLI 和已登录的 Codex CLI
- Obsidian 及一个已经创建的 Vault
- Zotero 9 和官方 Zotero Connector；文献订阅需要先启动一次 Zotero
- 微信电脑版 4.x，使用前由用户完成登录；安装器会安装本地 OCR 与窗口自动化依赖
- OpenCLI 1.8.6 与 Browser Bridge；公众号链接解析及知乎、B站、小红书、抖音读取会复用它

### 2. 克隆并安装

```powershell
New-Item -ItemType Directory -Force D:\Codex | Out-Null
gh repo clone zoutingjian37-create/medical-knowledge-hub D:\Codex\medical-knowledge-hub
Set-Location D:\Codex\medical-knowledge-hub
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -CreateDesktopShortcut
```

安装器默认把虚拟环境、缓存和运行状态放在 `D:\Codex`，并把知识提炼 Skill 安装到 Codex 的技能目录。

### 3. 配置 Obsidian

编辑项目根目录的 `.env`：

```dotenv
OBSIDIAN_VAULT_PATH=D:\你的Obsidian目录
```

### 4. 启动

双击桌面上的 `Medical Knowledge Hub`，或执行：

```powershell
.\start.bat
```

浏览器会打开 <http://127.0.0.1:5000/admin.html>。首次克隆的订阅列表为空，不包含作者的公众号、期刊或研究方向。

## 手动使用

1. 在“粘贴链接”中输入任一支持平台的公开链接。
2. 点击“提取并生成预览”。
3. 在“查看与保存”中勾选一篇或多篇内容，使用右上角的“预览”检查完整提炼结果。
4. 只有点击“保存到 Obsidian”并确认后才会更新知识库；同一工具条也支持全选和批量移入回收站。

原始正文只保存在项目外的临时缓存中，不进入 Git 或 Obsidian。

“默认用 Skill 提炼”开关控制新任务是否自动生成预览；关闭后任务只进入待处理列表，可以随后手动提炼。删除任务会先移入本地回收站，活动列表立即隐藏。回收站采用文件管理器式批量操作：逐项勾选或全选后，可恢复所选或彻底清理所选；默认保留 7 天，可设置为 1–30 天。永久删除只清理本地任务元数据、临时正文和预览，不会删除 Zotero 文献或已经写入 Obsidian 的内容。

## 按公众号名称发现文章

1. 先登录微信电脑版，再打开“公众号文章”。
2. 每行输入一个完整公众号名称，选择开始日期、结束日期和数量上限。
3. 程序进入微信“搜一搜”，精确匹配公众号，并在“文章”页识别日期。
4. `今天`、`昨天`、`星期几` 和 `月日` 都会先转换为北京时间的具体日期；打开文章后用正文完整日期复核。
5. 程序复制公开链接，按“公众号 + 具体发布日期 + 规范化链接”去重，再解析正文并进入统一待处理列表。

## 每日订阅

订阅分为两个互不混用的页面：

- “公众号订阅”：在同一个文本框中维护公众号名称，每行一个；点击“修改”后编辑，点击“保存”后作为本机默认公众号列表。程序使用已登录的微信电脑版发现文章，下载并提炼后进入 Obsidian 确认流程。
- “文献订阅”：新增、暂停、恢复、删除或立即运行期刊、RSS/Atom 和文献检索；发现结果先进入 Zotero，再由文献 Skill 提炼并进入 Obsidian 确认流程。

支持的来源包括：

- 微信公众号名称：使用已登录的微信电脑版发现文章；每日任务按上次成功日期继续，最终以具体发布日期去重。
- 期刊：优先使用主页声明的 RSS/Atom；没有 Feed 时使用 ISSN 或期刊名查询 Europe PMC。
- RSS/Atom：适合每日轮询，因为它只读取新增条目，不需要控制浏览器或桌面微信。
- 文献检索：使用 Europe PMC/PubMed 风格的结构化查询，可附加关键词和自然语言筛选要求。

总开关默认关闭；开启后默认每天 08:30 运行、每天最多提炼 5 篇。关闭总开关或暂停单条订阅不会删除 Zotero、运行历史或 Obsidian 内容；“立即运行”仍可使用。错过执行时间时，Windows 任务会在电脑下次可用时补跑。

个人订阅保存在 `D:\Codex\state\medical-knowledge-hub`，不进入 Git。开源仓库首次打开为空白状态，不携带作者的公众号、期刊或研究方向。

## Zotero 与学校登录

1. 启动 Zotero 9，并在左侧选择准备接收文献的目录。订阅中的“Zotero 目录”必须与当前选中目录同名。
2. 开放获取文献按“来源已给出的 PDF → Europe PMC → Unpaywall → arXiv/bioRxiv/medRxiv → 开放页面 `citation_pdf_url`”依次查找合法全文，再通过 Zotero 官方 Connector 的 `saveItems` + `saveAttachment` 保存题录和可用 PDF；PDF 上限 50 MB。
3. Unpaywall 是可选回退来源。在 `.env` 设置 `CONTENT_HUB_UNPAYWALL_EMAIL=你的联系邮箱` 后启用；邮箱只随 Unpaywall API 请求发送，不写入 Git 或文献笔记。
4. 解析器全部失败时仍保留题录并明确标记摘要级证据。远端 PDF 返回 401/403，或文献本身需要权限时，运行记录会显示“打开登录页面”。你亲自登录学校或出版社账号，再点击浏览器中的 Zotero Connector 保存。
5. 回到软件点击“已用 Zotero Connector 保存 PDF，继续”。软件会按 DOI/PMID 找到题录，并确认 Zotero 中已有受管理的 PDF 附件；只有题录、没有 PDF 时仍保持“等待学校登录”。程序不读取或保存账号、密码、Cookie 或 Token。

Zotero 的官方本地 Web API 目前只读，因此在不配置云端 API Key、也不安装自定义 Zotero 插件的前提下，软件不能静默创建目录。选错目录时会明确暂停，而不是把文献保存到错误位置。

## 哪些步骤消耗 Codex token

微信窗口识别与公开链接复制、OpenCLI 解析、RSS/Atom、Europe PMC 查询、日期/关键词筛选、去重、Zotero 保存、运行调度和 Obsidian 审批均由本地代码执行，不调用大模型。只有入选内容进入 `distill-medical-wechat` 或 `distill-medical-literature` 提炼时消耗 Codex token；每日上限用于控制这部分成本。

## 测试

```powershell
python -m unittest discover -s tests -v
node --test tests\static_assets.test.js
```

## 验收清单

- `GET /api/health` 返回 `200`。
- 五个平台的公开链接能进入统一待处理列表。
- RSS 或 Europe PMC 订阅能发现文献并保存到当前选中的 Zotero 目录。
- 总开关关闭后计划任务不自动处理；手动立即运行仍可用。
- 未确认的预览不会写入 Obsidian。
- `.env`、Cookie、Token、缓存和 Vault 内容没有进入 Git。
- 桌面快捷方式指向新仓库的 `start.bat`。

## 故障排查

### 页面无法打开

- 运行 `python -m uvicorn app:app --host 127.0.0.1 --port 5000` 查看错误。
- 检查 <http://127.0.0.1:5000/api/health>。

### OpenCLI 无法读取内容

- 执行 `install-platform-engines.ps1`。
- 检查 `OPENCLI_RUNTIME_DIR` 和 Browser Bridge 状态。
- 微信链接已经复制但正文解析失败时，检查 OpenCLI 运行时和 Browser Bridge；可以把同一公开链接粘贴到“粘贴链接”重试。

### 微信没有找到搜索框或文章日期

- 确认微信电脑版已经登录，并保持主窗口可见。
- 运行期间不要操作微信窗口或修改系统缩放。
- 查看 `D:\Codex\state\medical-knowledge-hub\diagnostics` 中最新诊断截图；微信升级后可据此更新文字锚点，不需要重写解析、去重或 Obsidian 流程。

### Codex 无法生成预览

- 确认 Codex CLI 已登录。
- 检查 `CONTENT_HUB_CODEX_CLI`、`distill-medical-wechat` 和 `distill-medical-literature` Skill。

### Zotero 显示未连接或等待目录

- 启动 Zotero 9，确认“设置 → 高级 → 允许本机其他应用与 Zotero 通信”已开启。
- 安装官方 Zotero Connector，并确认浏览器能将一篇文献保存到 Zotero。
- 在 Zotero 左侧选中与订阅配置完全同名的目录，再点击继续；“我的文库”是根目录，不会自动创建子目录。

### 无法保存到 Obsidian

- 检查 `OBSIDIAN_VAULT_PATH` 指向 Vault 根目录。
- 修改 `.env` 后重启本地服务。

## 作者与外部组件

本仓库的新 Git 历史只记录本项目的独立实现。OpenCLI 和 pywechat 作为单独安装的外部运行时，通过公开接口调用，不合并其源代码。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本项目使用 [GNU AGPL v3](LICENSE)。
