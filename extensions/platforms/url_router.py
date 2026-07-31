"""Deterministic URL-to-platform routing for the shared manual inbox."""

from urllib.parse import urlsplit


_HOSTS = {
    "mp.weixin.qq.com": "wechat",
    "weixin.qq.com": "wechat",
    "zhihu.com": "zhihu",
    "www.zhihu.com": "zhihu",
    "zhuanlan.zhihu.com": "zhihu",
    "bilibili.com": "bilibili",
    "www.bilibili.com": "bilibili",
    "space.bilibili.com": "bilibili",
    "xiaohongshu.com": "xiaohongshu",
    "www.xiaohongshu.com": "xiaohongshu",
    "douyin.com": "douyin",
    "www.douyin.com": "douyin",
}


def detect_platform(url: str) -> str:
    """Return a registered platform key without opening or resolving the URL."""

    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("链接必须使用 http 或 https")
    platform = _HOSTS.get((parsed.hostname or "").lower())
    if not platform:
        raise ValueError("暂不支持该链接；目前支持微信、知乎、B站、小红书和抖音")
    return platform
