# Medical Knowledge Hub

由 **zoutingjian37-create** 设计和维护的本地医学知识提炼软件。粘贴微信、知乎、B站、小红书或抖音公开链接后，软件提取正文或字幕、过滤广告，并生成等待确认的知识预览；只有用户确认后才写入 Obsidian。

仓库：<https://github.com/zoutingjian37-create/medical-knowledge-hub>

## 工作流程

```text
公开链接
  → 自动识别平台
  → OpenCLI 提取正文或字幕
  → 去广告并创建临时任务
  → Codex + distill-medical-literature 提炼
  → 用户查看变更预览
  → 确认后写入 Obsidian
  → 删除临时正文
```

微信 UI 发现器是可选辅助层。手动粘贴公开链接不依赖公众号后台登录，也不接收 Cookie、Token 或平台密码。

## 五分钟复现

### 1. 准备环境

- Windows 10/11
- Python 3.11 或更高版本
- Node.js 20 或更高版本
- Git、GitHub CLI 和已登录的 Codex CLI
- Obsidian 及一个已经创建的 Vault
- OpenCLI；知乎、B站、小红书和抖音需要按其说明连接 Browser Bridge

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

浏览器会打开 <http://127.0.0.1:5000/admin.html>。

## 手动使用

1. 在“粘贴链接”中输入任一支持平台的公开链接。
2. 点击“提取并生成预览”。
3. 在“查看与保存”中检查提炼结果。
4. 点击“确认保存”后才会更新 Obsidian。

原始正文只保存在项目外的临时缓存中，不进入 Git 或 Obsidian。

## 测试

```powershell
python -m unittest discover -s tests -v
node --test tests\static_assets.test.js
```

## 验收清单

- `GET /api/health` 返回 `200`。
- 五个平台的公开链接能进入统一待处理列表。
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

### Codex 无法生成预览

- 确认 Codex CLI 已登录。
- 检查 `CONTENT_HUB_CODEX_CLI` 和 `distill-medical-literature` Skill。

### 无法保存到 Obsidian

- 检查 `OBSIDIAN_VAULT_PATH` 指向 Vault 根目录。
- 修改 `.env` 后重启本地服务。

## 作者与外部组件

本仓库的新 Git 历史只记录本项目的独立实现。OpenCLI 和 pywechat 作为单独安装的外部运行时，通过公开接口调用，不合并其源代码。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本项目使用 [GNU AGPL v3](LICENSE)。
