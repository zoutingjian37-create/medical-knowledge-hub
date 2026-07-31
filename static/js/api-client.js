(function (global) {
    "use strict";

    async function request(path, options) {
        var init = Object.assign({}, options || {});
        init.headers = Object.assign({ Accept: "application/json" }, init.headers || {});

        if (init.body !== undefined && init.body !== null && typeof init.body !== "string") {
            init.body = JSON.stringify(init.body);
            init.headers["Content-Type"] = "application/json";
        }

        var response = await global.fetch(path, init);
        var contentType = response.headers.get("content-type") || "";
        var payload = contentType.indexOf("application/json") >= 0
            ? await response.json()
            : await response.text();

        if (!response.ok) {
            var message = payload && (payload.detail || payload.message || payload.error);
            throw new Error(message || "请求失败（HTTP " + response.status + "）");
        }

        return payload;
    }

    global.ContentHubAPI = {
        request: request,
        get: function (path) { return request(path); },
        post: function (path, body) { return request(path, { method: "POST", body: body }); },
        put: function (path, body) { return request(path, { method: "PUT", body: body }); },
        patch: function (path, body) { return request(path, { method: "PATCH", body: body }); },
        delete: function (path) { return request(path, { method: "DELETE" }); },
    };
}(window));
