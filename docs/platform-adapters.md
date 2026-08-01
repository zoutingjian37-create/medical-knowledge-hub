# 多平台采集适配说明

## 外部采集运行时

知乎、B站、小红书和抖音复用 `jackwener/OpenCLI` 作为本地采集引擎。微信公众号分成两层：本项目代码操作已登录的微信电脑版发现公开链接，OpenCLI 只解析已经复制出的单篇公开链接。本仓库维护的边界是：

1. 调用 OpenCLI 的只读命令并要求 JSON 或 Markdown 输出；
2. 校验链接确实属于目标平台；
3. 转换为本项目现有的 `NormalizedContent`；
4. 后续继续使用同一套任务、清洗、附件和 Obsidian 写入流程。

没有复制 OpenCLI 的浏览器控制、登录、签名或下载实现，也没有为五个平台各建一套解析后台。微信窗口发现是独立、可替换的输入层，不与解析、提炼和归档耦合。

OpenCLI 使用 Apache-2.0 许可证，提供命令行和结构化输出。本仓库通过公开 CLI 接口调用它，不包含或修改其源代码。

## 安装与连接

运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-platform-engines.ps1
```

默认安装到 `D:\Codex\tools\opencli-runtime`。然后在 Chrome、Edge 或其他 Chromium 浏览器安装 OpenCLI Browser Bridge，并在该浏览器正常登录所需平台。软件通过本机 `127.0.0.1:19825` 与连接器通信，不接收用户账号密码。

## 当前能力边界

- 微信公众号：默认在已登录的微信电脑版中进入“搜一搜”，精确匹配公众号，点击“文章”，按日期范围选取文章，再复制 `mp.weixin.qq.com` 公开链接。`weixin download` 负责读取单篇正文，入队前继续校验正文作者。
- 知乎：回答详情、用户回答/文章列表、文章公开页读取。
- B站：用户搜索、UP 主视频列表、视频详情；字幕能力由 OpenCLI 提供，可在后续任务阶段接入。
- 小红书：作者笔记列表、带有效分享参数的单篇笔记详情。
- 抖音：作者作品列表、单条公开视频页面读取。
- 目前页面提供连接检查和单条链接试读；批量订阅仍应通过后续统一订阅/任务层进入 Obsidian。

所有调用保持低频、用户主动触发，并遵守目标平台规则。不会启用点赞、评论、发布或删除等写操作。

## 微信视觉发现边界

默认 `mode=wechat_ui` 使用本项目的 `WindowsWeChatVisionSession`。它通过本地 OCR 识别文字和日期，通过窗口相对位置点击没有文字的菜单按钮，并在每一步验证页面状态。它不使用 Codex Computer Use，也不会扫描聊天记录、Cookie、Token 或个人数据库。

日期标签 `今天`、`昨天`、`星期几`、`M月D日` 和 `YYYY年M月D日` 会先转换成北京时间的具体日期。打开文章后再读取正文完整发布日期。最终索引使用“公众号 + 具体发布日期 + 规范化链接”，同一天的多篇文章不会相互覆盖。

`pywechat127` 的 UI Automation 收藏流程只保留为旧版微信兼容实现。当前微信 4.1.12.26 的 UI Automation 树在本机不可见，所以默认流程不依赖它。微信升级导致文字或布局变化时，失败现场保存到 `D:\Codex\state\medical-knowledge-hub\diagnostics`，解析和知识管线无需跟着重写。
