# Reels Studio

> **README này dành cho chủ dự án**, không dành cho AI agent.
> Hướng dẫn cho agent nằm trong CLAUDE.md và skill .claude/skills/project-knowledge/.

## Giới thiệu

[Mô tả ngắn: dự án làm gì và vì sao tồn tại]

## Cấu trúc dự án

```
.claude/                    # Kho tri thức cho AI agent (Claude Code)
├── skills/
│   └── project-knowledge/  # Tài liệu dự án (kiến trúc, pattern, ...)
└── agents/                 # Agent review / validate
.codex/                     # Bản sinh tự động cho Codex — không sửa tay
.githooks/pre-commit        # Đồng bộ .claude/** sang .codex/** + AGENTS.md

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
2. Điền tài liệu dự án: mở Claude Code và yêu cầu "điền tài liệu dự án" (skill
   `documentation-writing`) — sẽ có buổi phỏng vấn để viết Project Knowledge, CLAUDE.md và README.
3. Lên spec cho tính năng đầu tiên bằng skill `user-spec-planning`.

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
