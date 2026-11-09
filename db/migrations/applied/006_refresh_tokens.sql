-- ════════════════════════════════════════════════════════════════════════
-- 006 — Chỗ lưu refreshToken, thiếu từ đầu
--
-- Đặc tả API 7.1.3 hứa hai điều mà không bảng nào đỡ được:
--
--   · **Xoay vòng**: mỗi lần làm mới trả token mới và THU HỒI token cũ.
--   · 7.1.7: đổi mật khẩu thì thu hồi MỌI refreshToken của tài khoản đó.
--
-- Cả hai đòi trạng thái phía máy chủ. Một JWT tự chứa thì không thu hồi
-- được — nó hợp lệ cho tới lúc hết hạn, nên "đổi mật khẩu vì nghi có người
-- khác đang truy cập" sẽ không cắt được phiên của người đó trong 30 ngày.
-- Đó đúng là tình huống duy nhất mà người ta đổi mật khẩu.
--
-- ## Vì sao có `replaced_by`, không chỉ `revoked_at`
--
-- Xoay vòng mà không phát hiện tái dùng thì không thêm an toàn nào: kẻ lấy
-- được token cứ dùng, hệ thống cứ cấp token mới, không ai biết.
--
-- `replaced_by` nối thành chuỗi: token A -> B -> C. Khi một token ĐÃ THU HỒI
-- được nộp lại, chỉ có hai khả năng — người dùng thật mất mạng giữa lúc xoay
-- vòng, hoặc token đã rò ra ngoài. Không phân biệt được hai cái, nên xử lý
-- theo hướng an toàn: lần theo chuỗi và thu hồi CẢ HỌ, buộc đăng nhập lại.
-- Đây là cách làm chuẩn của refresh token rotation with reuse detection.
--
-- ## Lưu mã đã băm, như `password_resets`
--
-- Cùng một lý do: ai đọc được bảng này mà token nằm nguyên trong đó thì mạo
-- danh được mọi phiên đang sống. SHA-256 vì token là UUID do máy chủ sinh,
-- không phải mật khẩu người đặt — không dò được bằng từ điển.
--
-- Chạy:
--     python tools/run_sql.py db/migrations/006_refresh_tokens.sql \
--            --database nutrition_rec
-- ════════════════════════════════════════════════════════════════════════

USE nutrition_rec;

CREATE TABLE refresh_tokens (
    id          CHAR(36) DEFAULT (UUID()) PRIMARY KEY,
    user_id     CHAR(36) NOT NULL,

    -- SHA-256 hex của token gốc. Token gốc chỉ tồn tại trong phản hồi HTTP
    -- và trong máy người dùng, không bao giờ nằm trong CSDL.
    token_hash  CHAR(64) NOT NULL,

    expires_at  DATETIME NOT NULL,

    -- NULL = còn sống. Thu hồi thì ghi thời điểm, KHÔNG xóa dòng: một token
    -- đã thu hồi được nộp lại là tín hiệu rò rỉ, và xóa dòng đi thì lần nộp
    -- đó không phân biệt được với một token bịa.
    revoked_at  DATETIME NULL,

    -- Token đã thay thế token này khi xoay vòng. Lần theo cột này để thu hồi
    -- cả họ khi phát hiện tái dùng.
    replaced_by CHAR(36) NULL,

    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_refresh_window CHECK (expires_at > created_at),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,

    -- ON DELETE SET NULL, không CASCADE: dọn một token hết hạn ở giữa chuỗi
    -- không được kéo theo token đang sống ở cuối chuỗi.
    FOREIGN KEY (replaced_by) REFERENCES refresh_tokens(id) ON DELETE SET NULL,

    UNIQUE KEY uq_refresh_token (token_hash),

    -- Thu hồi mọi token của một người (7.1.7), và liệt kê phiên đang sống.
    INDEX idx_refresh_user (user_id, revoked_at, expires_at)
) ENGINE=InnoDB;
