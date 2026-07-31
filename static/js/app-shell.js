(function (global) {
    "use strict";

    var navigation = [
        { label: "概览", path: "/admin.html" },
        { label: "公众号查找", path: "/wechat-collect.html" },
        { label: "粘贴链接", path: "/inbox.html" },
        { label: "查看与保存", path: "/review.html" },
        { label: "平台状态", path: "/platforms.html" },
    ];

    function render(pathname) {
        var currentPath = pathname === "/" ? "/admin.html" : pathname;
        var links = navigation.map(function (item) {
            var current = item.path === currentPath ? ' aria-current="page"' : "";
            return '<a href="' + item.path + '" class="app-shell__link"' + current + ">"
                + item.label + "</a>";
        }).join("");

        return '<div class="app-shell" data-app-shell>'
            + '<div class="app-shell__inner">'
            + '<a class="app-shell__brand" href="/admin.html">Medical Knowledge Hub</a>'
            + '<nav class="app-shell__nav" aria-label="主导航">' + links + "</nav>"
            + '<div class="app-shell__tools">'
            + '<span class="app-shell__status" data-app-shell-status>检查中</span>'
            + "</div></div></div>";
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
