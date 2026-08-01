# 输出契约

生成一份 Markdown 预览。Frontmatter 使用以下字段：

```yaml
---
source_url: "https://公开内容地址"
source_platform: wechat | zhihu | bilibili | xiaohongshu | douyin
source_account: "作者或账号名称"
source_title: "内容标题"
published_at: "YYYY-MM-DD 或未识别"
verification_level: public-account | public-source
status: preview
wiki_updates: []
---
```

正文严格使用以下标题：

```markdown
# 文章知识卡标题

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
```

规则：

- `source_url` 必须是原始公开地址。
- 微信专业公众号使用 `public-account`；其他公开平台内容使用 `public-source`。
- `status` 在用户确认前必须是 `preview`。
- `wiki_updates` 只列相对 Vault 根目录的 Markdown 路径。
- `wiki_updates` 不得指向 `微信公众号/`、`证据卡/` 或 `系统/`，也不得用单篇来源标题制造新页面。
- 潜在选题使用“灵感候选”或“待核查”，不得跳过证据核查直接标记为“可直接立项”。
- 没有满足页面创建门槛时，只建议更新现有页面或写入“待积累”。
- 最后一行必须是：`状态：等待用户确认`。
