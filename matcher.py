"""
So khớp nội dung giữa truyện gốc và bài đăng Facebook.

Bài đăng Facebook thường "che chữ" (vd: "b/ ệ/ n/ h", "m//ổ") và viết lại câu chữ,
nên ta chuẩn hoá văn bản rồi so khớp theo cụm từ (n-gram) + tên nhân vật.
"""
import re
import unicodedata

def normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFC", text).lower()
    # Bỏ ký tự che chữ: "b/ ệ/ n/ h" -> "bệnh", "m//ổ" -> "mổ"
    t = re.sub(r"/+\s?", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()

def _shingles(text: str, n: int) -> set:
    words = normalize(text).split()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}

def extract_names(text: str) -> list[str]:
    """Tên nhân vật: cụm 2-3 từ viết hoa xuất hiện giữa câu (không đứng đầu câu)."""
    t = unicodedata.normalize("NFC", text or "")
    t = re.sub(r"/+\s?", "", t)
    upper = "A-ZÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬĐÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴ"
    pattern = rf"(?<![.!?\n“\"]\s)(?<!^)\b([{upper}]\w+(?:\s+[{upper}]\w+){{1,2}})"
    counts = {}
    for m in re.finditer(pattern, t, flags=re.M):
        name = m.group(1)
        counts[name] = counts.get(name, 0) + 1
    # Tên thật thường lặp lại nhiều lần
    return [n for n, c in sorted(counts.items(), key=lambda x: -x[1]) if c >= 2][:5]

def snippet_match(story_text: str, snippet: str) -> float:
    """
    Tỉ lệ cụm 2 từ của đoạn trích Google (tiêu đề + snippet) có xuất hiện trong truyện.
    Đoạn trích ngắn nên đo theo phía snippet: 0 = không liên quan, 1 = trùng hoàn toàn.
    """
    p2 = _shingles(snippet, 2)
    if not p2:
        return 0.0
    s2 = _shingles(story_text, 2)
    return round(len(p2 & s2) / len(p2), 3)


def similarity(story_text: str, post_text: str, names: list[str] | None = None) -> dict:
    """Trả về điểm 0..1 và các thành phần để giải thích."""
    s3, p3 = _shingles(story_text, 3), _shingles(post_text, 3)
    s2, p2 = _shingles(story_text, 2), _shingles(post_text, 2)
    tri = len(s3 & p3) / len(s3) if s3 else 0.0
    bi = len(s2 & p2) / len(s2) if s2 else 0.0
    post_norm = normalize(post_text)
    names = names or []
    name_hits = [n for n in names if normalize(n) in post_norm]
    name_score = len(name_hits) / len(names) if names else 0.0
    score = 0.45 * tri + 0.25 * bi + 0.30 * name_score
    return {
        "score": round(score, 3),
        "trigram": round(tri, 3),
        "bigram": round(bi, 3),
        "names_found": name_hits,
    }

