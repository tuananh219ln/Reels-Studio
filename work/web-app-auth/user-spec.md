---
# Creation date (YYYY-MM-DD)
created: 2026-10-29

# Status: draft | approved
status: draft

# Work type: feature | bug | refactoring
type: feature
---

# User-spec: web-app-auth

> **Executor instruction.** If the project has Project Knowledge, first read its main `SKILL.md`,
> then only the materials it routes to for this task. Read `decisions.md` if it exists. Work from
> the root of the project this spec belongs to. Implement the entire user-spec. Use the execution
> skills appropriate to the work.

## What We Are Building

Web app đầu tiên của Reels Studio, chạy trên máy dev (localhost):
- **Giao diện (`web/`):** Next.js 16 (App Router, TypeScript) và Ant Design.
- **Backend (`api/`):** FastAPI.
- **Database:** Postgres, chạy bằng `docker compose`.

Thành viên đăng nhập bằng email và mật khẩu; người dùng đầu tiên được tạo bằng một lệnh CLI. App có
khung giao diện theo bản thiết kế đã chốt, màn Video trống, và màn Quản lý người dùng: thêm người,
vô hiệu hoá, đặt mật khẩu tạm, đăng xuất khỏi mọi thiết bị. Đây là nền cho các màn MVP sau (soạn
kịch bản, render, kho kiến thức).

## Why

Hiện dự án chỉ có CLI render (`worker/`). Đội 2–5 người cần một web app có đăng nhập và quản lý
người dùng để các tính năng MVP tiếp theo (soạn kịch bản, render, kho kiến thức) có chỗ gắn vào.
Thành viên tự quản lý tài khoản cho nhau mà không cần đụng vào database.

## Expected Behavior

1. **Dựng app lần đầu.**
   - Người dùng chép `.env.example` thành `.env`, bật Postgres bằng `docker compose up -d postgres`.
   - Chạy lệnh migration, rồi chạy lệnh CLI tạo người dùng: nhập email, tên và mật khẩu. Mật khẩu
     nhập ẩn hai lần trong terminal.
   - Bật api (cổng 8000) và web (cổng 3000), mở `http://localhost:3000`.
   - README ghi đủ các lệnh theo thứ tự.
2. **Đăng nhập.**
   - Trang đăng nhập có email, mật khẩu và nút "Đăng nhập".
   - Đúng thông tin thì vào app ở màn Video. Phiên giữ 30 ngày và được gia hạn mỗi lần dùng.
   - Chưa đăng nhập mà mở một trang trong app thì bị chuyển về trang đăng nhập.
3. **Bắt buộc đổi mật khẩu.**
   - Người đăng nhập bằng mật khẩu tạm (do đồng đội đặt) phải đổi mật khẩu trước khi làm bất cứ
     việc gì khác.
   - Màn này không hỏi mật khẩu cũ, chỉ hỏi mật khẩu mới hai lần (tối thiểu 8 ký tự).
4. **Khung app.**
   - Theo bản thiết kế https://claude.ai/artifact/9rHaJJFHQMgVcnEXLvQXcB và phong cách MKT-Tools:
     menu trái nền trắng, mục đang chọn tô teal `#0F3B4C` chữ trắng, logo là nhãn "RS" xanh lá cạnh
     chữ "Reels Studio", nền trang `#F7F7F7`, thẻ trắng viền `#EDEDED`.
   - Header bên phải có vòng tròn chữ cái, tên và menu tài khoản: Đổi mật khẩu, Sửa tên, Đăng xuất.
   - Menu trái có: Video, Kho kiến thức, Thư viện nhạc, Quản lý người dùng, Job logs.
   - Kho kiến thức, Thư viện nhạc và Job logs mở ra trang trống "Sắp có", kiểu "Chưa có dữ liệu".
5. **Video.** Tiêu đề "Video" và khung trống "Chưa có video nào". Chưa có nút tạo video.
6. **Quản lý người dùng.** Bố cục theo ảnh MKT-Tools nhưng không có cột Vai trò.
   - Ô tìm theo email hoặc tên, và nút "Thêm người dùng".
   - Các cột:
     - Ảnh: vòng tròn chữ cái đầu của từ cuối trong tên, ví dụ "Nguyễn Văn An" → "A".
     - Email.
     - Tên.
     - Trạng thái: Hoạt động hoặc Vô hiệu hoá.
     - Đăng nhập gần nhất (`dd/mm/yyyy hh:mm`).
     - Phiên hoạt động: số phiên còn hạn.
     - Thao tác.
   - Thao tác trên người đang hoạt động: "Vô hiệu hoá", "Đặt mật khẩu tạm", "Đăng xuất khỏi mọi
     thiết bị".
   - Thao tác trên người bị vô hiệu hoá: chỉ có "Kích hoạt lại".
   - Dòng của chính mình hiện "Tài khoản của bạn", không có thao tác.
   - "Thêm người dùng" mở hộp thoại nhập email, tên và mật khẩu tạm do người thêm tự gõ. Người mới
     phải đổi mật khẩu ở lần đăng nhập đầu.
7. **Vô hiệu hoá và kích hoạt lại.**
   - Cả hai đều có hộp xác nhận.
   - Người bị vô hiệu hoá không đăng nhập được, và mọi phiên của họ hết hiệu lực ngay.
   - Không ai vô hiệu hoá được chính mình hay người hoạt động cuối cùng.
8. **Đặt mật khẩu tạm.** Người làm gõ mật khẩu mới. Người được đặt bị đăng xuất khỏi mọi thiết bị
   và phải đổi mật khẩu khi đăng nhập lại.
9. **Đổi mật khẩu từ menu tài khoản.** Nhập mật khẩu hiện tại và mật khẩu mới hai lần. Đổi xong
   thì các phiên khác bị đăng xuất, phiên đang dùng được giữ.
10. **Khôi phục bằng CLI.**
    - Chạy lệnh CLI với một email đã có. CLI hỏi xác nhận, rồi đặt mật khẩu mới, kích hoạt lại và
      đăng xuất mọi phiên cũ của người đó.
    - Tên cũ được giữ, và người đó không bị bắt đổi mật khẩu.
    - Đây là cách gỡ khi cả đội bị khóa ngoài.
11. **Trên điện thoại.** Ở cỡ màn hẹp, menu trái thu gọn thành nút mở menu, bảng cuộn ngang.
    Kiểm tra bằng chế độ thiết bị của trình duyệt; giai đoạn này app chỉ mở trên localhost.

## Acceptance Criteria

**Dựng và chạy**
- [ ] Thư mục `web/` và `api/` nằm ở gốc repo, mỗi phần tự quản lý phụ thuộc (giống `worker/`).
- [ ] `docker-compose.yml` ở gốc repo chỉ có service `postgres`:
  - `docker compose up -d postgres` bật được Postgres.
  - Lần khởi động đầu (volume trống), script khởi tạo của container tạo sẵn ba database: dev,
    `reels_test` và `reels_e2e`.
- [ ] `.gitattributes` ép `*.sh` (và mọi script chạy trong container) dùng xuống dòng LF, để script
      khởi tạo không hỏng khi checkout trên Windows (`core.autocrlf=true`).
- [ ] Alembic tạo đủ bảng trên database mới (`alembic upgrade head`):
  - Database dev: người dùng chạy theo README.
  - `reels_test`: pytest tự chạy migration trước khi chạy test.
  - `reels_e2e`: lệnh chạy E2E tự chạy migration.
- [ ] README ghi đủ các lệnh, theo thứ tự, để từ một máy có Docker đi tới mở được
      `http://localhost:3000`.
- [ ] `.env.example` có `DATABASE_URL`, `TEST_DATABASE_URL`, `ALLOWED_ORIGINS`, `API_URL`, kèm giá trị
      mẫu cho localhost. Không có `SESSION_SECRET`.
- [ ] Cấu hình:
  - api đọc `.env` ở gốc repo, và biến môi trường thật được ưu tiên hơn `.env` (cùng quy tắc với
    `worker/`).
  - `ALLOWED_ORIGINS` mặc định là `http://localhost:3000`.
  - Web đọc `API_URL` làm đích rewrite `/api/*` cả khi chạy `next dev` lẫn `next build`, kể cả khi
    biến này chỉ nằm trong `.env` ở gốc repo. Mặc định là `http://localhost:8000`.
- [ ] Web không nạp nhầm package từ `node_modules/` cũ ở gốc repo. Kiểm chứng: không còn
      `node_modules/` ở gốc repo, hoặc build và E2E của web chạy được khi thư mục đó đã bị đổi tên.

**Đăng nhập và phiên**
- [ ] Đăng nhập đúng thì vào màn Video. Sai mật khẩu, email không tồn tại hoặc tài khoản bị vô hiệu
      hoá kèm mật khẩu sai đều hiện cùng một thông báo "Email hoặc mật khẩu không đúng".
- [ ] Tài khoản bị vô hiệu hoá kèm mật khẩu đúng thì hiện "Tài khoản đã bị vô hiệu hoá" và không
      vào được app.
- [ ] Email được chuẩn hoá (bỏ khoảng trắng hai đầu, chuyển chữ thường) ở mọi nơi: đăng nhập, thêm
      người dùng, CLI.
- [ ] Phiên đăng nhập:
  - Là một token ngẫu nhiên; Postgres chỉ lưu bản hash của token.
  - Nằm trong cookie `httpOnly` với `SameSite=Lax`. Cờ `Secure` tắt khi chạy http trên localhost.
  - Hết hạn sau 30 ngày không dùng; mỗi lần dùng thì gia hạn lại 30 ngày.
  - Phiên hết hạn hoặc bị thu hồi khiến lần gọi tiếp theo trả 401, và web chuyển về trang đăng nhập.
- [ ] Mật khẩu được lưu bằng Argon2 và không bao giờ xuất hiện trong log, thông báo lỗi hay phản hồi
      API.
- [ ] "Đăng xuất" thu hồi phiên hiện tại và về trang đăng nhập.
- [ ] Request thay đổi dữ liệu (POST/PUT/PATCH/DELETE) có `Origin` không nằm trong `ALLOWED_ORIGINS`
      thì bị từ chối. Mặc định chỉ cho `http://localhost:3000`.
- [ ] Web gọi api qua rewrite `/api/*` tới `API_URL`, nên cookie nằm cùng trang và api không cần CORS.

**Bắt buộc đổi mật khẩu**
- [ ] Phiên của người đang mang cờ "phải đổi mật khẩu":
  - Gọi được `GET /api/me`, kết quả có `must_change_password: true`.
  - Đổi mật khẩu và đăng xuất được.
  - Mọi API khác trả 403 với mã `password_change_required`.
- [ ] Web thấy cờ này (khi tải trang hoặc khi gặp lỗi 403 kia) thì mở màn bắt buộc đổi mật khẩu; màn
      này không hỏi mật khẩu cũ.
- [ ] Mật khẩu mới phải từ 8 ký tự trở lên và hai lần nhập phải khớp; nếu không thì báo lỗi ngay trên
      form. Đổi xong:
  - Cờ được gỡ và người dùng vào màn Video.
  - Mọi phiên khác của người đó (ví dụ đăng nhập bằng mật khẩu tạm trên máy khác) bị thu hồi; phiên
    hiện tại giữ.

**Quản lý người dùng**
- [ ] Màn Quản lý người dùng hiện đúng các cột ở mục Expected Behavior 6. Ô tìm lọc theo email hoặc
      tên, không phân biệt hoa thường.
- [ ] Mọi người dùng đang đăng nhập đều vào được màn này (không phân quyền).
- [ ] Thêm người dùng:
  - Email phải đúng định dạng và chưa có trong hệ thống, kể cả khác hoa thường.
  - Tên dài 1–60 ký tự.
  - Mật khẩu tạm tối thiểu 8 ký tự.
  - Người mới có cờ "phải đổi mật khẩu" và trạng thái Hoạt động.
- [ ] Vô hiệu hoá (có hộp xác nhận):
  - Người đó không đăng nhập được nữa, và mọi phiên của họ hết hiệu lực ngay.
  - Thao tác trên dòng của họ chỉ còn "Kích hoạt lại".
- [ ] Không vô hiệu hoá được chính mình (dòng của mình không có nút này, và API cũng từ chối).
- [ ] Không vô hiệu hoá được người hoạt động cuối cùng, kể cả khi hai người vô hiệu hoá lẫn nhau cùng
      lúc: luôn còn ít nhất 1 người hoạt động.
- [ ] Kích hoạt lại (có hộp xác nhận) trả người đó về trạng thái Hoạt động. Mật khẩu và cờ "phải đổi
      mật khẩu" của họ giữ nguyên.
- [ ] Đặt mật khẩu tạm:
  - Mật khẩu mới tối thiểu 8 ký tự.
  - Người đó bị đăng xuất khỏi mọi thiết bị và mang cờ "phải đổi mật khẩu".
  - Không làm được trên người đang bị vô hiệu hoá.
- [ ] "Đăng xuất khỏi mọi thiết bị" thu hồi mọi phiên của người đó, và cột "Phiên hoạt động" về 0.
- [ ] Cột "Phiên hoạt động" chỉ đếm phiên còn hạn. "Đăng nhập gần nhất" được cập nhật mỗi lần đăng
      nhập thành công; người chưa đăng nhập lần nào thì cột hiện "Chưa đăng nhập".
- [ ] Mỗi người dùng lưu người tạo (người thêm trong app; để trống nếu tạo bằng CLI) và ngày tạo.
- [ ] Các trường hợp bị từ chối trả lỗi có mã và thông báo tiếng Việt cố định. Web hiện thông báo đó
      (ở form hoặc dạng thông báo nổi) và tải lại bảng:

      | Trường hợp | HTTP | Thông báo |
      |---|---|---|
      | Email đã có | 409 | "Email này đã có trong hệ thống" |
      | Email sai định dạng | 422 | "Email không hợp lệ" |
      | Tên rỗng hoặc quá 60 ký tự | 422 | "Tên phải từ 1 đến 60 ký tự" |
      | Mật khẩu dưới 8 ký tự | 422 | "Mật khẩu phải có ít nhất 8 ký tự" |
      | Tự vô hiệu hoá | 409 | "Không thể vô hiệu hoá chính mình" |
      | Vô hiệu hoá người hoạt động cuối (kể cả bên thua khi hai người cùng thao tác) | 409 | "Phải còn ít nhất một người dùng đang hoạt động" |
      | Đặt mật khẩu tạm cho người bị vô hiệu hoá | 409 | "Hãy kích hoạt lại người dùng trước" |
      | Sai mật khẩu hiện tại khi đổi từ menu | 400 | "Mật khẩu hiện tại không đúng" |

**Tài khoản của tôi**
- [ ] Đổi mật khẩu từ menu tài khoản:
  - Phải nhập đúng mật khẩu hiện tại.
  - Đổi xong thì các phiên khác của người đó bị thu hồi, phiên hiện tại vẫn dùng được.
- [ ] Sửa tên:
  - Tên được bỏ khoảng trắng hai đầu rồi mới kiểm tra độ dài 1–60 ký tự (cùng quy tắc khi thêm người
    dùng và trong CLI); tên rỗng hoặc chỉ có khoảng trắng thì báo lỗi.
  - Tên mới hiện ngay ở header và ở màn Quản lý người dùng.
- [ ] Ảnh đại diện là chữ cái đầu của từ cuối trong tên, viết hoa và giữ dấu: "Nguyễn Văn An" → "A",
      "Nguyễn Văn ánh" → "Á", "An" → "A".

**CLI**
- [ ] Lệnh CLI tạo người dùng (ví dụ `python -m reels_api create-user`) hỏi email và tên, rồi hỏi mật
      khẩu ẩn hai lần (`getpass`). Mật khẩu không được truyền qua tham số.
- [ ] CLI kiểm tra đầu vào theo đúng quy tắc của app: email đúng định dạng, tên 1–60 ký tự sau khi bỏ
      khoảng trắng, mật khẩu tối thiểu 8 ký tự. Nhập sai hoặc hai lần mật khẩu không khớp thì CLI báo
      lỗi tiếng Việt và hỏi lại mục đó.
- [ ] Email mới thì tạo người dùng với trạng thái Hoạt động, không có cờ "phải đổi mật khẩu".
- [ ] Email đã có:
  - CLI không hỏi tên mà hỏi xác nhận đặt lại.
  - Đồng ý thì đặt mật khẩu mới, kích hoạt lại, gỡ cờ "phải đổi mật khẩu", thu hồi mọi phiên và giữ
    tên cũ.
  - Từ chối thì không đổi gì và thoát với mã khác 0.
- [ ] Không có terminal (stdin không phải TTY) thì CLI báo lỗi tiếng Việt và thoát với mã khác 0,
      không treo.
- [ ] Mọi lỗi của CLI là thông báo tiếng Việt, không in traceback. CLI in được tiếng Việt khi chạy
      trong PowerShell hoặc cmd.

**Giao diện**
- [ ] Giao diện dùng Ant Design, màu chính `#0F3B4C`, giao diện và thông báo đều bằng tiếng Việt.
- [ ] Khung app khớp bản thiết kế đã chốt: menu trái, mục đang chọn, logo "RS", header có avatar, tên
      và menu tài khoản.
- [ ] Màn Video chỉ có khung trống "Chưa có video nào". Ba mục chưa làm mở trang "Sắp có".
- [ ] Ở chiều rộng 390px: menu trái thu gọn thành nút mở menu, bảng người dùng cuộn ngang, và trang
      không bị cuộn ngang.
- [ ] Khi api hoặc Postgres không chạy, web hiện thông báo lỗi kết nối bằng tiếng Việt, không trắng
      trang.

**Tài liệu dự án**
- [ ] Project Knowledge được cập nhật:
  - `architecture.md`: đăng nhập email + mật khẩu, phiên lưu trong Postgres, vô hiệu hoá thay cho
    xoá, cấu trúc `web/` + `api/`, Alembic.
  - `deployment.md`: biến môi trường đang dùng, bỏ `SESSION_SECRET`, lệnh CLI tạo và khôi phục người
    dùng, Docker Desktop.
  - `project.md`: không phân quyền; đăng nhập Google để spec sau.
- [ ] `backlog.md` có mục "Đăng nhập Google". Lý do: tiện cho đội. Điều kiện: cần tên miền HTTPS.

## Constraints

- **Stack:** Next.js (TypeScript), FastAPI (Python 3.12), Postgres; SQLAlchemy 2, Alembic, psycopg 3,
  pwdlib (Argon2), Ant Design, Playwright. Không dùng JWT cho phiên.
- **Chạy local:**
  - Máy dev Windows 10. Postgres chạy trong Docker (Docker Desktop + WSL2).
  - api và web chạy trực tiếp trên máy khi dev.
  - Chưa có Dockerfile cho web/api hay compose đầy đủ; phần đó làm trong spec deploy VPS.
- **Next.js:** không chạy được hai `next dev` cùng lúc trên một project, và rewrite được cố định lúc
  build. Vì vậy web cho E2E là một bản `next build` + `next start` riêng (thư mục build riêng, với
  `API_URL` của E2E có sẵn lúc build), chạy được cả khi server dev đang bật.
- **Chỉ localhost:** chưa hỗ trợ truy cập qua mạng LAN hay điện thoại thật.
- **Bảo mật:**
  - Secret và cấu hình chỉ nằm trong `.env` hoặc biến môi trường; `.env` không vào git.
  - Mật khẩu chỉ lưu bản hash; token phiên chỉ lưu bản hash.
  - Request thay đổi dữ liệu phải qua kiểm tra Origin.
- **Nền tảng:** đường dẫn repo có dấu cách (`C:\Users\Young Sheldon\...`), nên mọi script phải chạy
  được với đường dẫn có dấu cách. Next.js 16 cần Node ≥ 20.9; máy dev có Node 24.
- **Ngôn ngữ:** giao diện chỉ tiếng Việt, không có i18n.
- **Phạm vi:**
  - Chưa nối với `worker/`.
  - Chưa có bảng Video và các màn MVP khác.
  - Chưa có đăng nhập Google, phân quyền, tự đăng ký, gửi email, hay giới hạn số lần đăng nhập sai.

## Risks

- **Rủi ro: Docker Desktop và WSL2 chưa có trên máy dev.** Không có chúng thì api không chạy được và
  test không chạy được.
  **Giảm thiểu:**
  - WSL2 và Docker Desktop đã được cài ngày 2026-10-29; cần khởi động lại máy.
  - README ghi bước cài.
  - Test cần Postgres sẽ được bỏ qua (skip) kèm lý do khi không kết nối được database.
- **Rủi ro: thu hồi phiên không có tác dụng ngay** (vô hiệu hoá, đặt mật khẩu tạm, đổi mật khẩu,
  đăng xuất mọi thiết bị).
  **Giảm thiểu:** phiên lưu trong Postgres và được kiểm tra ở mỗi request; có test cho từng thao tác.
- **Rủi ro: CSRF qua rewrite của Next.js.**
  **Giảm thiểu:** api kiểm tra Origin cho mọi request thay đổi dữ liệu; cookie dùng `SameSite=Lax`.
- **Rủi ro: chỉ chặn ở giao diện**, khiến phiên đang phải đổi mật khẩu vẫn gọi trực tiếp được các API
  khác.
  **Giảm thiểu:** chặn ngay trong api (trả 403 `password_change_required`), có test.
- **Rủi ro: test xoá hoặc ghi đè dữ liệu dev.**
  **Giảm thiểu:** pytest dùng `reels_test`; E2E dùng `reels_e2e` với api và web riêng ở cổng
  8100/3100 và không dùng lại server dev.
- **Rủi ro: `node_modules/` cũ (Remotion) ở gốc repo bị web nạp nhầm.**
  **Giảm thiểu:** dọn thư mục đó hoặc chặn việc tìm module ở thư mục cha, có tiêu chí nghiệm thu.
- **Rủi ro: dò mật khẩu bằng cách thử nhiều lần**, vì không giới hạn số lần đăng nhập sai.
  **Giảm thiểu:** chấp nhận khi app chỉ chạy trên localhost; thêm giới hạn khi lên VPS. Thông báo lỗi
  chung không lộ email nào có trong hệ thống.

## Accepted Decisions

- **Chỉ email + mật khẩu.**
  - Ban đầu người dùng muốn đăng nhập bằng Gmail, sau đó chọn "Google + mật khẩu dự phòng".
  - Khi bàn chi tiết thì chốt "Tạm thời mail và pass đã". Google cần OAuth client, và Google không
    chấp nhận địa chỉ quay về là IP nội bộ, nên được để sang spec sau, khi có tên miền HTTPS.
- **Chỉ localhost.** Truy cập qua mạng LAN hay điện thoại thật được hoãn tới khi có VPS.
- **Không phân quyền.** Ảnh MKT-Tools có vai trò Quản trị viên / Thành viên, nhưng người dùng chọn
  giữ đúng `project.md` (MVP không có vai trò). Vì vậy ai cũng quản lý được người dùng.
- **Vô hiệu hoá thay cho xoá, và kích hoạt lại được.** Giữ lại tài khoản để sau này video vẫn biết ai
  tạo.
- **Mật khẩu tạm do người tạo tự gõ.** Người dùng chọn cách này thay vì để app tự sinh hay gửi email.
- **Tên nhập khi thêm người dùng; ảnh đại diện là chữ cái đầu của từ cuối trong tên.** Không có ảnh
  từ Google, và không cho tải ảnh lên. Lấy từ cuối vì nhiều người cùng họ Nguyễn.
- **Bắt buộc đổi mật khẩu sau khi đăng nhập bằng mật khẩu tạm.** Màn bắt buộc không hỏi mật khẩu cũ;
  đổi từ menu tài khoản thì có hỏi.
- **Phiên lưu trong Postgres, cookie 30 ngày, gia hạn khi dùng.**
  - Chọn cách này vì vô hiệu hoá và đăng xuất mọi thiết bị phải có tác dụng ngay, điều mà JWT không
    làm được.
  - Không cần `SESSION_SECRET`.
- **Chỉ hiện số phiên và nút "Đăng xuất khỏi mọi thiết bị"**, không liệt kê từng thiết bị.
- **Người bị vô hiệu hoá chỉ có thao tác "Kích hoạt lại".**
- **CLI vừa để tạo người dùng đầu tiên vừa là đường khôi phục.** Với email đã có, CLI đặt lại mật
  khẩu, kích hoạt lại, giữ tên và gỡ cờ "phải đổi mật khẩu".
- **"Tài khoản đã bị vô hiệu hoá" chỉ hiện khi mật khẩu đúng.** Các trường hợp khác dùng thông báo
  chung, để người ngoài không dò được email nào có trong hệ thống.
- **Không giới hạn số lần đăng nhập sai** (người dùng chọn), chấp nhận khi chỉ chạy local.
- **Dùng Ant Design** vì giao diện MKT-Tools của người dùng là kiểu Ant Design.
- **Postgres chạy trong Docker; api và web chạy trực tiếp khi dev** để sửa code là thấy ngay.
- **Không làm Dockerfile web/api và compose đầy đủ ở phần này.** Ban đầu định có, nhưng image chỉ
  được build mà không chạy hay kiểm chứng, và spec VPS sau có thể phải làm lại. Người dùng chọn để
  sang spec deploy VPS.
- **Màn Video chỉ có khung trống.** Nút tạo video để spec sau, vì cần bảng Video và Claude.
- **Các mục menu chưa làm vẫn hiện**, mở ra trang "Sắp có".
- **Next.js gọi api qua rewrite `/api`** để cookie cùng trang và không cần CORS.
- **Chặn vô hiệu hoá người hoạt động cuối bằng khoá dòng trong transaction**, để đúng cả khi hai
  người thao tác cùng lúc.

## Testing

**Unit tests:** cần cho các phần logic thuần, chạy bằng pytest:
- Chuẩn hoá và kiểm tra email; kiểm tra tên (1–60 ký tự).
- Quy tắc mật khẩu (≥ 8 ký tự).
- Lấy chữ cái avatar: "Nguyễn Văn An" → "A"; tên một từ; tên có dấu.
- Đọc cấu hình từ `.env` và biến môi trường (biến thật ưu tiên hơn `.env`).

**Integration tests:** cần, vì gần như mọi hành vi đều nằm ở ranh giới API ↔ Postgres.
- Chạy bằng pytest + TestClient trên Postgres thật, database `reels_test`. Mỗi test chạy trong một
  transaction rồi rollback.
- Cover:
  - Đăng nhập: đúng; sai; email lạ; tài khoản bị vô hiệu hoá với mật khẩu đúng và mật khẩu sai.
  - Cookie và phiên: thuộc tính cookie; hết hạn sau 30 ngày; gia hạn khi dùng; 401 khi phiên hết hạn
    hoặc bị thu hồi.
  - Bắt buộc đổi mật khẩu: `/api/me` được gọi, mọi API khác trả 403 `password_change_required`, đổi
    xong thì gỡ cờ.
  - Đổi mật khẩu từ menu: sai mật khẩu hiện tại; thu hồi các phiên khác.
  - Thêm người dùng: email trùng (kể cả khác hoa thường); email sai định dạng; tên rỗng hoặc quá dài.
  - Vô hiệu hoá: thu hồi phiên; không vô hiệu hoá được chính mình hay người hoạt động cuối.
  - Kích hoạt lại; đặt mật khẩu tạm (thu hồi phiên, bật cờ, bị từ chối với người đang vô hiệu hoá);
    đăng xuất mọi thiết bị; đếm phiên còn hạn; cập nhật "Đăng nhập gần nhất".
  - Kiểm tra Origin.
  - Mật khẩu không xuất hiện trong phản hồi API, và không xuất hiện trong log của api (bắt log bằng
    `caplog` trong các test đăng nhập, thêm người dùng, đặt mật khẩu tạm, đổi mật khẩu).
  - Mã HTTP và thông báo của từng trường hợp bị từ chối trong bảng ở mục "Quản lý người dùng".
  - Sửa tên: hợp lệ; rỗng; chỉ có khoảng trắng; quá 60 ký tự.
  - CLI:
    - Tạo mới; email đã có khi đồng ý và khi từ chối; không có terminal.
    - Email sai, tên rỗng, mật khẩu ngắn, hai lần nhập không khớp thì báo lỗi và hỏi lại.
    - Chạy CLI như một tiến trình con với stdout là pipe: thông báo tiếng Việt in đúng, không có
      traceback.
- Riêng trường hợp hai người vô hiệu hoá lẫn nhau cùng lúc: một test dùng hai kết nối thật, dữ liệu
  được commit vào `reels_test` và dọn sau test. Test kiểm tra chỉ một thao tác thành công và luôn còn
  ít nhất 1 người hoạt động.
- Khi không kết nối được Postgres, các test cần database bị bỏ qua (skip) kèm lý do tiếng Việt.

**E2E tests:** cần, vì người dùng yêu cầu kiểm thử đăng nhập trên trình duyệt thật.
- Chạy bằng Playwright với database `reels_e2e` và api/web riêng ở cổng 8100/3100
  (`API_URL=http://localhost:8100`, `ALLOWED_ORIGINS=http://localhost:3100`). Web E2E là bản
  `next build` vào thư mục build riêng rồi `next start`, nên chạy được cả khi server dev đang bật.
  Seed và dọn dữ liệu mỗi lần chạy.
- Cover:
  - Đăng nhập và đăng xuất; chưa đăng nhập thì bị chuyển về trang đăng nhập.
  - Người mới thêm đăng nhập bằng mật khẩu tạm rồi bị bắt đổi mật khẩu.
  - Thêm người dùng, vô hiệu hoá, kích hoạt lại, đặt mật khẩu tạm, đăng xuất mọi thiết bị.
  - Đổi mật khẩu và sửa tên từ menu tài khoản.
  - Trang "Sắp có".
  - Cỡ màn 390px: menu thu gọn, trang không bị cuộn ngang.
  - Thông báo lỗi khi api không chạy. Trường hợp api còn chạy nhưng Postgres dừng được kiểm ở
    integration test: api trả 503 với thông báo lỗi kết nối, và web hiện đúng thông báo đó (kiểm bằng
    E2E giả lập phản hồi 503 của api).

## Verification

### Agent Verification

| Step | Expected Result |
|------|-----------------|
| 1. Xoá volume Postgres cũ (nếu có), `docker compose up -d postgres`, rồi chạy `alembic upgrade head` trên database dev | Postgres chạy; có đủ ba database (dev, `reels_test`, `reels_e2e`); database dev có đủ bảng |
| 2. Chạy pytest trong `api/` | Toàn bộ test pass, không có test nào bị skip vì thiếu database |
| 3. Bật server dev (`next dev` cổng 3000), rồi chạy Playwright E2E trong `web/` | Toàn bộ test pass trên `reels_e2e`; database dev không bị đổi |
| 4. Đổi tên tạm `node_modules/` ở gốc repo (nếu còn), chạy build web và E2E, rồi trả lại tên cũ | Build và E2E vẫn pass |
| 5. Chạy lệnh CLI tạo người dùng đầu tiên trong PowerShell, bật api và web, đăng nhập ở `http://localhost:3000` | CLI in tiếng Việt đúng; vào được màn Video; header hiện tên và chữ cái avatar |
| 6. Chạy lại lệnh CLI với cùng email và trả lời "không" | Thoát với mã khác 0; dữ liệu không đổi |
| 7. Chụp màn Đăng nhập, Video, Quản lý người dùng ở cỡ 1440px và 390px | Có ảnh để người dùng đối chiếu với bản thiết kế |

### User Verification
- **Xem giao diện thật** so với bản thiết kế đã chốt và ảnh MKT-Tools: màu sắc, menu, bảng quản lý
  người dùng. Agent không tự đánh giá được giao diện có đúng ý người dùng hay không.
- **Tự bấm thử các luồng:** thêm một đồng đội, đăng nhập bằng mật khẩu tạm trong cửa sổ ẩn danh, đổi
  mật khẩu, rồi vô hiệu hoá người đó và xem phiên của họ bị đăng xuất.
- **Thử cỡ điện thoại** bằng chế độ thiết bị của trình duyệt (F12): menu thu gọn, bảng cuộn ngang.
