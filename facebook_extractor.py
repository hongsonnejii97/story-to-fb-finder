import os
import re
import shutil
import subprocess
from bs4 import BeautifulSoup
from matcher import similarity, snippet_match, extract_names


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


def extract_facebook_content(fb_url: str, story_text: str = "") -> dict:
    """
    Mở bài viết Facebook công khai bằng Chrome headless (như khách chưa đăng nhập)
    và lấy phần nội dung khớp nhất với truyện.
    """
    browser = find_browser_path()
    if not browser:
        raise RuntimeError("Không tìm thấy trình duyệt Chrome/Edge trên máy.")

    proc = subprocess.run(
        [browser, "--headless=new", "--disable-gpu", "--virtual-time-budget=6000", "--dump-dom", fb_url],
        capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=90,
    )
    soup = BeautifulSoup(proc.stdout, "html.parser")

    og = soup.find("meta", property="og:description") or soup.find("meta", attrs={"name": "description"})
    meta_text = og["content"].strip() if og and og.get("content") else ""

    blocks = []
    for d in soup.find_all("div", dir="auto"):
        txt = d.get_text(separator="\n", strip=True)
        if len(txt) > 80:
            blocks.append(txt)
    for d in soup.find_all("div", attrs={"data-ad-preview": "message"}):
        txt = d.get_text(separator="\n", strip=True)
        if len(txt) > 50:
            blocks.append(txt)

    if not blocks and not meta_text:
        return _empty("Không tải được nội dung (bài viết có thể ở nhóm kín, đã bị xoá hoặc cần đăng nhập).")

    if story_text:
        names = extract_names(story_text)

        def score(t):  # ưu tiên khối khớp truyện nhất, hoà điểm thì lấy khối dài hơn
            return (similarity(story_text, t, names)["score"], len(t))

        best = max(blocks, key=score) if blocks else ""
        best_score = similarity(story_text, best, names)["score"] if best else 0.0
        # Đoạn mô tả og:description là phần đầu của chính bài viết -> dùng để đối chiếu.
        # Nếu khối chọn được không chứa phần mở đầu của bài thì đó là bài khác trên trang.
        if meta_text and best and snippet_match(best, meta_text[:200]) < 0.5:
            same_post = [b for b in blocks if snippet_match(b, meta_text[:200]) >= 0.5]
            best = max(same_post, key=len) if same_post else meta_text
            best_score = similarity(story_text, best, names)["score"]
    else:
        best = max(blocks, key=len) if blocks else meta_text
        best_score = 0.0

    if not best or len(best) < len(meta_text):
        best, source = meta_text, "meta"
    else:
        source = "dom"

    best = re.sub(r"\n{3,}", "\n\n", best).strip()
    return {
        "content": best,
        "char_count": len(best),
        "word_count": len(best.split()),
        "source": source,
        "match_score": best_score,
    }
