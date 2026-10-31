# Prompt giao Claude Code: sửa lỗi lint ở StockPicker.tsx

> Cấu hình chạy: model Sonnet 5.5, effort medium. Chỉ nâng high khi bí cùng một lỗi 2–3 vòng.
> TUYỆT ĐỐI không dùng subagent. Không commit — owner tự commit.

## Việc cần làm

File `web/src/components/video/StockPicker.tsx` đang làm `npm run lint` (trong thư mục `web/`) thất bại
với lỗi của eslint-plugin-react-hooks — `react-hooks/set-state-in-effect`, và ở một biến thể trước còn có
`react-hooks/preserve-manual-memoization`. Hãy sửa cấu trúc code trong file này cho tới khi cả hai lệnh sau đều xanh:

```bash
cd web && npm run lint && npm run typecheck
```

## Bối cảnh (đã kiểm chứng, đừng làm lại)

- Toàn bộ phần còn lại của đợt việc này đã xong và xanh: khôi phục `keywords`/`title_keywords` vào
  `OUTPUT_FORMAT` của api, thêm 2 nguồn ảnh Pexels + Openverse (api + web). Pytest api: **490 passed**.
  Không đụng vào backend, không đụng vào file nào khác ngoài `StockPicker.tsx` (trừ khi lint/typecheck
  chỉ rõ lỗi nằm ở file khác do đợt việc này gây ra — khi đó báo cáo thay vì tự sửa lan).
- StockPicker là hộp thoại chọn ảnh stock cho cảnh: mở ra thì gọi `GET /stock/sources` lấy danh sách
  nguồn đang bật, chọn nguồn mặc định (Pixabay nếu có, không thì nguồn đầu tiên), rồi tìm ngay từ khóa
  đầu tiên của cảnh ở nguồn đó. Người dùng chuyển nguồn thì tìm lại cùng từ khóa. Hành vi này phải giữ
  nguyên từng chi tiết, gồm: chống đua bằng ref `latest`, trạng thái loading/error, các `data-testid`
  (`stock-hit`, `picker-error`, `picker-hint`), nhãn "Chọn từ kho ảnh" / "Từ khóa tìm ảnh" / "Nguồn ảnh".
  E2E `web/e2e/videos.spec.ts` đang dựa vào các nhãn và testid này.

## Đã thử và vẫn đỏ (đừng lặp lại nguyên xi)

1. `useEffectEvent` bất đồng bộ chứa setState, effect gọi nó → bị flag ngay tại dòng gọi trong effect.
2. `useEffectEvent` đồng bộ gọi một hàm async thường chứa setState → vẫn bị flag tại dòng gọi event.
3. Cả `load` lẫn `start` cùng bọc `useCallback` → `start` vẫn bị flag trong effect, thêm lỗi
   `preserve-manual-memoization` ở `load`.
4. Hiện trạng trong file (bản mới nhất): chỉ `start` là `useCallback` chứa mọi setState sau await,
   `load` là hàm async thường chỉ gọi từ sự kiện người dùng, phần fetch tách thành `fetchHits` ở mức
   module — cấu trúc này mô phỏng trang jobs nhưng **vẫn lỗi** (owner vừa chạy lại, chưa rõ cùng lỗi cũ
   hay lỗi mới — hãy tự chạy lint để thấy lỗi hiện tại trước khi sửa).

Trang `web/src/app/(app)/jobs/page.tsx` có hàm `reload` bọc `useCallback` được effect gọi `void reload()`
và đang xanh — hãy tự tìm điểm khác biệt thật sự khiến analyzer xử lý hai nơi khác nhau, thay vì đoán.

## Ràng buộc

- Không tắt rule, không nới cấu hình eslint. Không dùng `eslint-disable` — trừ khi đã thử hết cách cấu trúc
  mà vẫn không qua; khi đó chỉ được disable đúng 1 dòng kèm comment giải thích, và phải nêu rõ trong báo cáo.
- Không đổi hành vi, không đổi nhãn/testid, không đổi API. Không sửa E2E để né lỗi.
- Sau lint + typecheck xanh, chạy thêm E2E của file videos nếu môi trường local đang sẵn (api + fakes):
  chỉ cần xác nhận 2 test picker ("photos from the stock picker..." và "photos from Pexels and Openverse...")
  không vỡ vì thay đổi cấu trúc; nếu môi trường không sẵn thì ghi rõ "chưa chạy E2E" trong báo cáo.

## Báo cáo (theo đúng quy tắc repo, 3 phần)

1. **Đã làm**: cấu trúc cuối cùng là gì, vì sao analyzer chấp nhận (nói rõ điểm khác biệt với trang jobs nếu tìm ra).
2. **Đã kiểm chứng**: dán kết quả thật của `npm run lint`, `npm run typecheck` (và E2E nếu chạy được).
3. **Rủi ro còn lại**: có dùng eslint-disable hay không; hành vi nào chưa được kiểm chứng.
