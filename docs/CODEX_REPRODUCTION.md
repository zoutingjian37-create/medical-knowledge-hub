# Codex 复现与接管手册

这份文档用于让另一台 Windows 电脑上的 Codex 从空目录复现 Medical Knowledge Hub。权威行为由自动化测试和以下状态机共同定义。

## 不可改变的产品边界

- 支持微信、知乎、B站、小红书、抖音公开链接；五个平台统一进入 `KnowledgeJobQueue`。
- 微信使用公开链接解析；其他四个平台复用 OpenCLI 与 Browser Bridge，不复制爬虫。
- Codex 只生成预览；只有本地服务的 `/approve` 在用户确认后可以写 Vault。
- 不收集平台密码、Cookie、Token、聊天数据库或微信个人资料。
- 原始正文只进入 `D:\Codex\cache\medical-knowledge-hub`，确认或拒绝后删除，不能提交 Git。
- `微信公众号/`、`证据卡/`、`系统/` 是受管目录，不能成为 Codex 建议的 Wiki 更新目标。

## 数据流和状态机

```text
公开 URL
  → URL 平台识别
  → OpenCLI/微信链接解析器
  → 平台无关 MarkdownDocument
  → 广告清理与去重
  → pending
  → 本机 Codex CLI + distill-medical-wechat
  → preview_ready
  → 用户查看
     ├─ approve → Obsidian 证据卡/Wiki/日志 → 删除缓存
     └─ reject  → 删除缓存，不写 Obsidian
```

## 从零安装

前置条件：Windows 10/11、Python 3.11+、Node.js 20+、Git、GitHub CLI、Codex CLI、Obsidian Vault。`gh auth status` 和 `codex login status` 必须成功。

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

在浏览器安装并连接 OpenCLI Browser Bridge；在需要的平台网页保持正常登录。编辑 `.env`，确认 `OBSIDIAN_VAULT_PATH`、`OPENCLI_RUNTIME_DIR`、`CONTENT_HUB_CODEX_CLI` 都指向真实路径。

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
```

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
- `extensions/platforms/wechat/parser.py`：微信公开链接解析。
- `extensions/processing/job_queue.py`：广告清理、去重与入队。
- `extensions/processing/compiler.py`：Codex 预览、路径校验和确认写入。
- `static/inbox.html`：五平台手动链接 UI。
- `skills/distill-medical-wechat/`：可复用知识提炼契约。

## 常见失败的定位顺序

1. 桌面图标消失：重新运行安装器；检查快捷方式目标是否为 `start.bat`。
2. 服务不起：看 `D:\Codex\state\medical-knowledge-hub\logs\server.err.log`。
3. 链接不支持：核对域名和内容 URL 形态，不要放宽到任意域名。
4. OpenCLI 不可用：检查 `/api/ext/platforms/{platform}/health`、Browser Bridge 和网页登录状态。
5. Codex 失败：检查 `.env` 的 CLI 路径、`login status` 和 Skill 安装目录。
6. Vault 不写：确认任务是 `preview_ready`、用户点击了确认、Vault 路径是根目录。

## 给接管 Codex 的执行指令

先阅读本文件、README、设计文档和测试。优先修复现有适配边界，不引入第二套平台爬虫。任何代码修改先写失败测试，再实现；完成前必须执行全量测试和至少一条真实公开链接到 `preview_ready` 的验收。不得提交 `.env`、缓存、任务状态、原文、Cookie、Token、Vault 文件或发布压缩包。
