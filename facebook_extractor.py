import copy
import json
import os
import re
import shutil
import subprocess
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from matcher import similarity, snippet_match, extract_names


EXCLUDE_MARKERS = (
    ".comments.",
    ".top_level_comments.",
    ".comment_list_renderer.",
    ".comment_rendering_instance",
    ".timeline_list_feed_units.",
    ".group_feed.",
    ".news_feed.",
    ".lasso_blue_feed.",
    ".section_components.",
    ".reels_section.",
    ".related_videos",
    ".chaining",
    ".recent_posts",
    "permalink_cards",
    ".notice_message",
    ".feedback_strings.",
    ".ranges",
    ".delight_ranges",
    ".image_ranges",
    ".inline_style_ranges",
    ".aggregated_ranges",
    ".title_with_entities",
    ".contextual_message",
    ".privacy_scope",
    ".accessibility_caption",
)

MAIN_SUFFIXES = (
    ".comet_sections.content.story.comet_sections.message.story.message",
    ".comet_sections.content.story.comet_sections.message_container.story.message",
    ".comet_sections.content.story.message",
    ".result.data.creation_story.message",
    ".result.data.video.creation_story.message",
    ".result.data.video.savable_description",
    ".result.data.video.message",
    ".result.data.message",
    ".result.data.message_preferred_body",
    ".result.data.story.message",
    ".result.data.node.message",
    ".result.data.node.comet_sections.content.story.comet_sections.message.story.message",
    ".result.data.node_v2.comet_sections.content.story.comet_sections.message.story.message",
    ".media.creation_story.comet_sections.message.story.message",
    ".media.creation_story.message",
    ".creation_story.comet_sections.message.story.message",
    ".creation_story.message",
)

ATTACHED_MARKERS = (
    ".attached_story_layout.",
    ".attached_story.",
)


def find_browser_path() -> str | None:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    for name in ["chrome.exe", "msedge.exe", "chrome", "google-chrome"]:
        found = shutil.which(name)
        if found:
            return found
    return None


def _empty(msg: str) -> dict:
    return {"content": msg, "char_count": 0, "word_count": 0, "source": "none", "match_score": 0.0}


def _dedup_texts(texts: list[str]) -> list[str]:
    """Loại bỏ các đoạn trùng lặp hoặc nằm trọn trong đoạn dài hơn."""
    unique = []
    for t in sorted(set(texts), key=len, reverse=True):
        t_norm = re.sub(r"\s+", " ", t).strip()
        if not t_norm:
            continue
        if not any(t_norm in re.sub(r"\s+", " ", u) for u in unique):
            unique.append(t)
    # Giữ thứ tự xuất hiện ban đầu trong danh sách gốc
    order = {t: i for i, t in enumerate(texts)}
    unique.sort(key=lambda x: order.get(x, 999999))
    return unique


def extract_post_from_json_scripts(soup: BeautifulSoup, story_text: str = "") -> str:
    """
    Trích xuất toàn bộ nội dung bài đăng gốc (không bị cắt 'Xem thêm', giữ nguyên emoji và xuống dòng)
    từ dữ liệu Relay JSON (<script type="application/json">) của Facebook cho mọi loại link:
    Group, Reel, Page, Cá nhân (profile/permalink.php/story.php), Photo, Watch/Video, Share.
    """
    hoisted_main: list[str] = []
    hoisted_attached: list[str] = []
    main_candidates: list[str] = []
    attached_candidates: list[str] = []
    fallback_candidates: list[str] = []

    def walk(obj, path: str = ""):
        if isinstance(obj, dict):
            if "text" in obj and isinstance(obj["text"], str):
                val = obj["text"].strip()
                if val:
                    if any(m in path for m in EXCLUDE_MARKERS):
                        return
                    is_hoisted = "group_hoisted_feed.edges[" in path
                    if ".edges[" in path and not is_hoisted:
                        return
                    if any(am in path for am in ATTACHED_MARKERS) and path.endswith(".message"):
                        if is_hoisted:
                            hoisted_attached.append(val)
                        else:
                            attached_candidates.append(val)
                    elif path.endswith(MAIN_SUFFIXES):
                        if is_hoisted:
                            hoisted_main.append(val)
                        else:
                            main_candidates.append(val)
                    elif path.endswith((".message", ".savable_description")):
                        fallback_candidates.append(val)
            for k, v in obj.items():
                walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                walk(item, f"{path}[{idx}]")

    for sc in soup.find_all("script", attrs={"type": "application/json"}):
        raw = sc.string or sc.get_text()
        if not raw or '"text"' not in raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        walk(data)

    if hoisted_main or hoisted_attached:
        main_parts = _dedup_texts(hoisted_main)
        attached_parts = _dedup_texts(hoisted_attached)
    else:
        main_parts = _dedup_texts(main_candidates)
        attached_parts = _dedup_texts(attached_candidates)

    def pick_single(parts: list[str]) -> str:
        if not parts:
            return ""
        if len(parts) == 1:
            return parts[0]
        if story_text:
            names = extract_names(story_text)
            return max(parts, key=lambda t: (similarity(story_text, t, names)["score"], len(t)))
        return max(parts, key=len)

    best_main = pick_single(main_parts)
    best_attached = pick_single(attached_parts)

    combined = [p for p in (best_main, best_attached) if p]
    if len(combined) == 2:
        m_norm = re.sub(r"\s+", " ", combined[0]).strip()
        a_norm = re.sub(r"\s+", " ", combined[1]).strip()
        if m_norm in a_norm:
            combined = [combined[1]]
        elif a_norm in m_norm:
            combined = [combined[0]]

    if combined:
        return "\n\n".join(combined).strip()

    fallback_parts = _dedup_texts(fallback_candidates)
    if fallback_parts:
        return pick_single(fallback_parts).strip()

    return ""


def _extract_dom_text_with_emoji(el) -> str:
    """Chuyển thẻ <img alt='...'> (emoji Facebook) thành ký tự thực trước khi lấy text."""
    node = copy.copy(el)
    for img in node.find_all("img"):
        alt = img.get("alt") or ""
        img.replace_with(alt)
    return node.get_text(separator="\n", strip=True)


def _parse_html_candidates(html: str, story_text: str = "") -> tuple[str, str]:
    """
    Trả về (best_text, source) từ HTML của trang Facebook.
    Ưu tiên:
      1. Relay JSON (<script type="application/json">) - luôn chứa bản full không bị cắt 'Xem thêm'
      2. Khối DOM (div[dir="auto"], div[data-ad-preview="message"])
      3. Thẻ meta og:description / description
    """
    if not html:
        return "", "none"

    soup = BeautifulSoup(html, "html.parser")

    # 1. Trích xuất từ Relay JSON
    json_text = extract_post_from_json_scripts(soup, story_text)

    # 2. Trích xuất thẻ meta
    og = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
    meta_text = og["content"].strip() if og and og.get("content") else ""

    # 3. Trích xuất từ các khối DOM
    blocks = []
    for d in soup.find_all("div", dir="auto"):
        txt = _extract_dom_text_with_emoji(d)
        if len(txt) > 40:
            blocks.append(txt)
    for d in soup.find_all("div", attrs={"data-ad-preview": "message"}):
        txt = _extract_dom_text_with_emoji(d)
        if len(txt) > 40:
            blocks.append(txt)

    dom_best = ""
    if blocks:
        if story_text:
            names = extract_names(story_text)

            def score(t):
                return (similarity(story_text, t, names)["score"], len(t))

            dom_best = max(blocks, key=score)
            # Chỉ đối chiếu với meta_text nếu có khối khác khớp meta_text VÀ có độ dài tương đương
            if meta_text and dom_best and snippet_match(dom_best, meta_text[:200]) < 0.5:
                same_post = [
                    b for b in blocks
                    if snippet_match(b, meta_text[:200]) >= 0.5 and len(b) >= len(dom_best) * 0.6
                ]
                if same_post:
                    dom_best = max(same_post, key=len)
        else:
            dom_best = max(blocks, key=len)

    # Chọn kết quả đầy đủ nhất giữa JSON, DOM và Meta
    # Lưu ý: json_text từ Relay store luôn là nội dung gốc đầy đủ và sạch nhất (không dính lượt xem/cảm xúc như meta)
    if json_text:
        if dom_best and len(dom_best) > len(json_text) * 1.25:
            return dom_best, "dom"
        return json_text, "json"
    if dom_best and len(dom_best) >= len(meta_text):
        return dom_best, "dom"
    if meta_text:
        return meta_text, "meta"
    return "", "none"


def _fetch_html_cffi(fb_url: str) -> str:
    """Tải trực tiếp HTML Facebook bằng curl_cffi giả lập TLS Chrome (nhanh ~0.5-1s)."""
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    resp = cffi_requests.get(
        fb_url,
        impersonate="chrome120",
        headers=headers,
        allow_redirects=True,
        timeout=25,
    )
    return resp.text or ""


def _fetch_html_headless(fb_url: str) -> str:
    """Fallback mở bằng Chrome/Edge headless nếu request trực tiếp bị chặn."""
    browser = find_browser_path()
    if not browser:
        return ""
    proc = subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--virtual-time-budget=6000", "--dump-dom", fb_url],
        capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=90,
    )
    return proc.stdout or ""


def extract_facebook_content(fb_url: str, story_text: str = "") -> dict:
    """
    Trích xuất đầy đủ 100% nội dung bài đăng Facebook cho mọi định dạng link:
    Group, Reel, Page, Cá nhân (profile, permalink.php, story.php), Photo, Watch, Share.
    """
    best, source = "", "none"

    # Bước 1: Tải bằng curl_cffi (lấy trọn vẹn Relay JSON của bài viết mà không bị cắt 'Xem thêm')
    try:
        html = _fetch_html_cffi(fb_url)
        best, source = _parse_html_candidates(html, story_text)
    except Exception:
        best, source = "", "none"

    # Bước 2: Nếu chưa lấy được từ JSON (hoặc bài viết rỗng/chỉ có meta ngắn), thử thêm Chrome headless
    if source != "json" and (source != "dom" or len(best) < 80):
        try:
            html_dom = _fetch_html_headless(fb_url)
            best_dom, source_dom = _parse_html_candidates(html_dom, story_text)
            if len(best_dom) > len(best):
                best, source = best_dom, source_dom
        except Exception:
            pass

    if not best:
        return _empty("Không tải được nội dung (bài viết có thể ở nhóm kín, đã bị xoá hoặc cần đăng nhập).")

    best = re.sub(r"\n{3,}", "\n\n", best).strip()
    best_score = 0.0
    if story_text:
        names = extract_names(story_text)
        best_score = similarity(story_text, best, names)["score"]

    return {
        "content": best,
        "char_count": len(best),
        "word_count": len(best.split()),
        "source": source,
        "match_score": best_score,
    }
