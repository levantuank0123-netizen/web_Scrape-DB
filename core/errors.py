"""Phân loại lỗi kỹ thuật → thông báo nghiệp vụ tiếng Việt + cờ permanent.

7 loại lỗi chính thức (theo định nghĩa đầu):
  - Login fill xong vẫn ở login → "TK bị Xóa Dashboard" (permanent)
  - TimeoutError chờ ô email → "Trang login lỗi / chuyển hướng" (permanent)
  - Có captcha → "Có Captcha — cần login thủ công" (permanent)
  - 404 / không tồn tại → "Dashboard không tồn tại" (permanent)
  - Lỗi mạng / timeout chung → "Lỗi kết nối" (transient)
  - Profile chưa login + ko có pass → "Chưa login + không có pass" (permanent)
  - Khác → giữ nguyên text gốc rút gọn (transient)
"""
from __future__ import annotations
import re

# (regex pattern, business message, permanent_flag)
ERROR_RULES = [
    # Permanent — sẽ được skip trong các lần chạy sau
    (r"(affiliate\s*[/\\]?\s*referral\s+program\s+is\s+disabled|program\s+is\s+disabled|aff\s+program\s+disable)",
     "AFF Program Disable", True),
    # Login form fill xong mà vẫn ở login → TK bị xóa (chỉ khi login flow đã chạy)
    (r"(login\s*th[ấâ]t\s*b[ạa]i|stayed on login|v[ẫâ]n[\s\S]*?trang\s+login)",
     "TK bị Xóa Dashboard", True),
    # Login fail/page load chậm (mới) → transient
    (r"(login\s*fail|page\s*load\s*ch[ậa]m|kh[ôo]ng\s*l[ấâ]y\s*đư[ợo]c\s*s[ốo]\s*li[ệe]u)",
     "Login fail / page load chậm", False),
    (r"(captcha|recaptcha|hcaptcha|cloudflare\s*turnstile)",
     "Có Captcha — cần login thủ công", True),
    (r"(timeout.*?wait_for_selector.*?email|wait_for_selector.*?input.*?email|kh[ôo]ng\s*t[ìi]m\s*th[ấâ]y\s*form\s*login)",
     "Trang login lỗi / chuyển hướng", True),
    (r"(404|page not found|kh[ôo]ng t[ìi]m th[ấâ]y|trang kh[ôo]ng t[ồo]n t[ạa]i)",
     "Dashboard không tồn tại", True),
    (r"(profile\s*ch[ưu]a\s*login|kh[ôo]ng\s*c[óo]\s*email/password)",
     "Chưa login + không có pass", True),

    # Transient — sẽ retry lần sau
    (r"(429|rate\s*limit|too\s*many\s*requests)",
     "Lỗi kết nối", False),
    (r"(ECONNREFUSED|ETIMEDOUT|net::ERR|connection\s*reset|timeout.*?goto|profile open error|gpm start)",
     "Lỗi kết nối", False),
]


def classify(error_text: str | None) -> tuple[str | None, bool]:
    """Chuyển error_text → (business_message, permanent)."""
    if not error_text:
        return None, False
    text = str(error_text).strip()

    # Identity: nếu error đã là 1 trong các business message chuẩn → giữ nguyên + đúng cờ permanent
    PERMANENT_OUTPUTS = {
        "TK bị Xóa Dashboard",
        "Có Captcha — cần login thủ công",
        "Trang login lỗi / chuyển hướng",
        "Dashboard không tồn tại",
        "Chưa login + không có pass",
        "AFF Program Disable",
    }
    if text in PERMANENT_OUTPUTS:
        return text, True

    for pattern, msg, permanent in ERROR_RULES:
        if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
            return msg, permanent
    # Chưa khớp rule: rút gọn để khỏi tràn ô + retry
    short = re.sub(r"\s+", " ", text).strip()[:200]
    return short, False
