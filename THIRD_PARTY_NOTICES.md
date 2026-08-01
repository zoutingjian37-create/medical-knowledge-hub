# Third-party notices

Medical Knowledge Hub 独立实现：

Copyright (C) 2026 zoutingjian37-create.

## OpenCLI

- Project: `jackwener/OpenCLI`
- Website: https://github.com/jackwener/opencli
- License: Apache License 2.0
- Usage: 作为独立安装的本地命令行运行时，读取已经复制的微信公开链接，以及知乎、B站、小红书和抖音公开内容
- Pinned runtime version: 1.8.6

OpenCLI 源代码不包含在本仓库中，其安装目录保留自己的许可证。

## pywechat / pyweixin

- Project: `Hello-Mr-Crab/pywechat`
- Website: https://github.com/Hello-Mr-Crab/pywechat
- License: GNU Lesser General Public License v2.1
- Usage: 提供代码驱动 Windows RPA 的架构参考，并作为 UI Automation 树仍可见的旧版微信兼容依赖；不属于默认采集链路
- Pinned package: `pywechat127==1.9.8`

该依赖作为独立 Python 包安装，其源代码不包含在本仓库核心代码中。默认视觉状态机没有复制其源代码。

## RapidOCR ONNX Runtime

- Project: `RapidAI/RapidOCR`
- Website: https://github.com/RapidAI/RapidOCR
- License: Apache License 2.0
- Usage: 在本机离线识别微信窗口中的公众号名称、文章标题、日期和菜单文字
- Pinned package: `rapidocr_onnxruntime==1.2.3`

OCR 模型和运行时作为独立 Python 包安装。截图仅用于当前本机运行和失败诊断，不上传远程服务，也不进入 Git。

## Upstream compatibility audit

上游兼容性最近核验于 2026-08-01：

- OpenCLI 仓库仍活跃，1.8.6 提供 `weixin download`。其公开搜索结果存在覆盖和时效限制，所以本项目只把它用于单篇公开链接解析。
- pywechat 包可以识别微信 4.x 安装路径，但当前账号和设备的 UI Automation 树不可见。默认流程改用本地 OCR 与状态验证，旧收藏流程只保留为兼容通道。
- 两个依赖均以独立运行时使用；本仓库没有复制、合并或改写其源代码。

核验依据见 [docs/upstream-compatibility.md](docs/upstream-compatibility.md)。

## 标准文献服务与 Zotero

本项目通过公开协议或官方本地接口调用以下服务，不复制其源代码，也不把用户凭据写入仓库：

- [Europe PMC REST API](https://dev.europepmc.org/RestfulWebService)：医学文献检索、PMID/PMCID、摘要和开放全文链接。
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)：DOI 与出版元数据补全。
- [OpenAlex API](https://docs.openalex.org/)：OpenAlex ID、开放获取状态和元数据补全。
- [Unpaywall API](https://unpaywall.org/products/api)：按 DOI 查找机构仓储或出版商提供的合法开放全文；只有配置联系邮箱后才调用。
- [Zotero Local API](https://www.zotero.org/support/dev/web_api/v3/local_api)：只读检查本地文库和全文索引。
- [Zotero Connector HTTP Server](https://www.zotero.org/support/dev/client_coding/connector_http_server)：使用官方 `saveItems` 创建题录，并用 `saveAttachment` 把开放 PDF 上传为 Zotero 管理的附件。
- RSS 2.0 / Atom：期刊和科研网站的标准增量订阅格式。
- arXiv、bioRxiv、medRxiv：仅根据其公开文章地址生成官方 PDF 地址，不绕过登录或付费墙。

全文回退链的适配器边界和“首个成功下载即停止”策略参考了 [jannisborn/paperscraper](https://github.com/jannisborn/paperscraper) 的公开设计。Paperscraper 采用 MIT License；本仓库没有捆绑该项目，也没有复制其下载器源文件，而是使用上述官方 API 独立实现最小适配器。

学校或出版社登录始终由用户在浏览器完成。本项目不接收或保存账号、密码、Cookie、Token。
