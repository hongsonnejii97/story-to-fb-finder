"""
Tìm kiếm Google qua API chính thức (không cào trang google.com).

Hỗ trợ 3 nhà cung cấp, chọn theo key có trong file .env:
  - Serper.dev        : SERPER_API_KEY            (kết quả giống google.com, có gói miễn phí)
  - SerpAPI           : SERPAPI_KEY
  - Google Custom Search JSON API : GOOGLE_CSE_KEY + GOOGLE_CSE_CX
"""
import os
import re
import urllib.parse
import requests
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


class SearchNotConfigured(Exception):
    pass


def _load_env():
    load_dotenv(ENV_PATH, override=True)


def get_provider() -> str | None:
    _load_env()
    if os.getenv("SERPER_API_KEY"):
        return "serper"
    if os.getenv("SERPAPI_KEY"):
        return "serpapi"
    if os.getenv("GOOGLE_CSE_KEY") and os.getenv("GOOGLE_CSE_CX"):
        return "google_cse"
    return None


def google_search(query: str, num: int = 10) -> list[dict]:
    """Trả về danh sách kết quả theo đúng thứ hạng Google: position, title, url, snippet."""
    provider = get_provider()
    if not provider:
        raise SearchNotConfigured("Chưa cấu hình API key tìm kiếm.")

    if provider == "serper":
        r = requests.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": os.getenv("SERPER_API_KEY"), "Content-Type": "application/json"},
            json={"q": query, "gl": "vn", "hl": "vi", "num": num},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("organic", [])
        return [
            {"position": it.get("position", i + 1), "title": it.get("title", ""),
             "url": it.get("link", ""), "snippet": it.get("snippet", "")}
            for i, it in enumerate(items)
        ]

    if provider == "serpapi":
        r = requests.get(
            "https://serpapi.com/search.json",
            params={"engine": "google", "q": query, "hl": "vi", "gl": "vn",
                    "google_domain": "google.com.vn", "num": num, "api_key": os.getenv("SERPAPI_KEY")},
            timeout=30,
        )
        r.raise_for_status()
        items = r.json().get("organic_results", [])
        return [
            {"position": it.get("position", i + 1), "title": it.get("title", ""),
             "url": it.get("link", ""), "snippet": it.get("snippet", "")}
            for i, it in enumerate(items)
        ]

    # google_cse
    r = requests.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": os.getenv("GOOGLE_CSE_KEY"), "cx": os.getenv("GOOGLE_CSE_CX"),
                "q": query, "hl": "vi", "gl": "vn", "num": min(num, 10)},
        timeout=20,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    return [
        {"position": i + 1, "title": it.get("title", ""),
         "url": it.get("link", ""), "snippet": it.get("snippet", "")}
        for i, it in enumerate(items)
    ]


def google_search_url(query: str) -> str:
    """Link mở Google trên trình duyệt (dùng cho chế độ thủ công)."""
    return "https://www.google.com/search?hl=vi&q=" + urllib.parse.quote(query)


def clean_facebook_url(url: str) -> str:
    """Chuẩn hoá link Facebook, bỏ tham số theo dõi (fbclid, __cft__...)."""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url.strip())
    qs = urllib.parse.parse_qs(parsed.query)
    keep = {k: qs[k][0] for k in ["story_fbid", "fbid", "id", "v", "set", "multi_permalinks"] if k in qs}
    netloc = (
        parsed.netloc.lower()
        .replace("m.facebook.com", "www.facebook.com")
        .replace("web.facebook.com", "www.facebook.com")
        .replace("mbasic.facebook.com", "www.facebook.com")
        .replace("touch.facebook.com", "www.facebook.com")
    )
    if netloc == "facebook.com":
        netloc = "www.facebook.com"
    path = re.sub(r"\.php/+$", ".php", parsed.path)
    if not keep:
        path = path.rstrip("/")
    return urllib.parse.urlunparse(("https", netloc, path, "", urllib.parse.urlencode(keep), ""))


def is_valid_facebook_post(url: str) -> bool:
    """Chỉ nhận link bài viết/ảnh/video/reel/group/page/cá nhân, bỏ trang đăng nhập, tìm kiếm, hashtag..."""
    if not url or ("facebook.com" not in url.lower() and "fb.watch" not in url.lower()):
        return False
    lower = url.lower()
    if "fb.watch/" in lower:
        return True
    if any(k in lower for k in ["/login", "/recover", "/hashtag/", "/search/", "/policies",
                                 "/help/", "/terms", "/privacy", "/reg/", "/events/", "/marketplace/"]):
        return False
    return any(p in lower for p in [
        "/posts/", "/permalink/", "/permalink.php", "/story.php",
        "/photos/", "/photo", "/videos/", "/watch", "/reel/", "/reels/",
        "/share/", "/p/", "/notes/", "story_fbid", "fbid=", "multi_permalinks=",
    ])
