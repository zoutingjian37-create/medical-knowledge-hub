# 多平台采集适配说明

## 外部采集运行时

微信、知乎、B站、小红书和抖音统一复用 `jackwener/OpenCLI` 作为本地采集引擎。本仓库只维护一层很薄的 Python 适配：

1. 调用 OpenCLI 的只读命令并要求 JSON 或 Markdown 输出；
2. 校验链接确实属于目标平台；
3. 转换为本项目现有的 `NormalizedContent`；
4. 后续继续使用同一套任务、清洗、附件和 Obsidian 写入流程。

没有复制 OpenCLI 的浏览器控制、登录、签名或下载实现，也没有为五个平台各建一套后台。

OpenCLI 使用 Apache-2.0 许可证，提供命令行和结构化输出。本仓库通过公开 CLI 接口调用它，不包含或修改其源代码。

## 安装与连接

运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install-platform-engines.ps1
```

默认安装到 `D:\Codex\tools\opencli-runtime`。然后在 Chrome、Edge 或其他 Chromium 浏览器安装 OpenCLI Browser Bridge，并在该浏览器正常登录所需平台。软件通过本机 `127.0.0.1:19825` 与连接器通信，不接收用户账号密码。

## 当前能力边界

- 微信公众号：名称查找默认调用 `weixin search`；搜索结果通过同一个 Browser Bridge 会话解析为带签名的 `mp.weixin.qq.com` 链接，再由 `weixin download` 读取。入队前校验正文作者与请求的公众号名称一致。公开搜索不是公众号完整历史，可能受搜狗收录和临时验证页影响。
- 知乎：回答详情、用户回答/文章列表、文章公开页读取。
- B站：用户搜索、UP 主视频列表、视频详情；字幕能力由 OpenCLI 提供，可在后续任务阶段接入。
- 小红书：作者笔记列表、带有效分享参数的单篇笔记详情。
- 抖音：作者作品列表、单条公开视频页面读取。
- 目前页面提供连接检查和单条链接试读；批量订阅仍应通过后续统一订阅/任务层进入 Obsidian。

所有调用保持低频、用户主动触发，并遵守目标平台规则。不会启用点赞、评论、发布或删除等写操作。

## 微信的备用边界

`pywechat127` 只在请求显式传入 `mode=wechat_ui` 时启动。它依赖微信 4.x 的当前窗口结构，并通过“文章列表 → 逐篇收藏 → 收藏页复制链接”完成发现，速度慢且容易受微信升级影响。默认 `mode=public` 不启动微信、不使用 Computer Use，也不会扫描聊天记录或个人数据库。

OpenCLI 搜索返回的是搜狗跳转链接。本项目只用 OpenCLI 自己的 Browser Bridge 打开该链接并读取最终地址；执行器直接调用 Node 入口且 `shell=False`，不会把包含 `&` 的 URL 拼进 `cmd.exe`。解析不到真实微信 URL 时整次发现明确失败，不会静默返回半截数据。
