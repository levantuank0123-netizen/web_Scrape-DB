# Skill: Rewardful (getrewardful.com)

**Status**: ✅ DONE
**Adapter file**: [`scrapers/getrewardful.py`](../scrapers/getrewardful.py)
**Platform key**: `getrewardful`

## Đặc điểm Platform

Rewardful là affiliate platform white-label dùng cho SaaS. Mỗi brand có 1 subdomain riêng:
- `{brand}.getrewardful.com/` → Dashboard (sau khi login)
- `{brand}.getrewardful.com/login` → Form login (đôi khi redirect root nếu chưa có form)
- `{brand}.getrewardful.com/affiliates/sign_in` → Login route phụ

Mỗi brand subdomain dùng cookie riêng → 1 GPM profile có thể chứa nhiều brand miễn là khác subdomain.

## Flow Login

```
1. Goto dashboard_url (đã normalize về root /)
2. Nếu URL có "login"/"signin" HOẶC có visible password field → cần login
3. Login flow:
   a. Try /login, /affiliates/sign_in, /sign_in lần lượt
   b. Tìm password field visible
   c. Nếu không thấy → click link "Sign in"/"Log in" trên page
   d. Fill email + password + tick "Remember me" + submit
4. Verify login: URL không còn /login VÀ không có password field visible
```

## Fields được trích xuất

Từ trang **Dashboard**:

| Field | Nguồn | Pattern |
|---|---|---|
| `ref_link` | Pattern `https://...?via=xxx` hoặc `?ref=xxx` | Regex trên body text |
| `clicks` | Bảng "Visitors\|Leads\|Conversions" cột 1 | `Visitors\tLeads\tConversions\n123\t...\t...` |
| `ref_count` | Cột Leads | (cùng pattern trên) |
| `orders` | Cột Conversions | (cùng pattern trên) |
| `total_earned` | Bảng "Unpaid\|Paid\|Total Earned" cột 3 | Parse money tokens sau header |
| `unpaid` | Cột Unpaid | (cùng) |
| `paid` | Cột Paid | (cùng) |
| `due_now` | Subtitle "$xxx USD due now" dưới Unpaid | Regex riêng `$X due now` |
| `currency` | Symbol đầu tiên ($/€/£/¥/₫) | Tự detect |

## Bug đã fix (đáng nhớ)

### 1. dashboard_url chứa path lạ
Master sheet có URL như `swooped.getrewardful.com/profile` — path `/profile` không tồn tại, gây 404.
**Fix**: `_normalize_url()` luôn dùng `{scheme}://{netloc}/` (bỏ path).

### 2. /login redirect tới signup page
Một số brand `swooped` redirect `/login` → `/` (signup page).
**Fix**: Thử thứ tự `[/login, /affiliates/sign_in, /sign_in]`, sau đó click link "Sign in".

### 3. Layout bảng money có "due now" subtitle
Format text:
```
Unpaid    Paid    Total Earned
$484.53 USD
$335.82 USD due now
    $0 USD    $484.53 USD
```
Có 4 money token chứ không phải 3 → cần regex riêng cho due_now.
**Fix**: Tách phase: tìm "due now" trước, đếm tokens, gán đúng vị trí.

### 4. False positive _is_on_login
Trước: chỉ cần URL có "login" OR có password field → return True. Khi dashboard có hidden password (settings page) → false positive.
**Fix**: Yêu cầu URL match VÀ có visible password field.

## Performance

- Sequential: ~5s/dashboard (login + scrape + extract)
- Parallel (5 profiles): 78 dashboard ~3 phút (longest queue = 22)
- Cookie cache: lần chạy thứ 2 skip login bước → ~2s/dashboard

## Error classification (mapping)

Lỗi xử lý qua `core/errors.py`:
- Login form fill xong vẫn ở login → "TK bị Xóa Dashboard" (permanent)
- Không tìm thấy form login ở 3 URL → "Trang login lỗi / chuyển hướng" (permanent)
- 404 / page not found → "Dashboard không tồn tại" (permanent)
- Captcha detect → "Có Captcha — cần login thủ công" (permanent)
- Layout extract trả None toàn bộ → "TK bị Xóa Dashboard" hoặc "TK chưa được duyệt" (permanent)
- Connection error / GPM start fail → "Lỗi kết nối" (transient, retry)

## Cách dùng

### Chạy 1 dashboard
```bash
python -m core.runner --account alphana-ai
```

### Chạy theo platform
```bash
python -m core.runner --platform getrewardful --parallel
```

### Chạy theo owner
```bash
python -m core.runner --owner "Dũng" --platform getrewardful
```

### Force scrape (bỏ qua skip logic)
```bash
python -m core.runner --account alphana-ai --force
```

## Kết quả test (2026-06-22)

- 78 dashboard total
- 67 ok (86%)
- 11 lỗi "TK bị Xóa Dashboard"
- 15 có total_earned > 0
- 3 có due_now > 0 (aiapply $335.82, foreplayco $83.20, elai $7.25)
- Tổng commission unpaid: ~$1100

## TODO / Hạn chế

- Số liệu hiện là **tổng tích lũy**, không phải số của ngày `metric_date`. Cần dùng date filter của Rewardful (nếu có) hoặc tính delta giữa các ngày liên tiếp.
- Một số brand có dashboard tùy biến (custom theme) có thể khiến regex không match → cần kiểm tra body_text trong `raw_json`.
- Heyberries case: login OK nhưng không có data → có thể TK chưa được duyệt, hoặc dashboard layout khác.
