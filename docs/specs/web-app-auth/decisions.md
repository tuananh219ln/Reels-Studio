# Решения: web-app-auth

<!-- Добавляй запись только для существенного решения или отклонения от user-spec.

## Краткое название решения

**Что решили:** решение.
**Почему:** причина.
**Отклонение от user-spec:** нет / что изменилось и почему.
-->

## 127.0.0.1 thay cho localhost trong URL nội bộ

**Что решили:** `DATABASE_URL`, `TEST_DATABASE_URL` và `API_URL` dùng `127.0.0.1`; E2E dùng
`API_URL=http://127.0.0.1:8100`. Origin của trình duyệt vẫn là `http://localhost:3000` / `:3100`.
**Почему:** trên máy dev, `localhost` thử IPv6 (`::1`) trước; Postgres và uvicorn chỉ nghe IPv4 nên
mỗi kết nối chậm thêm 5 giây (đo được: 127.0.0.1 0.02s, localhost 5.05s).
**Отклонение от user-spec:** spec ghi mặc định `API_URL=http://localhost:8000` và E2E
`API_URL=http://localhost:8100`; đổi host sang `127.0.0.1`, cổng và hành vi giữ nguyên.
