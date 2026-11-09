-- ════════════════════════════════════════════════════════════════════════
-- 005 — Mã đặt lại mật khẩu, thành bảng riêng
--
-- Luồng "Quên mật khẩu" (FC03, API 7.1.5–7.1.6) có một nghịch lý: để đổi
-- mật khẩu thì phải chứng minh mình là chủ tài khoản, mà bằng chứng duy
-- nhất hệ thống có — chính mật khẩu — thì người dùng không nhớ. Nên hệ
-- thống tạm thay nó bằng một bằng chứng khác: quyền đọc hộp thư đã đăng ký.
-- Mã đặt lại là bằng chứng đó, và bảng này là nơi nó sống.
--
-- ## Vì sao một bảng, không phải bốn cột trong `users`
--
-- Một mã gồm bốn thứ: mã đã băm, thuộc về ai, hết hạn lúc nào, đã dùng
-- chưa. Nhồi vào `users` thì:
--
--   · Mỗi người CHỈ CÓ MỘT mã sống được. Email đến chậm nên người ta bấm
--     "Gửi lại" là chuyện thường, và lúc đó mã trong email thứ nhất chết
--     — trong khi đó mới là email họ đang mở.
--   · Bốn cột ấy RỖNG với gần như mọi dòng. Tại một thời điểm chỉ vài
--     người đang đặt lại mật khẩu trong số hàng trăm tài khoản.
--   · Không có lịch sử. Một tài khoản bị xin mã 50 lần trong một phút là
--     dấu hiệu bị dò, mà cột bị ghi đè thì không nhìn thấy điều đó.
--
-- ## Lưu mã ĐÃ BĂM, không lưu mã gốc
--
-- Lý do giống hệt chỗ `users.password_hash`: ai đọc được bảng này mà mã
-- nằm nguyên trong đó thì đổi được mật khẩu của mọi tài khoản đang có mã
-- sống. Băm thì bảng đó vô dụng với họ. Backend băm mã bằng SHA-256 rồi
-- tra theo `token_hash`; không có truy vấn nào cần mã gốc, vì người dùng
-- luôn nộp lại nó từ liên kết trong email.
--
-- SHA-256 chứ không phải BCrypt, có chủ ý. BCrypt cố ý chậm để chống dò
-- mật khẩu do người đặt — thứ có entropy thấp. Mã ở đây là 32 byte ngẫu
-- nhiên, không dò được bằng từ điển, nên cái chậm đó chỉ còn là chi phí.
--
-- ## Mã PHẢI sinh bằng bộ sinh số ngẫu nhiên mật mã
--
-- Cột `id` dưới đây dùng `UUID()` của MySQL, và điều đó CHỈ đúng cho một
-- khóa chính. `UUID()` sinh UUID phiên bản 1 — ghép từ thời điểm và địa
-- chỉ MAC của máy chủ, nên đoán được. Dùng nó làm mã đặt lại thì ai biết
-- thời điểm gửi email là thu hẹp được không gian tìm kiếm xuống còn vài
-- nghìn khả năng. Backend phải sinh mã bằng `SecureRandom` (32 byte),
-- không bao giờ bằng `UUID()` của CSDL.
--
-- Chạy:
--     python tools/run_sql.py db/migrations/005_password_resets.sql \
--            --database nutrition_rec
-- ════════════════════════════════════════════════════════════════════════

USE nutrition_rec;

CREATE TABLE password_resets (
    id          CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id     CHAR(36) NOT NULL,

    -- SHA-256 ở dạng hex: luôn đúng 64 ký tự, nên CHAR chứ không VARCHAR.
    -- UNIQUE vừa là ràng buộc vừa là chỉ mục để tra khi người dùng nộp mã.
    token_hash  CHAR(64) NOT NULL,

    expires_at  DATETIME NOT NULL,

    -- NULL = chưa dùng. Dùng rồi thì ghi thời điểm chứ không xóa dòng:
    -- một mã bị dùng hai lần là dấu hiệu liên kết đã rò ra ngoài, và xóa
    -- dòng đi thì lần thứ hai không phân biệt được với mã bịa.
    used_at     DATETIME NULL,

    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_reset_window CHECK (expires_at > created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    UNIQUE KEY uq_reset_token (token_hash),

    -- Đếm số lần xin mã gần đây của một tài khoản, cho mức 429 RATE_LIMITED
    -- ở 7.1.5. Thứ tự (user_id, created_at) để lọc theo người rồi quét
    -- khoảng thời gian liền nhau.
    --
    -- Giới hạn này CHỈ che được email đã đăng ký. Email không có trong hệ
    -- thống không sinh dòng nào — cố ý, vì lưu lại mọi địa chỉ người lạ
    -- nhập vào là tự dựng một danh sách email mà hệ thống không cần. Nên
    -- phép giới hạn cho nhóm đó phải đặt ở tầng trước CSDL, theo địa chỉ IP.
    INDEX idx_reset_user_time (user_id, created_at)
) ENGINE=InnoDB;
