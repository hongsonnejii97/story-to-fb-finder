import re
import urllib.parse
from bs4 import BeautifulSoup
import requests

def clean_story_title(raw_title: str, url: str = "") -> tuple[str, str]:
    """
    Cleans raw story title and extracts story code (e.g., #TTTY 3516).
    """
    code = ""
    # Look for code patterns like #TTTY 3516, TTTY-3516, #TTN 1066, etc.
    code_match = re.search(r'(#?[A-Za-z]{2,6}[\s\-]*\d+)', raw_title)
    if code_match:
        code = code_match.group(1).strip()
    
    t = raw_title
    if code:
        t = t.replace(code, "")
        
    # Split by common title separators (en-dash, em-dash, hyphen, pipe, colon)
    parts = re.split(r'[\u2013\u2014\-\|:]', t)
    valid_parts = []
    for p in parts:
        p_strip = p.strip()
        # Filter out site names / branding
        if len(p_strip) > 5 and not any(b in p_strip.lower() for b in [
            "truyện hay", "đọc truyện", "giang sơn", "mỗi ngày", "truyenfull", 
            "truyen", "saytruyen", "santruyen", "wattpad", "tangthuvien"
        ]):
            valid_parts.append(p_strip)
            
    if valid_parts:
        clean_title = max(valid_parts, key=len)
    else:
        clean_title = re.sub(r'^[#\s\d\-–—|:]+', '', t).strip()
        if not clean_title and url:
            slug = [s for s in url.strip("/").split("/") if s][-1]
            clean_title = slug.replace("-", " ").title()

    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
    return clean_title, code

def scrape_story(story_url: str) -> dict:
    """
    Scrapes story URL, extracts clean title, code, intro preview, and generates Google queries.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    resp = requests.get(story_url.strip(), headers=headers, timeout=15)
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    
    # 1. Title extraction
    raw_title = ""
    h1 = soup.find("h1")
    if h1 and len(h1.get_text(strip=True)) > 5:
        raw_title = h1.get_text(strip=True)
    elif soup.title and soup.title.string:
        raw_title = soup.title.string.strip()
    
    clean_title, story_code = clean_story_title(raw_title, story_url)
    
    # 2. Intro / content extraction
    intro_text = ""
    # Specific containers for common novel sites
    containers = [
        soup.find(id="text-box"),
        soup.find(class_="summary-content"),
        soup.find(class_="story-intro"),
        soup.find(class_="desc-text"),
        soup.find(class_="story-detail-content"),
        soup.find(id="story-intro"),
    ]
    for c in containers:
        if c:
            text = c.get_text(separator="\n", strip=True)
            if len(text) > 80:
                intro_text = text
                break
    
    # Fallback to meta descriptions
    if not intro_text:
        meta_desc = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
        if meta_desc and meta_desc.get("content"):
            intro_text = meta_desc["content"].strip()
            
    # Fallback to general paragraph collection
    if not intro_text:
        paras = []
        for p in soup.find_all("p"):
            t = p.get_text(strip=True)
            if len(t) > 60:
                paras.append(t)
        intro_text = "\n\n".join(paras[:10])

    # 3. Câu mở đầu truyện: giữ nguyên ký tự gốc (kể cả "h//ôn") giống cách người dùng copy lên Google
    paragraphs = [p.strip() for p in intro_text.split("\n") if len(p.strip()) > 20]
    first_para = paragraphs[0] if paragraphs else ""
    first_sentence = ""
    if first_para:
        dot_split = re.split(r"[.!?]", first_para)
        if len(dot_split[0].strip()) >= 20:
            first_sentence = dot_split[0].strip()
        else:
            first_sentence = first_para[:80].strip()

    # Gửi nguyên đoạn mở đầu giống thao tác copy-paste lên Google (Google tự bỏ phần sau 32 từ)
    opening_query = first_para[:400].strip()

    # 4. Danh sách truy vấn, theo thứ tự ưu tiên
    queries = []
    if opening_query:
        queries.append(opening_query)                                # giống hệt cách tìm thủ công
    if clean_title:
        queries.append(f"{clean_title} facebook")
    if opening_query:
        queries.append(f"site:facebook.com {opening_query}")
    if clean_title:
        queries.append(f'site:facebook.com "{clean_title}"')
        
    return {
        "url": story_url,
        "raw_title": raw_title,
        "clean_title": clean_title,
        "story_code": story_code,
        "first_sentence": first_sentence,
        "opening_query": opening_query,
        "intro_preview": intro_text[:600] + ("..." if len(intro_text) > 600 else ""),
        "full_intro": intro_text,
        "queries": queries
    }
