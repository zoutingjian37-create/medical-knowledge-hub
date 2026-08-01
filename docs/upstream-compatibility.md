# 上游时效性与架构决策

最近核验：2026-08-01。

## 结论

| 组件 | 当前状态 | 在本项目中的位置 |
| --- | --- | --- |
| `jackwener/OpenCLI` | 活跃；本机与 npm 均为 1.8.6，仓库在 2026-07 仍有提交 | 单篇公众号链接解析，以及知乎、B站、小红书、抖音读取 |
| `Hello-Mr-Crab/pywechat` / `pywechat127` | 包可安装，但维护文档说明 UI 树只在少数账号和设备可见 | 借鉴代码驱动 RPA 的边界；旧版兼容后端 |
| 本项目微信视觉层 | 已在微信 4.1.12.26、Windows 4K 缩放环境真实复制公开链接 | 默认公众号名称与日期发现入口 |

OpenCLI 的单篇链接解析仍可用，但它的搜狗公众号搜索结果存在缺失和过时内容，不再作为默认公众号发现入口。pywechat 的原始 UI Automation 流程也不能直接作为当前微信 4.1 的默认入口。本项目只复用两者仍然可靠的边界，并自行维护视觉发现状态机。

## OpenCLI 核验

- 仓库：<https://github.com/jackwener/OpenCLI>
- 微信公开搜索加入记录：<https://github.com/jackwener/OpenCLI/commit/dbf1f6af>
- 更新记录：<https://github.com/jackwener/OpenCLI/blob/main/CHANGELOG.md>
- 临时验证页问题：<https://github.com/jackwener/OpenCLI/issues/2045>

`weixin search` 仍可作为诊断接口，但不能保证指定公众号的最新文章和完整日期范围。生产流程只把已经从微信复制出的真实 `mp.weixin.qq.com` URL 交给 `weixin download`。

## pywechat 核验

- 仓库：<https://github.com/Hello-Mr-Crab/pywechat>
- 公众号采集限制说明：<https://github.com/Hello-Mr-Crab/pywechat/issues/164>
- 不同电脑卡住的同类问题：<https://github.com/Hello-Mr-Crab/pywechat/issues/202>

当前包能读取 `HKCU\Software\Tencent\Weixin` 并识别本机微信 4.x，因此“只能找微信 3.9 注册表”不是当前事实。真正问题是 UI Automation 树会因账号、设备或升级而消失。上游最新说明也把“UI 树可见”列为前提。本机实测只能看到渲染子窗口，无法定位 `mmui::MainWindow`。

## 最终分层

```text
公众号名称
  → 已登录微信电脑版的本地视觉状态机
  → 精确公众号 → 文章页 → 日期归一化与筛选
  → 打开文章 → 正文日期复核 → 复制公开链接
  → OpenCLI weixin download
  → 校验正文作者
  → 过滤、去重、知识提炼、人工确认、Obsidian

旧版兼容：pywechat UI Automation 收藏流程
诊断接口：OpenCLI weixin search
人工排障：Computer Use
```

默认链路由本地 Python 代码驱动，不依赖 Codex 识别窗口。视觉层使用离线中文 OCR、文字锚点、窗口比例、有限重试和诊断截图。解析失败、作者不符、日期不符或页面状态未验证时都会明确失败。
