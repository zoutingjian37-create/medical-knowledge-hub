# 输出契约

输出一份 Markdown 讲解预览：

```yaml
---
source_url: "https://论文或可信数据库地址"
source_platform: journal | pubmed | europe_pmc | website | other
source_account: "作者或期刊"
source_title: "论文标题"
published_at: "YYYY-MM-DD 或未识别"
evidence_level: abstract_verified | full_text_verified
status: preview
wiki_updates: []
---
```

正文严格使用以下标题：

```markdown
# 讲解标题

## 为什么值得看
## 研究问题
## 研究怎么做
## 统计方法为什么这样选
## 主要发现
## 这篇研究的新意
## 对科研设计的启发
## 局限与证据边界
## 来源

状态：等待用户确认
```

规则：

- “主要发现”以结论和方向为主，只保留会改变解释的关键数字。
- “这篇研究的新意”区分方法学原创、方法应用创新、其他创新和没有可主张创新。
- 只有摘要时不得写成全文已核验，也不得补造摘要没有报告的细节。
- `wiki_updates` 只允许安全的 Vault 相对 Markdown 路径；默认保持空列表。
- 不包含广告、课程、二维码、联系方式或社群引导。
- 最后一行必须是 `状态：等待用户确认`。
