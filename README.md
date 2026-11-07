# Reels Studio

> **README này dành cho chủ dự án**, không dành cho AI agent.
> Rules cho mọi AI agent (Claude, Codex, Cursor, ...) nằm trong `AGENTS.md`; tài liệu dự án nằm trong `docs/`.

## Giới thiệu

Web app nội bộ tạo video ngắn dọc 9:16 (20–40 giây) cho Reels, TikTok và Shorts: nhập chủ đề → Claude viết kịch bản chia cảnh → gán ảnh → render bằng FFmpeg ra MP4. Mục tiêu: giảm thời gian lên ý tưởng và dựng video cho team khoảng 5 người.

## Cấu trúc dự án

```
AGENTS.md         # Rules chung cho mọi AI agent (CLAUDE.md chỉ import file này)
docs/             # Tài liệu dự án: kiến trúc, pattern, triển khai, UX, nội dung
└── specs/        # Spec của các tính năng đầu tiên (lịch sử)
ruff.toml         # Cấu hình lint Python cho api/ và worker/

worker/           # Lõi render video (Python, CLI reels_render)
api/              # FastAPI: đăng nhập, phiên, quản lý người dùng (Postgres + Alembic)
web/              # Next.js + Ant Design: giao diện web
docker-compose.yml  # Postgres cho máy dev

```

## Cách làm việc với AI

- Mọi AI agent đọc `AGENTS.md`: cách làm (gọn, không subagent), lệnh lint/test, quy tắc dễ sai,
  quy trình git. Sửa rules thì sửa ở đó, không tạo bản riêng cho từng AI.
- Tài liệu dự án trong `docs/` được cập nhật cùng PR khi hành vi thay đổi.
- Tính năng lớn ghi kế hoạch ngắn trong mô tả PR. Ý tưởng, tính năng và lỗi
  ghi thành [Issue](https://github.com/tuananh219ln/Reels-Studio/issues) theo mẫu có sẵn (Lỗi, Tính năng, Ý tưởng).

**Kiểm soát code do AI viết:**

- Repo của cả team, không có người sở hữu riêng: PR nào CI xanh hết (và đã cập nhật theo `main`)
  là được merge, kể cả do agent merge khi được nhờ. Không merge khi còn check đỏ hoặc đang chạy, không
  dùng `--admin` để vượt.
- `.github/pull_request_template.md`: mỗi PR ghi làm gì, kiểm tra thế nào, rủi ro gì.
- `.claude/settings.json`: Claude Code không được đọc `.env`, force push, `reset --hard`, hạ
  migration hay push thẳng lên `main`; muốn sửa CI, luật lint, migration hay rules thì phải hỏi.
- `.github/workflows/claude-review.yml`: AI review một PR **chỉ khi** người có quyền ghi vào repo
  comment `/ai-review` trên PR đó (mỗi lần chạy tốn phí API); kết quả là comment tiếng Việt. Cần
  secret `ANTHROPIC_API_KEY` (hoặc `CLAUDE_CODE_OAUTH_TOKEN` từ `claude setup-token`) trong
  Settings → Secrets and variables → Actions. Workflow kiểu này chỉ chạy khi file đã nằm trên `main`.
- `.github/workflows/claude-ask.yml`: hỏi AI về dự án ngay trong issue hoặc PR bằng comment có
  `@claude` (ví dụ `@claude lỗi này nằm ở file nào?`). Chỉ người có quyền ghi gọi được, mỗi lần
  tốn phí API. Claude chỉ đọc repo và trả lời bằng comment tiếng Việt, không sửa code hay tạo PR.
  Dùng chung secret với `claude-review.yml`.

## Chạy web app trên máy (localhost)

**macOS/Linux, một lệnh:** cài `uv`, Docker Desktop, Node 22 và FFmpeg (`brew install uv node@22
ffmpeg`), rồi từ thư mục gốc repo chạy `./scripts/dev.sh`. Script tự bật Postgres, tạo `.env` nếu
chưa có, dựng lại `api/.venv` đúng Python 3.12 khi venv thiếu, sai phiên bản hoặc repo bị chuyển
thư mục, chạy migration, rồi chạy api, worker và web trong cùng một terminal (Ctrl+C tắt cả ba).
Lần đầu vẫn cần tạo người dùng: `cd api && .venv/bin/python -m reels_api create-user`.
Muốn có dữ liệu thật để thử: `docker/pull-prod-db.sh` (xem docs/deployment.md), rồi chạy lại
`./scripts/dev.sh`.

Các bước dưới đây là cách làm tay (lệnh PowerShell cho Windows):

Cần: Docker Desktop (Windows cần WSL2: `wsl --install` bằng quyền admin rồi khởi động lại máy),
Python 3.12, Node 20.9 trở lên, FFmpeg (`winget install Gyan.FFmpeg`, cho worker render). Mọi lệnh
chạy từ thư mục gốc repo, trong PowerShell.

1. **Cấu hình:** chép `.env.example` thành `.env` (nếu đã có `.env` thì thêm các dòng còn thiếu).
   Muốn viết kịch bản thật thì điền `ANTHROPIC_API_KEY`.
2. **Postgres:** `docker compose up -d postgres`. Lần đầu (volume trống) container tạo sẵn ba
   database: `reels` (dev), `reels_test` (pytest), `reels_e2e` (Playwright).
3. **api** (một lần):
   ```powershell
   cd api
   py -3.12 -m venv .venv
   .venv\Scripts\python -m pip install -e ..\worker -e ".[dev]"   # api dùng cả bộ render reels_render
   .venv\Scripts\alembic upgrade head
   .venv\Scripts\python -m reels_api create-user   # tạo người dùng đầu tiên (mật khẩu nhập ẩn)
   ```
4. **web** (một lần): `cd web` rồi `npm install` và `npx playwright install chromium`.
5. **Chạy** (ba cửa sổ terminal):
   ```powershell
   cd api; .venv\Scripts\python -m uvicorn reels_api.main:create_app --factory --port 8000
   cd api; .venv\Scripts\python -m reels_api worker   # nhận job viết kịch bản và render
   cd web; npm run dev
   ```
   Mở http://localhost:3000 và đăng nhập. File (ảnh, MP4) nằm trong `data/storage/` ở gốc repo,
   hoặc thư mục `STORAGE_DIR` nếu có đặt.

**Khôi phục khi bị khóa ngoài** (quên mật khẩu, bị vô hiệu hoá): chạy lại
`.venv\Scripts\python -m reels_api create-user` trong `api/` với email đã có. Lệnh hỏi xác nhận rồi
đặt mật khẩu mới, kích hoạt lại và đăng xuất mọi phiên cũ.

**Kiểm thử:** `cd api; .venv\Scripts\python -m pytest -n 4` (cần Postgres đang chạy; các test worker và
so khớp render cần FFmpeg trên PATH; `-n 4` chạy 4 tiến trình song song, mỗi tiến trình một database
`reels_test_gw0`... tự tạo, cần cài lại `pip install -e ".[dev]"` để có `pytest-xdist`) và `cd web; npm run e2e`
(tự bật api, worker, Claude/Pixabay giả ở cổng 8199 và web riêng ở cổng 8100/3100 trên `reels_e2e`; chạy được cả
khi server dev đang bật).

**Chạy nhanh trước khi đẩy lên:** chỉ chạy phần mình sửa, để CI chạy đủ bộ test.

- api: `python -m pytest tests/test_publish.py` (một file), `-k "ten_test"` (theo tên), `--lf -x` (chỉ
  các test lỗi lần trước, dừng ở lỗi đầu tiên).
- web: `npx playwright test -g "tên test"` (theo tên), `npx playwright test e2e/app.spec.ts` (một file),
  `npx playwright test --last-failed` (chỉ các test lỗi lần trước).

## Triển khai (CI/CD)

Workflow `.github/workflows/ci-cd.yml` chạy kiểm thử (api, worker, web + E2E, build Cloudflare)
trên mọi PR. pytest của api và E2E đều chia ra 4 máy chạy song song. PR còn **Draft** chỉ chạy kiểm tra nhanh (lint,
typecheck, pytest); E2E và build Docker image chạy khi bấm **Ready for review**. PR chỉ sửa `docs/`
hoặc file `.md` không chạy CI. Khi merge vào `main` và mọi kiểm thử đều qua, workflow mới triển khai:

1. **api → Coolify:** gọi deploy webhook, Coolify tự build `api/Dockerfile` từ git, container
   chạy migration khi khởi động. Workflow chờ Coolify báo `finished`. Postgres là một database
   riêng trên Coolify, không bị deploy lại.
2. **worker → Coolify:** sau khi api xong (đã có migration), gọi webhook của app worker
   (`api/Dockerfile.worker`, có FFmpeg) và chờ tương tự. Khi deploy, Coolify có thể chạy worker cũ
   và mới cùng lúc một lát: worker mới chờ khóa trong Postgres tới khi worker cũ tắt hẳn, rồi mới
   nhận job. Job đang chạy dở lúc worker cũ tắt thành Lỗi "Worker khởi động lại giữa chừng"; bấm
   Thử lại trên trang video.
3. **web → Cloudflare:** build bằng OpenNext rồi `wrangler deploy` (Cloudflare Workers — Cloudflare
   khuyên dùng cho Next.js thay cho Pages). `/api/*` được chuyển tiếp tới domain api trên Coolify,
   nên cookie phiên vẫn thuộc domain web.

**Cài đặt một lần:**

1. **Coolify — Postgres:** + New → Database → **PostgreSQL** (bản 17), Initial Database `reels`,
   không bật Make it publicly available. Start, rồi bật **Scheduled Backups**. Copy
   **Postgres URL (internal)**.
2. **Thư mục file dùng chung** (ảnh, MP4, ảnh thu nhỏ; api ghi, worker đọc và ghi): trên server
   Coolify chạy một lần `sudo mkdir -p /data/reels-storage && sudo chown 10001:10001 /data/reels-storage`
   (10001 là user `app` trong cả hai image). Mỗi video khoảng 10–30 MB; xóa video là xóa hẳn file.
3. **Coolify — api:** + New → Application từ repo này (GitHub App hoặc deploy key), nhánh `main`,
   build pack **Dockerfile**, **Base Directory `/`**, **Dockerfile Location `/api/Dockerfile`**
   (image cần cả `worker/`), cổng `8000`, cùng server và cùng project với Postgres. App api đã có từ
   trước thì sửa Base Directory từ `/api` thành `/` và Dockerfile Location như trên.
   - Domain: ví dụ `https://api.example.com`.
   - Biến môi trường: `DATABASE_URL` = Postgres URL (internal) vừa copy (dán nguyên, app tự đổi
     `postgres://` thành driver psycopg), `ALLOWED_ORIGINS=https://app.example.com` (domain web),
     `COOKIE_SECURE=true`, `PIXABAY_API_KEY`, `STORAGE_DIR=/data/storage`.
   - Persistent Storage → **Directory Mount**: Source `/data/reels-storage`, Destination
     `/data/storage`.
   - Advanced → Auto deploy: chọn **Manual deployments only**, để chỉ GitHub Actions triển khai
     sau khi kiểm thử qua.
   - Keys & Tokens → tạo API token quyền `deploy`. Webhook nằm ở tab Webhooks của application.
4. **Coolify — worker:** + New → Application từ cùng repo, nhánh `main`, build pack **Dockerfile**,
   Base Directory `/`, Dockerfile Location `/api/Dockerfile.worker`, cùng server và project. Không cần
   domain hay cổng (worker không nhận request; nếu Coolify bắt buộc cổng thì để mặc định và tắt
   health check).
   - Biến môi trường: `DATABASE_URL` (giống api), `ANTHROPIC_API_KEY`, `PIXABAY_API_KEY`,
     `STORAGE_DIR=/data/storage`; tùy chọn `CLAUDE_MODEL` (mặc định `claude-sonnet-5-5`).
   - Persistent Storage → Directory Mount: Source `/data/reels-storage`, Destination `/data/storage`
     (đúng thư mục như api).
   - Auto deploy: **Manual deployments only**. Webhook ở tab Webhooks.
5. **Cloudflare:** tạo API token theo mẫu "Edit Cloudflare Workers"; ghi lại Account ID. Sau lần
   deploy đầu, vào Workers → `reels-studio-web` → Settings → Domains & Routes để gắn domain web
   (`app.example.com`).
6. **GitHub** (Settings → Environments → tạo environment `production`):
   - Secrets: `COOLIFY_WEBHOOK` (api), `COOLIFY_WORKER_WEBHOOK` (worker), `COOLIFY_TOKEN`,
     `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
   - Variable: `API_URL=https://api.example.com` (domain api trên Coolify, không có `/` cuối).
7. **Người dùng đầu tiên:** trong Coolify mở Terminal của container `api` và chạy
   `python -m reels_api create-user`.

Nếu domain api cũng đi qua Cloudflare (đám mây cam), đặt SSL/TLS là **Full (strict)**.

**Kiểm tra sau khi deploy** (chỉ thấy được trên hạ tầng thật):

- Làm một video từ chủ đề tới MP4 và bấm giờ (mục tiêu ≤ 10 phút); xem "render mất … giây" trên
  trang video (mục tiêu ≤ 2× độ dài video).
- Tải một ảnh lên một cảnh rồi render: MP4 có ảnh đó nghĩa là api và worker thấy cùng thư mục file.
- Phát và **tua** MP4 trong trình duyệt trên domain web: tua được nghĩa là yêu cầu Range (206) đi
  qua được Cloudflare/OpenNext.
