# Third-party notices

Medical Knowledge Hub 独立实现：

Copyright (C) 2026 zoutingjian37-create.

## OpenCLI

- Project: `jackwener/OpenCLI`
- Website: https://github.com/jackwener/opencli
- License: Apache License 2.0
- Usage: 作为独立安装的本地命令行运行时，通过公开 CLI 接口搜索微信公开候选文章、解析搜索跳转，并读取五个平台的公开内容
- Pinned runtime version: 1.8.6

OpenCLI 源代码不包含在本仓库中，其安装目录保留自己的许可证。

## pywechat / pyweixin

- Project: `Hello-Mr-Crab/pywechat`
- Website: https://github.com/Hello-Mr-Crab/pywechat
- License: GNU Lesser General Public License v2.1
- Usage: 用户明确选择“微信界面补全”时启用的可选 Windows UI 依赖；不属于默认采集链路
- Pinned package: `pywechat127==1.9.8`

该依赖作为独立 Python 包安装，其源代码不包含在本仓库核心代码中。

## Upstream compatibility audit

上游兼容性最近核验于 2026-08-01：

- OpenCLI 仓库仍活跃，1.8.6 提供 `weixin search`、Browser Bridge 和 `weixin download`。本项目补齐其搜索结果从搜狗跳转到真实微信 URL 的编排，不复制 OpenCLI 抓取实现。
- pywechat 仓库与 `pywechat127` 包仍活跃并支持当前微信 4.x，但其维护者说明公众号列表几乎不暴露可用的 UI Automation 信息；现有方案必须逐篇收藏再取链接，因此只保留为慢速、尽力而为的备用通道。
- 两个依赖均以独立运行时使用；本仓库没有复制、合并或改写其源代码。

核验依据见 [docs/upstream-compatibility.md](docs/upstream-compatibility.md)。
