# Phase 12 — Kiểm thử toàn hệ thống và đo hiệu năng

Trạng thái: **ĐẠT với các giới hạn đã công bố** trên máy người dùng ngày 26/10/2026 (UTC+7). Kết luận dựa trên bằng chứng thực chạy được người dùng cung cấp; trợ lý không tự chạy Docker trên máy Windows.

- [Đối soát](reconciliation.md)
- [Recovery](recovery.md)
- [Hiệu năng](performance.md)
- [Hạn chế và các lần lỗi đã khắc phục](limitations.md)
- `release.json`: chỉ mục SHA-256 và đường dẫn gốc của 53 tệp bằng chứng.
- `evidence/`: bản sao nguyên byte, gồm cả lần đo thất bại; chỉ run được chỉ định trong release.json được dùng cho kết luận đạt.

Kiểm tra bản lưu: `python scripts/verify_phase12.py --target .`

Bộ kiểm thử tái sử dụng: `src.cdc.checks`, `src.quality`, `src.marts.checks`, `src.mining.verify`, `src.delivery.store.verify`, `src.inference.checks`, `src.dashboard.checks` và `tests/`. Harness đo được lưu tại `scripts/phase12/`; chạy lại tạo cửa sổ bằng chứng mới, không thay bằng chứng đã chấp nhận. Không cần chạy lại để cài báo cáo.

Phase 13 tiếp theo: đóng gói, khóa phiên bản, tài liệu vận hành/bảo vệ và dựng lại trong môi trường riêng. Chưa có bằng chứng dựng lại sạch ở Phase 12.
