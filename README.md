# Medical Knowledge Hub

由 **zoutingjian37-create** 设计和维护的本地医学知识提炼软件。它同时支持五个平台的公开链接和医学文献订阅：先用代码发现、过滤、去重并保存 Zotero，再只对入选内容调用 Codex Skill；只有用户确认后才写入 Obsidian。

仓库：<https://github.com/zoutingjian37-create/medical-knowledge-hub>

## 工作流程

```text
手动公开链接 / 公众号 / 期刊 / RSS / 文献检索要求
  → OpenCLI、RSS/Atom 或 Europe PMC 发现候选内容
  → 日期、关键词、广告和重复项代码过滤
  → 文献题录与可用 PDF 保存到 Zotero
  → 创建临时提炼任务
  → Codex + distill-medical-literature 提炼
  → 用户查看变更预览
  → 确认后写入 Obsidian
  → 删除临时正文；PDF 留在 Zotero
```

公众号名称查找默认走 OpenCLI 的公开微信搜索，并用 Browser Bridge 把搜索结果安全解析为 `mp.weixin.qq.com` 链接；采集时还会核对正文作者，避免同名或搜索误命中。它不操作桌面微信，也不接收 Cookie、Token 或平台密码。

`pywechat127` 的微信 UI 发现器只保留为用户明确选择的慢速备用通道。该通道需要逐篇收藏、再从收藏中复制链接，受微信界面版本和窗口布局影响，不能视为稳定或完整的公众号历史接口。公开搜索同样可能受收录范围和验证页影响；失败会明确报错，不会把不完整结果伪装成成功。

## 五分钟复现

### 1. 准备环境

- Windows 10/11
- Python 3.11 或更高版本
- Node.js 20 或更高版本
- Git、GitHub CLI 和已登录的 Codex CLI
- Obsidian 及一个已经创建的 Vault
- Zotero 9 和官方 Zotero Connector；文献订阅需要先启动一次 Zotero
- OpenCLI 1.8.6 与 Browser Bridge；公众号公开查找及知乎、B站、小红书、抖音读取均会复用它

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
3. 在“查看与保存”中检查提炼结果。
4. 点击“确认保存”后才会更新 Obsidian。

原始正文只保存在项目外的临时缓存中，不进入 Git 或 Obsidian。

## 按公众号名称发现文章

1. 打开“公众号文章发现”。
2. 每行输入一个公众号名称，选择“快速公开搜索（推荐）”。
3. 程序通过 OpenCLI 搜索公开候选文章并解析真实微信链接，不控制桌面微信。
4. 选择采集后，程序解析正文、校验正文作者并进入统一待处理列表。
5. 只有需要补查公开搜索未收录内容时，才手动选择“微信界面补全（慢速备用）”。

## 每日订阅

打开“订阅中心”，可以新增、暂停、恢复、删除或立即运行以下来源：

- 微信公众号名称：复用 OpenCLI 公开搜索，适合发现已被公开搜索收录的候选文章，不保证完整历史。
- 期刊：优先使用主页声明的 RSS/Atom；没有 Feed 时使用 ISSN 或期刊名查询 Europe PMC。
- RSS/Atom：适合每日轮询，因为它只读取新增条目，不需要控制浏览器或桌面微信。
- 文献检索：使用 Europe PMC/PubMed 风格的结构化查询，可附加关键词和自然语言筛选要求。

总开关默认关闭；开启后默认每天 08:30 运行、每天最多提炼 5 篇。关闭总开关或暂停单条订阅不会删除 Zotero、运行历史或 Obsidian 内容；“立即运行”仍可使用。错过执行时间时，Windows 任务会在电脑下次可用时补跑。

个人订阅保存在 `D:\Codex\state\medical-knowledge-hub`，不进入 Git。页面提供“导出个人配置”和“导入个人配置”，用于换电脑迁移；导出文件不包含密码、Cookie 或 Token。

## Zotero 与学校登录

1. 启动 Zotero 9，并在左侧选择准备接收文献的目录。订阅中的“Zotero 目录”必须与当前选中目录同名。
2. 开放获取文献会通过 Zotero 官方 Connector 的 `saveItems` + `saveAttachment` 保存题录和可用 PDF；PDF 上限 50 MB。下载失败时仍保留题录、改用摘要级证据，并在运行记录中显示原因。
3. 需要学校权限时，运行记录会显示“打开登录页面”。你亲自登录学校或出版社账号，再点击浏览器中的 Zotero Connector 保存。
4. 回到软件点击“已保存到 Zotero，继续”。软件只按 DOI/PMID 检查题录是否已入库，不读取或保存账号、密码、Cookie 或 Token。

Zotero 的官方本地 Web API 目前只读，因此在不配置云端 API Key、也不安装自定义 Zotero 插件的前提下，软件不能静默创建目录。选错目录时会明确暂停，而不是把文献保存到错误位置。

## 哪些步骤消耗 Codex token

RSS/Atom、Europe PMC 查询、日期/关键词筛选、去重、Zotero 保存、运行调度和 Obsidian 审批均由本地代码执行，不调用大模型。只有入选文献进入 `distill-medical-literature` 提炼时消耗 Codex token；每日上限用于控制这部分成本。

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
- 如果微信结果出现临时验证页，程序会等待后重试一次；仍失败时请稍后再运行，不要频繁刷新。

### Codex 无法生成预览

- 确认 Codex CLI 已登录。
- 检查 `CONTENT_HUB_CODEX_CLI` 和 `distill-medical-literature` Skill。

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
