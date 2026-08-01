# 上游时效性与架构决策

最近核验：2026-08-01。

## 结论

| 组件 | 当前状态 | 在本项目中的位置 |
| --- | --- | --- |
| `jackwener/OpenCLI` | 活跃；本机与 npm 均为 1.8.6，仓库在 2026-07 仍有提交 | 默认公开搜索、Browser Bridge 跳转解析、正文或字幕读取 |
| `Hello-Mr-Crab/pywechat` / `pywechat127` | 活跃；本机包为 1.9.8，可识别微信 4.1.12.26 | 仅作为显式选择的微信 UI 慢速备用 |

两个项目没有整体失效。失去工程可靠性的是把 pywechat 的公众号 UI 收藏流程作为默认入口：它依赖窗口结构、固定交互和逐篇收藏，慢且容易随微信升级变化。

## OpenCLI 核验

- 仓库：<https://github.com/jackwener/OpenCLI>
- 微信公开搜索加入记录：<https://github.com/jackwener/OpenCLI/commit/dbf1f6af>
- 更新记录：<https://github.com/jackwener/OpenCLI/blob/main/CHANGELOG.md>
- 临时验证页问题：<https://github.com/jackwener/OpenCLI/issues/2045>

`weixin search` 能快速返回公开候选文章，但上游提交明确留下了“搜狗跳转 URL 还需解析成真实 `mp.weixin.qq.com` URL”的边界。本项目复用 OpenCLI Browser Bridge 补齐这段编排，再把真实 URL 交回 `weixin download`。遇到上游已知的临时验证页时只等待并重试一次，避免无限重试和频繁访问。

## pywechat 核验

- 仓库：<https://github.com/Hello-Mr-Crab/pywechat>
- 公众号采集限制说明：<https://github.com/Hello-Mr-Crab/pywechat/issues/164>
- 不同电脑卡住的同类问题：<https://github.com/Hello-Mr-Crab/pywechat/issues/202>

当前包能读取 `HKCU\Software\Tencent\Weixin` 并识别本机微信 4.x，因此“只能找微信 3.9 注册表”不是当前事实。真正问题是公众号页面几乎没有稳定的 UI Automation 语义；维护者给出的可行办法仍是逐篇收藏后从收藏页取链接，且明确不能保证所有机器和布局都正常。

## 最终分层

```text
公众号名称
  → OpenCLI weixin search
  → OpenCLI Browser Bridge 解析搜狗跳转
  → 校验为真实、带签名的 mp.weixin.qq.com URL
  → OpenCLI weixin download
  → 校验正文作者
  → 过滤、去重、知识提炼、人工确认、Obsidian

显式慢速备用：pywechat UI 收藏流程
人工排障：Computer Use
```

这条默认链路不启动桌面微信，也不依赖 Codex 识别窗口坐标。公开搜索不保证覆盖公众号完整历史，所以界面使用“候选文章”表述；解析失败、作者不符或验证未通过时明确失败。
