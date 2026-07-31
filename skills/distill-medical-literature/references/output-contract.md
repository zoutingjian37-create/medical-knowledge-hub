# 输出契约

输出一份 Markdown 预览。Frontmatter 使用以下字段：

```yaml
---
source_url: "https://公开来源地址"
source_platform: wechat | journal | pubmed | europe_pmc | website | other
source_account: "作者、公众号或期刊"
source_title: "来源标题"
published_at: "YYYY-MM-DD 或未识别"
evidence_level: public_account_summary | abstract_verified | full_text_verified
status: preview
wiki_updates: []
---
```

正文严格使用以下标题：

```markdown
# 知识卡标题

## 核心结论
## 临床问题与 PICO/PECO
## 数据与变量
## 方法—问题映射
## 主要结论
## 统计方法创新
## 其他创新点
## 迁移方向
## 潜在选题
## 证据边界
## Wiki 更新建议
## 来源

状态：等待用户确认
```

规则：

- `source_url` 必须是永久公开来源，不能是临时缓存路径。
- 只有对照摘要或全文后，才能使用 `abstract_verified` 或 `full_text_verified`。
- “主要结论”以定性结果为主，只保留会改变判断的数字。
- “统计方法创新”必须标为“方法学原创”“方法应用创新”或“高级方法使用”。
- 没有创新时明确写“未识别到可主张的统计方法创新”，不要硬造。
- “潜在选题”只能标记为“灵感候选”或“待核查”，不得声称可直接立项。
- `wiki_updates` 只列相对 Vault 根目录的 Markdown 路径；默认只生成建议。
- 不保存原文，不把广告、课程、二维码或咨询信息写入任何章节。
- 最后一行必须是 `状态：等待用户确认`。
