# Reels Studio

> **README này dành cho chủ dự án**, không dành cho AI agent.
> Hướng dẫn cho agent nằm trong CLAUDE.md và skill .claude/skills/project-knowledge/.

## Giới thiệu

Web app nội bộ tạo video ngắn dọc 9:16 (20–40 giây) cho Reels, TikTok và Shorts: nhập chủ đề → Claude viết kịch bản chia cảnh → gán ảnh → render bằng FFmpeg ra MP4. Mục tiêu: giảm thời gian lên ý tưởng và dựng video cho team khoảng 5 người.

## Cấu trúc dự án

```
.claude/                    # Kho tri thức cho AI agent (Claude Code)
├── skills/
│   └── project-knowledge/  # Tài liệu dự án (kiến trúc, pattern, ...)
└── agents/                 # Agent review / validate
.codex/                     # Bản sinh tự động cho Codex — không sửa tay
.githooks/pre-commit        # Đồng bộ .claude/** sang .codex/** + AGENTS.md

worker/           # Lõi render video (Python, CLI reels_render)
api/              # FastAPI: đăng nhập, phiên, quản lý người dùng (Postgres + Alembic)
web/              # Next.js + Ant Design: giao diện web
docker-compose.yml  # Postgres cho máy dev
docker-compose.coolify.yml  # Stack production trên Coolify (api + postgres)

backlog.md        # Ý tưởng tính năng và lỗi (làm sau)
work/             # Tính năng và lỗi đang làm
└── [feature]/    # Mỗi tính năng có một user-spec.md
```

## Phương pháp phát triển

Dự án dùng cách làm **spec-driven** với AI agent:

1. **User Spec** (viết bằng ngôn ngữ của người dùng) → thống nhất kết quả mong muốn
2. **Triển khai** → một phiên agent mới thực hiện user-spec đó
3. **Hoàn tất** → cập nhật tài liệu dự án và lưu trữ tính năng vào `work/completed/`

Ý tưởng tính năng và lỗi đã biết ghi trong `backlog.md`. Việc đang làm nằm trong thư mục `work/`.

## Bắt đầu

1. Bật git hook (một lần sau khi clone): `git config core.hooksPath .githooks`
2. Tài liệu dự án đã có trong `.claude/skills/project-knowledge/`. Muốn cập nhật thì yêu cầu
   "cập nhật tài liệu" (skill `documentation-writing`).
3. Lên spec cho tính năng đầu tiên bằng skill `user-spec-planning`.

## Chạy web app trên máy (localhost)

Cần: Docker Desktop (Windows cần WSL2: `wsl --install` bằng quyền admin rồi khởi động lại máy),
Python 3.12, Node 20.9 trở lên. Mọi lệnh chạy từ thư mục gốc repo, trong PowerShell.

1. **Cấu hình:** chép `.env.example` thành `.env` (nếu đã có `.env` thì thêm các dòng còn thiếu).
2. **Postgres:** `docker compose up -d postgres`. Lần đầu (volume trống) container tạo sẵn ba
   database: `reels` (dev), `reels_test` (pytest), `reels_e2e` (Playwright).
3. **api** (một lần):
   ```powershell
   cd api
   py -3.12 -m venv .venv
   .venv\Scripts\python -m pip install -e ".[dev]"
   .venv\Scripts\alembic upgrade head
   .venv\Scripts\python -m reels_api create-user   # tạo người dùng đầu tiên (mật khẩu nhập ẩn)
   ```
4. **web** (một lần): `cd web` rồi `npm install` và `npx playwright install chromium`.
5. **Chạy** (hai cửa sổ terminal):
   ```powershell
   cd api; .venv\Scripts\python -m uvicorn reels_api.main:create_app --factory --port 8000
   cd web; npm run dev
   ```
   Mở http://localhost:3000 và đăng nhập.

**Khôi phục khi bị khóa ngoài** (quên mật khẩu, bị vô hiệu hoá): chạy lại
`.venv\Scripts\python -m reels_api create-user` trong `api/` với email đã có. Lệnh hỏi xác nhận rồi
đặt mật khẩu mới, kích hoạt lại và đăng xuất mọi phiên cũ.

**Kiểm thử:** `cd api; .venv\Scripts\python -m pytest` (cần Postgres đang chạy) và
`cd web; npm run e2e` (tự bật api và web riêng ở cổng 8100/3100 trên `reels_e2e`; chạy được cả khi
server dev đang bật).

## Triển khai (CI/CD)

Workflow `.github/workflows/ci-cd.yml` chạy kiểm thử (api, worker, web + E2E, build Cloudflare)
trên mọi PR. Khi merge vào `main` và mọi kiểm thử đều qua, workflow mới triển khai:

1. **api + postgres → Coolify:** gọi deploy webhook, Coolify tự build từ git theo
   `docker-compose.coolify.yml`, chạy migration khi khởi động. Workflow chờ Coolify báo `finished`.
2. **web → Cloudflare:** build bằng OpenNext rồi `wrangler deploy` (Cloudflare Workers — Cloudflare
   khuyên dùng cho Next.js thay cho Pages). `/api/*` được chuyển tiếp tới domain api trên Coolify,
   nên cookie phiên vẫn thuộc domain web.

**Cài đặt một lần:**

1. **Coolify:** tạo resource mới → chọn repo này (GitHub App hoặc deploy key), nhánh `main`,
   build pack **Docker Compose**, Docker Compose Location `/docker-compose.coolify.yml`.
   - Gán domain cho service `api`, ví dụ `https://api.example.com` (cổng 8000).
   - Biến môi trường: `ALLOWED_ORIGINS=https://app.example.com` (domain web).
     `SERVICE_PASSWORD_POSTGRES` do Coolify tự sinh.
   - Advanced → Auto deploy: chọn **Manual deployments only**, để chỉ GitHub Actions triển khai
     sau khi kiểm thử qua.
   - Keys & Tokens → tạo API token quyền `deploy`. Webhook nằm ở tab Webhooks của resource.
2. **Cloudflare:** tạo API token theo mẫu "Edit Cloudflare Workers"; ghi lại Account ID. Sau lần
   deploy đầu, vào Workers → `reels-studio-web` → Settings → Domains & Routes để gắn domain web
   (`app.example.com`).
3. **GitHub** (Settings → Environments → tạo environment `production`):
   - Secrets: `COOLIFY_WEBHOOK`, `COOLIFY_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
   - Variable: `API_URL=https://api.example.com` (domain api trên Coolify, không có `/` cuối).
4. **Người dùng đầu tiên:** trong Coolify mở Terminal của container `api` và chạy
   `python -m reels_api create-user`.

Nếu domain api cũng đi qua Cloudflare (đám mây cam), đặt SSL/TLS là **Full (strict)**.

## Online Pipeline (tùy chọn)

Repo đã có sẵn các workflow GitHub Actions để chạy toàn bộ vòng đời tính năng (issue → phỏng vấn →
PR spec → duyệt → triển khai → PR code → hoàn tất) chỉ qua GitHub, không cần terminal. Kèm theo là
bản sao (vendored) các skill và agent mà workflow cần, trong `.claude/skills/` và `.claude/agents/`.
Tất cả chưa hoạt động cho đến khi cài đặt xong:

1. Cài Claude GitHub App cho repo (chạy `claude` và dùng `/install-github-app`, hoặc vào
   https://github.com/apps/claude).
2. Tạo credential Claude — `claude setup-token` (OAuth) hoặc API key từ
   https://console.anthropic.com — và lưu thành secret `CLAUDE_CODE_OAUTH_TOKEN` hoặc
   `ANTHROPIC_API_KEY` của repo.
3. Tạo Personal Access Token (quyền `repo`) tại https://github.com/settings/tokens và lưu thành
   secret `GH_PAT` (chỉ cần để việc duyệt PR spec kích hoạt được job triển khai).

Sau khi đặt secret, mở một issue mới để bắt đầu pipeline.

Các skill/agent vendored là bản chụp và sẽ cũ dần. Chạy lại
`.claude/skills/online-pipeline/scripts/vendor-skills.sh` để kéo bản mới nhất — không có gì được
commit tự động, hãy xem diff trước.
