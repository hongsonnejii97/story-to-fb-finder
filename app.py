import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from story_scraper import scrape_story
from google_searcher import (
    ENV_PATH, SearchNotConfigured, get_provider, google_search, google_search_url,
    clean_facebook_url, is_valid_facebook_post,
)
from facebook_extractor import extract_facebook_content
from matcher import snippet_match

# Điểm khớp tối thiểu giữa (tiêu đề + đoạn trích Google) và nội dung truyện.
# Đo thực tế: bài đúng 0.6 - 0.97, bài sai 0.03 - 0.15.
MATCH_THRESHOLD = 0.3

app = FastAPI(title="Facebook Story Matcher API")

# Cho phép gọi API khi mở index.html trực tiếp (origin "null") hoặc từ cổng khác
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    input: str


class ExtractRequest(BaseModel):
    fb_url: str
    story_text: Optional[str] = ""


class ConfigRequest(BaseModel):
    provider: str           # serper | serpapi | google_cse
    api_key: str
    cx: Optional[str] = ""  # chỉ dùng cho google_cse


@app.get("/", response_class=HTMLResponse)
async def get_index():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/config")
async def get_config():
    return {"provider": get_provider()}


@app.post("/api/config")
async def save_config(req: ConfigRequest):
    key = req.api_key.strip()
    if not key:
        raise HTTPException(400, "API key trống.")
    lines = {
        "serper": [f"SERPER_API_KEY={key}"],
        "serpapi": [f"SERPAPI_KEY={key}"],
        "google_cse": [f"GOOGLE_CSE_KEY={key}", f"GOOGLE_CSE_CX={(req.cx or '').strip()}"],
    }.get(req.provider)
    if not lines:
        raise HTTPException(400, "Nhà cung cấp không hợp lệ.")
    if req.provider == "google_cse" and not (req.cx or "").strip():
        raise HTTPException(400, "Google Custom Search cần thêm mã CX (Search engine ID).")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for k in ["SERPER_API_KEY", "SERPAPI_KEY", "GOOGLE_CSE_KEY", "GOOGLE_CSE_CX"]:
        os.environ.pop(k, None)
    return {"provider": get_provider()}


@app.post("/api/search")
def search_endpoint(req: SearchRequest):
    user_input = req.input.strip()
    if not user_input:
        raise HTTPException(400, "Vui lòng nhập link truyện hoặc tiêu đề.")

    # Dán thẳng link Facebook -> chỉ trích xuất nội dung
    if ("facebook.com" in user_input.lower() or "fb.watch" in user_input.lower()) and user_input.startswith("http"):
        fb = clean_facebook_url(user_input)
        ex = extract_facebook_content(fb)
        return {
            "story_title": "Bài viết Facebook nhập trực tiếp", "story_code": "", "intro_preview": "",
            "story_text": "", "query": "", "fb_link": fb, "fb_title": "", "rank": None,
            "match_score": None, "warning": "", "fb_content": ex["content"],
            "char_count": ex["char_count"], "word_count": ex["word_count"], "other_fb_links": [],
        }

    # 1. Phân tích truyện
    if user_input.startswith("http"):
        try:
            story = scrape_story(user_input)
        except Exception as e:
            raise HTTPException(400, f"Không đọc được trang truyện: {e}")
        story_title, story_code = story["clean_title"], story["story_code"]
        intro_preview, queries = story["intro_preview"], story["queries"]
        story_text = f"{story_title}\n{story['full_intro']}"
    else:
        story_title, story_code, intro_preview = user_input, "", ""
        queries = [user_input, f"site:facebook.com {user_input}"]
        story_text = user_input

    base = {
        "story_title": story_title, "story_code": story_code,
        "intro_preview": intro_preview, "story_text": story_text,
        "query": queries[0] if queries else "",
        "google_url": google_search_url(queries[0]) if queries else "",
    }

    # Chưa có API key -> chế độ thủ công
    if not get_provider():
        return {**base, "needs_config": True}

    # 2. Tìm Google theo thứ tự truy vấn; giữ nguyên thứ hạng Google,
    #    chọn bài Facebook xếp cao nhất mà nội dung khớp truyện
    candidates, seen, chosen, errors = [], set(), None, []
    for q in queries:
        try:
            results = google_search(q)
        except SearchNotConfigured:
            return {**base, "needs_config": True}
        except Exception as e:
            errors.append(str(e))
            continue
        for r in results:
            if not is_valid_facebook_post(r["url"]):
                continue
            url = clean_facebook_url(r["url"])
            if url in seen:
                continue
            seen.add(url)
            cand = {
                "url": url, "title": r["title"], "snippet": r["snippet"],
                "rank": r["position"], "query": q,
                "match": snippet_match(story_text, f"{r['title']} {r['snippet']}"),
            }
            candidates.append(cand)
            if chosen is None and cand["match"] >= MATCH_THRESHOLD:
                chosen = cand
        if chosen:
            break

    if not candidates:
        detail = "Google không trả về bài viết Facebook nào cho truyện này."
        if errors:
            detail += f" Lỗi API: {errors[0]}"
        raise HTTPException(404, detail)

    warning = ""
    if chosen is None:
        # Không bài nào vượt ngưỡng: lấy bài khớp nhất (hoà điểm thì lấy hạng cao hơn)
        chosen = max(candidates, key=lambda c: (c["match"], -c["rank"]))
        warning = ("Không có kết quả Facebook nào khớp rõ với nội dung truyện. "
                   "Đang hiển thị bài gần giống nhất, hãy kiểm tra lại.")

    # 3. Lấy nội dung bài viết
    try:
        ex = extract_facebook_content(chosen["url"], story_text)
    except Exception as e:
        ex = {"content": chosen["snippet"] or f"Không trích xuất được nội dung: {e}",
              "char_count": len(chosen["snippet"]), "word_count": len(chosen["snippet"].split())}

    others = [c for c in candidates if c["url"] != chosen["url"]]
    others.sort(key=lambda c: (c["match"] < MATCH_THRESHOLD, c["query"] != chosen["query"], c["rank"]))

    return {
        **base,
        "query": chosen["query"],
        "google_url": google_search_url(chosen["query"]),
        "fb_link": chosen["url"],
        "fb_title": chosen["title"],
        "rank": chosen["rank"],
        "match_score": chosen["match"],
        "warning": warning,
        "fb_content": ex["content"],
        "char_count": ex["char_count"],
        "word_count": ex["word_count"],
        "other_fb_links": others[:10],
    }


@app.post("/api/extract_content")
def extract_content_endpoint(req: ExtractRequest):
    url = clean_facebook_url(req.fb_url.strip())
    if not is_valid_facebook_post(url) and "facebook.com" not in url.lower() and "fb.watch" not in url.lower():
        raise HTTPException(400, "Link Facebook không hợp lệ.")
    ex = extract_facebook_content(url, req.story_text or "")
    ex["fb_link"] = url
    return ex


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8765, reload=True)
