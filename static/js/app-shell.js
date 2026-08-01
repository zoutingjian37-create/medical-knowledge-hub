(function (global) {
    "use strict";

    var navigation = [
        { label: "概览", path: "/admin.html" },
        { label: "粘贴链接", path: "/inbox.html" },
        { label: "公众号查找", path: "/wechat-collect.html" },
        { label: "公众号订阅", path: "/wechat-subscriptions.html" },
        { label: "文献订阅", path: "/literature-subscriptions.html" },
        { label: "查看与保存", path: "/review.html" },
        { label: "回收站", path: "/trash.html" },
        { label: "平台状态", path: "/platforms.html" },
    ];

    function render(pathname) {
        var currentPath = pathname === "/" ? "/admin.html" : pathname;
        var links = navigation.map(function (item) {
            var current = item.path === currentPath ? ' aria-current="page"' : "";
            return '<a href="' + item.path + '" class="app-shell__link"' + current + ">"
                + item.label + "</a>";
        }).join("");

        return '<aside class="app-shell" data-app-shell>'
            + '<div class="app-shell__inner">'
            + '<a class="app-shell__brand" href="/admin.html" aria-label="医学知识工作台首页">'
            + '<span class="app-shell__brand-mark" aria-hidden="true">MK</span>'
            + '<span class="app-shell__brand-copy"><strong>医学知识工作台</strong>'
            + '<small>Medical Knowledge Hub</small></span></a>'
            + '<nav class="app-shell__nav" aria-label="主导航">'
            + '<span class="app-shell__nav-label">工作区</span>' + links + "</nav>"
            + '<div class="app-shell__tools">'
            + '<span class="app-shell__status" data-app-shell-status>正在检查本地服务</span>'
            + '<a href="/api/docs">接口说明</a>'
            + "</div></div></aside>";
    }

    function mount() {
        if (!global.document.body || global.document.querySelector("[data-app-shell]")) return;
        var container = global.document.createElement("div");
        container.innerHTML = render(global.location.pathname);
        var shell = container.firstElementChild;
        global.document.body.prepend(shell);
        var status = shell.querySelector("[data-app-shell-status]");
        global.ContentHubAPI.get("/api/health").then(function () {
            status.textContent = "本地服务正常";
            status.classList.add("app-shell__status--ok");
        }).catch(function () {
            status.textContent = "本地服务异常";
            status.classList.add("app-shell__status--error");
        });
    }

    global.ContentHubShell = { render: render, mount: mount };
    if (global.document.readyState === "loading") {
        global.document.addEventListener("DOMContentLoaded", mount);
    } else {
        mount();
    }
}(window));
