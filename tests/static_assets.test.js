const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const apiClientPath = path.join(__dirname, "..", "static", "js", "api-client.js");
const appShellPath = path.join(__dirname, "..", "static", "js", "app-shell.js");
const appCssPath = path.join(__dirname, "..", "static", "css", "app.css");

function loadApiClient(fetchImplementation) {
    global.window = global;
    global.fetch = fetchImplementation;
    delete require.cache[require.resolve(apiClientPath)];
    require(apiClientPath);
    return global.ContentHubAPI;
}

test("API client serializes JSON bodies", async () => {
    let request;
    const api = loadApiClient(async (url, options) => {
        request = { url, options };
        return {
            ok: true,
            headers: { get: () => "application/json" },
            json: async () => ({ accepted: true }),
        };
    });
    const result = await api.post("/api/example", { title: "hello" });
    assert.deepEqual(result, { accepted: true });
    assert.equal(request.options.body, JSON.stringify({ title: "hello" }));
});

test("app shell uses short action-oriented module names", () => {
    global.window = global;
    global.document = { readyState: "loading", addEventListener() {} };
    delete require.cache[require.resolve(appShellPath)];
    require(appShellPath);

    const html = global.ContentHubShell.render("/inbox.html");

    for (const label of ["公众号查找", "粘贴链接", "查看与保存", "平台状态"]) {
        assert.match(html, new RegExp(label));
    }
    assert.match(html, /href="\/inbox\.html"[^>]*aria-current="page"/);
    assert.doesNotMatch(html, /login\.html|rss\.html|blacklist\.html/);
});

test("shared stylesheet renders an operational responsive workspace", () => {
    const css = fs.readFileSync(appCssPath, "utf8");

    for (const selector of [
        "body",
        ".page-shell",
        ".workspace-header",
        ".workspace-grid",
        ".action-list",
        ".action-row",
        ".action-row:hover",
        ".workflow-list",
        ".page-footer",
    ]) {
        assert.match(css, new RegExp(selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{"));
    }
    assert.match(css, /@media\s*\(max-width:\s*680px\)/);
    assert.match(css, /prefers-reduced-motion/);
});

test("dashboard follows the real collect-review-archive task path", () => {
    const html = fs.readFileSync(path.join(__dirname, "..", "static", "admin.html"), "utf8");

    assert.match(html, /class="workspace-header"/);
    assert.match(html, /class="action-list"/);
    assert.match(html, /class="workflow-list"/);
    assert.match(html, /粘贴新链接/);
    assert.match(html, /采集.*提炼.*确认.*Obsidian/s);
    assert.doesNotMatch(html, /card-grid|card__number|START HERE/);
});

test("application shell uses a persistent desktop navigation rail", () => {
    global.window = global;
    global.document = { readyState: "loading", addEventListener() {} };
    delete require.cache[require.resolve(appShellPath)];
    require(appShellPath);

    const html = global.ContentHubShell.render("/admin.html");
    assert.match(html, /^<aside class="app-shell"/);
    assert.match(html, /app-shell__nav-label/);
    assert.match(html, /app-shell__brand-copy/);
});

test("manual inbox queues any supported public link for knowledge distillation", () => {
    const html = fs.readFileSync(path.join(__dirname, "..", "static", "inbox.html"), "utf8");

    assert.match(html, /\/api\/ext\/platforms\/queue/);
    for (const platform of ["微信", "知乎", "B站", "小红书", "抖音"]) {
        assert.match(html, new RegExp(platform));
    }
    assert.match(html, /提取并生成预览/);
    assert.match(html, /\/compile/);
    assert.match(html, /\/review\.html/);
    assert.match(html, /response\.reason === "advertisement"/);
    assert.match(html, /已过滤推广内容/);
    assert.match(html, /response\.reason === "duplicate"/);
    assert.match(html, /已处理过这篇内容/);
    assert.doesNotMatch(html, /下载 \.md|复制 Markdown/);
    assert.doesNotMatch(html, /\/api\/login|searchbiz|appmsgpublish/);
    assert.doesNotMatch(html, /name=["'](?:cookie|token)|Authorization|Bearer/i);
});

test("platform page includes WeChat link parsing and OpenCLI", () => {
    const html = fs.readFileSync(path.join(__dirname, "..", "static", "platforms.html"), "utf8");
    assert.match(html, /微信公众号/);
    assert.match(html, /OpenCLI/);
    assert.match(html, /\/api\/ext\/platforms/);
});

test("dashboard descriptions say what each module does in plain language", () => {
    const html = fs.readFileSync(path.join(__dirname, "..", "static", "admin.html"), "utf8");
    for (const text of [
        "粘贴文章或视频链接，自动提取重点",
        "按公众号名称查找公开文章，并加入待处理列表",
        "支持微信、知乎、B站、小红书和抖音，自动识别并提取内容",
        "查看提取结果；确认后保存到 Obsidian",
        "检查各平台现在能不能正常读取内容",
        "查看本地接口，供开发和排错使用",
    ]) {
        assert.match(html, new RegExp(text));
    }
    assert.match(html, /href="\/inbox\.html"/);
    assert.doesNotMatch(html, /编译为|解析连接|知识提炼流程|固定 Codex Skill/);
});

test("secondary pages use concise descriptions", () => {
    const inbox = fs.readFileSync(path.join(__dirname, "..", "static", "inbox.html"), "utf8");
    const review = fs.readFileSync(path.join(__dirname, "..", "static", "review.html"), "utf8");
    const platforms = fs.readFileSync(path.join(__dirname, "..", "static", "platforms.html"), "utf8");
    const wechat = fs.readFileSync(path.join(__dirname, "..", "static", "wechat-collect.html"), "utf8");

    assert.match(inbox, /<h1>粘贴链接<\/h1>/);
    assert.match(review, /<h1>查看与保存<\/h1>/);
    assert.match(platforms, /<h1>平台状态<\/h1>/);
    assert.match(wechat, /<h1>公众号文章<\/h1>/);
    assert.match(wechat, /发布日期/);
    assert.match(wechat, /aria-label="开始日期"/);
    assert.match(wechat, /aria-label="结束日期"/);
    assert.doesNotMatch(wechat, /星期几.*(?:转换|解释)/s);
    assert.doesNotMatch(wechat, /最近\s*1-6\s*天/);
    assert.doesNotMatch(wechat, /mode: "wechat_ui"/);
    assert.match(wechat, /无需打开浏览器或连接 OpenCLI 扩展/);
    assert.match(wechat, /Asia\/Shanghai/);
    assert.match(wechat, /id="wechatIssueDialog"/);
    assert.match(wechat, /failed_step/);
    assert.match(wechat, /retry_from/);
    assert.match(wechat, /showModal/);
    assert.match(wechat, /复制公开链接/);
});

test("wechat and literature subscriptions are separate operational modules", () => {
    const wechat = fs.readFileSync(path.join(__dirname, "..", "static", "wechat-subscriptions.html"), "utf8");
    const literature = fs.readFileSync(path.join(__dirname, "..", "static", "literature-subscriptions.html"), "utf8");
    const legacy = fs.readFileSync(path.join(__dirname, "..", "static", "subscriptions.html"), "utf8");
    const shell = fs.readFileSync(path.join(__dirname, "..", "static", "js", "app-shell.js"), "utf8");

    assert.match(wechat, /<h1>公众号订阅<\/h1>/);
    assert.match(wechat, /id="wechatAccounts"/);
    assert.match(wechat, /每行一个公众号/);
    assert.match(wechat, /id="editWechatAccounts"[^>]*>修改</);
    assert.match(wechat, /id="saveWechatAccounts"[^>]*>保存</);
    assert.match(wechat, /id="wechatDailyLimit"/);
    assert.match(wechat, /每个公众号文章上限/);
    assert.match(wechat, /\/api\/ext\/subscriptions\/wechat-accounts/);
    assert.match(wechat, /daily_limit:\s*Number\(wechatDailyLimit\.value/);
    assert.match(wechat, /id="wechatRunIssue"/);
    assert.match(wechat, /从检查点继续/);
    assert.match(wechat, /subscription_id:\s*run\.subscription_id/);
    assert.match(wechat, /wechatRunIssue\.showModal\(\)/);
    assert.match(wechat, /id="selectAllWechatRuns"/);
    assert.match(wechat, /id="wechatRunFilter"/);
    assert.match(wechat, /id="retrySelectedWechatRuns"[^>]*disabled/);
    assert.match(wechat, /id="deleteSelectedWechatRuns"[^>]*disabled/);
    assert.match(wechat, /id="showMoreWechatRuns"/);
    assert.match(wechat, /\/api\/ext\/literature\/runs\/retry-selected/);
    assert.match(wechat, /api\.delete\("\/api\/ext\/literature\/runs"/);
    assert.match(wechat, /已完成记录自动保留 14 天/);
    assert.match(wechat, /scope:\s*['"]wechat['"]/);
    assert.doesNotMatch(wechat, /Zotero|导出个人配置|导入个人配置|RSS \/ Atom/);

    assert.match(literature, /<h1>文献订阅<\/h1>/);
    assert.match(literature, /RSS \/ Atom/);
    assert.match(literature, /PubMed \/ Europe PMC/);
    assert.match(literature, /Zotero/);
    assert.match(literature, /登录学校或出版社账号/);
    assert.match(literature, /已用 Zotero Connector 保存 PDF/);
    assert.match(literature, /尚未检测到 Zotero PDF/);
    assert.match(literature, /scope:\s*['"]literature['"]/);
    assert.doesNotMatch(literature, /微信公众号|公众号名称|value=["']wechat_account["']/);

    assert.match(legacy, /wechat-subscriptions\.html/);
    assert.match(shell, /公众号订阅/);
    assert.match(shell, /文献订阅/);
    assert.doesNotMatch(shell, /订阅中心/);
    const client = fs.readFileSync(path.join(__dirname, "..", "static", "js", "api-client.js"), "utf8");
    assert.match(client, /delete:\s*function\s*\(path, body\)/);
});

test("literature subscription form resolves its own fields instead of browser globals", () => {
    const literature = fs.readFileSync(
        path.join(__dirname, "..", "static", "literature-subscriptions.html"),
        "utf8",
    );

    for (const field of [
        "literatureForm",
        "kind",
        "name",
        "source",
        "query",
        "keywords",
        "requirement",
        "dailyLimit",
        "collection",
        "formStatus",
    ]) {
        assert.match(
            literature,
            new RegExp(
                `const \\w+ = document\\.getElementById\\("${field}"\\);`,
            ),
        );
    }
});

test("review page exposes the complete review-gated workflow", () => {
    const html = fs.readFileSync(path.join(__dirname, "..", "static", "review.html"), "utf8");
    const trash = fs.readFileSync(path.join(__dirname, "..", "static", "trash.html"), "utf8");
    const inbox = fs.readFileSync(path.join(__dirname, "..", "static", "inbox.html"), "utf8");
    const wechatCollect = fs.readFileSync(path.join(__dirname, "..", "static", "wechat-collect.html"), "utf8");

    assert.match(html, /\/api\/ext\/knowledge\/jobs/);
    assert.match(html, /\/api\/ext\/platforms\/queue/);
    assert.match(html, /\/handoff/);
    assert.match(html, /\/compile/);
    assert.match(html, /\/import-preview/);
    assert.match(html, /\/approve/);
    assert.match(html, /href="\/trash\.html"/);
    assert.doesNotMatch(html, /trashMode|trashSettings|showTrash/);
    assert.match(html, /id="selectAllJobs"/);
    assert.match(html, /id="previewSelected"[^>]*disabled/);
    assert.match(html, /id="recleanSelected"[^>]*disabled/);
    assert.match(html, /id="saveSelected"[^>]*disabled/);
    assert.match(html, /id="deleteSelected"[^>]*disabled/);
    assert.match(html, /\/api\/ext\/knowledge\/jobs\/approve-selected/);
    assert.match(html, /\/api\/ext\/knowledge\/jobs\/trash-selected/);
    assert.match(html, /\/api\/ext\/knowledge\/jobs\/reclean-selected/);
    assert.match(html, /id="previewContent"[^>]*class="dialog-body preview-content"/);
    assert.doesNotMatch(html, /<pre id="previewText"/);
    assert.match(html, /document\.createElement\("img"\)/);
    assert.match(html, /url\.protocol === "http:" \|\| url\.protocol === "https:"/);
    assert.doesNotMatch(html, /previewContent\.innerHTML\s*=/);
    assert.match(trash, /<h1>回收站<\/h1>/);
    assert.match(trash, /恢复所选/);
    assert.match(trash, /彻底清理所选/);
    assert.match(trash, /id="retentionDays"[^>]*min="1"[^>]*max="30"[^>]*value="7"/);
    assert.match(trash, /\/api\/ext\/knowledge\/trash\/settings/);
    assert.match(trash, /\/api\/ext\/knowledge\/trash\/purge/);
    assert.match(trash, /id="selectAllTrash"/);
    assert.match(trash, /id="clearSelected"[^>]*disabled/);
    assert.match(trash, /id="restoreSelected"[^>]*disabled/);
    assert.match(trash, /\/api\/ext\/knowledge\/trash\/delete-selected/);
    assert.match(trash, /\/api\/ext\/knowledge\/trash\/restore-selected/);
    assert.doesNotMatch(trash, /onclick="(?:restoreJob|deleteJob)/);
    assert.match(html, /文献自动讲解：开启/);
    assert.match(html, /\/api\/ext\/knowledge\/settings/);
    assert.match(inbox, /\/api\/ext\/knowledge\/settings/);
    assert.doesNotMatch(wechatCollect, /\/api\/ext\/knowledge\/settings/);
    assert.doesNotMatch(wechatCollect, /\/compile/);
    assert.match(wechatCollect, /自动重试/);
    assert.match(wechatCollect, /data\.complete === false/);
    assert.match(wechatCollect, /item\.title \|\| item\.account \|\| item\.source_url/);
    assert.match(wechatCollect, /item\.failed_step/);
    assert.match(html, /id="savePreview"/);
    assert.match(html, /确认保存到 Obsidian/);
    assert.match(html, /savePreview\.addEventListener/);
    assert.match(html, /确认保存/);
    assert.match(html, /生成文献讲解/);
    assert.doesNotMatch(html, /cache_path|wechat_cookie|wechat_token/i);
});
