const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const apiClientPath = path.join(__dirname, "..", "static", "js", "api-client.js");
const appShellPath = path.join(__dirname, "..", "static", "js", "app-shell.js");

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

test("manual inbox queues any supported public link for knowledge distillation", () => {
    const html = fs.readFileSync(path.join(__dirname, "..", "static", "inbox.html"), "utf8");

    assert.match(html, /\/api\/ext\/platforms\/queue/);
    for (const platform of ["微信", "知乎", "B站", "小红书", "抖音"]) {
        assert.match(html, new RegExp(platform));
    }
    assert.match(html, /提取并生成预览/);
    assert.match(html, /\/compile/);
    assert.match(html, /\/review\.html/);
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
    assert.match(wechat, /<h1>公众号批量查找<\/h1>/);
});

test("review page exposes the complete review-gated workflow", () => {
    const html = fs.readFileSync(path.join(__dirname, "..", "static", "review.html"), "utf8");

    assert.match(html, /\/api\/ext\/knowledge\/jobs/);
    assert.match(html, /\/api\/ext\/platforms\/queue/);
    assert.match(html, /\/handoff/);
    assert.match(html, /\/compile/);
    assert.match(html, /\/import-preview/);
    assert.match(html, /\/approve/);
    assert.match(html, /\/reject/);
    assert.match(html, /确认保存/);
    assert.match(html, /自动提取重点/);
    assert.doesNotMatch(html, /cache_path|wechat_cookie|wechat_token/i);
});
