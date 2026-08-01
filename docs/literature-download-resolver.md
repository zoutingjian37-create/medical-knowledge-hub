# 合法全文解析链执行方案

## 目标与边界

文献模块只完成“发现题录、寻找合法可用全文、保存 Zotero、等待提炼”四件事。它不替代 Zotero，不实现通用出版社爬虫，不读取学校账号、密码、Cookie 或 Token，也不绕过付费墙。

借鉴范围：

- Zotero Connector：复用用户浏览器中的正式登录和出版社识别能力。
- Paperscraper：借鉴小型解析器串联、失败后继续下一个来源、首个成功来源停止的结构。
- Europe PMC、Unpaywall、OpenAlex：通过官方公开接口获取开放全文位置。
- arXiv、bioRxiv、medRxiv：使用公开文章地址对应的官方 PDF 地址。

## 执行顺序

```text
RSS / Europe PMC / 文献查询
  → Crossref、OpenAlex 补全 DOI、作者和开放状态
  → 保留来源已经声明的 PDF
  → Europe PMC 按 DOI/PMID 精确补查
  → Unpaywall 按 DOI 查询最佳开放位置（配置邮箱后启用）
  → arXiv、bioRxiv、medRxiv 官方 PDF
  → 已确认开放的文章页面读取 citation_pdf_url
  → Zotero 保存题录与 PDF
```

解析器发生超时、无结果或格式错误时，只记录本次来源失败并继续下一个来源。找到候选 PDF 后由 Zotero 下载层验证；实际下载返回错误、非 PDF 内容或失效重定向时，会跳过该地址并从下一个来源继续。只有成功读到合法 PDF 后才停止，避免重复下载。

## 权限文献接力

```text
没有开放 PDF 或远端 PDF 返回 401/403
  → waiting_school_login
  → 打开正式出版社页面
  → 用户在浏览器完成学校登录
  → 用户点击官方 Zotero Connector
  → 软件按 DOI/PMID 检查 Zotero
  → 继续 Skill 提炼与 Obsidian 确认
```

401/403 在创建本地 Zotero 题录前转换为登录接力，避免软件自己创建的空题录被误认为用户已经完成 Connector 保存。

## 安全规则

- 所有期刊页面、重定向和 PDF 地址必须通过公网 URL 校验，拒绝环回、私网和云元数据地址。
- PDF 最大 50 MB，同时核验 HTTP Content-Type 或 `%PDF-` 文件头。
- Unpaywall 联系邮箱只从本机 `.env` 读取，不进入仓库。
- PDF 永久文件只由 Zotero 管理；项目状态目录只保留题录标识、运行记录和提炼预览。

## 暂不实现

- Elsevier、Wiley TDM 下载器：需要用户另行申请 API Key，现阶段没有必要增加密钥管理和界面复杂度。
- 任意出版社 HTML 抓取器：优先使用 Zotero Translators 和 Connector。
- Sci-Hub 或任何付费墙绕过通道。

## 验收标准

- 已有 PDF 不触发额外解析器。
- Europe PMC、Unpaywall、医学预印本和 `citation_pdf_url` 至少各有一个自动化测试。
- 单个来源失败后能够继续回退。
- 401/403 进入学校登录状态，且不会预先创建可误判的 Zotero 题录。
- 原有文献发现、Zotero、Skill 和 Obsidian 测试保持通过。
