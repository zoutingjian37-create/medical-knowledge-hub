# 输出契约

```yaml
---
source_url: "https://mp.weixin.qq.com/s/..."
source_platform: wechat
source_account: "公众号名称"
source_title: "文章标题"
published_at: "YYYY-MM-DD 或未识别"
verification_level: public_account
status: preview
wiki_updates: []
---
```

Frontmatter 后直接放清洗后的原文 Markdown，保持原有顺序和正文图片；不要添加摘要、PICO、创新点或选题章节。末尾只追加：

```markdown
## 来源

[原文标题](公开链接)

状态：等待用户确认
```
