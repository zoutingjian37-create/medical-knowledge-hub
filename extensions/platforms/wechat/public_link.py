"""Validation shared by WeChat discovery and parsing boundaries."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_IDENTITY_QUERY_KEYS = ("__biz", "mid", "idx", "sn")
_SIGNED_QUERY_KEYS = ("src", "timestamp", "ver", "signature", "new")


def canonicalize_public_article_url(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("A public WeChat article URL must use HTTP or HTTPS")
    if host != "mp.weixin.qq.com" or not parsed.path.startswith("/s"):
        raise ValueError("This is not a public WeChat article URL")
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    identity = [
        (key, query[key]) for key in _IDENTITY_QUERY_KEYS if query.get(key)
    ]
    if parsed.path == "/s" and not identity:
        if not query.get("signature") or not query.get("timestamp"):
            raise ValueError("This public WeChat article URL has no article identity")
        identity = [
            (key, query[key]) for key in _SIGNED_QUERY_KEYS if query.get(key)
        ]
    return urlunsplit(
        ("https", "mp.weixin.qq.com", parsed.path, urlencode(identity), "")
    )
