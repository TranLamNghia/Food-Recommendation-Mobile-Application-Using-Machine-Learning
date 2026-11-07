/// Mức tin cậy của một ngưỡng dinh dưỡng — cột
/// `condition_rules.evidence_level`.
///
/// Tồn tại vì một ứng dụng sức khỏe dẫn khuyến cáo của WHO và một con số
/// chưa ai tra bằng **cùng một giọng** là không trung thực. Trước đây xuất
/// xứ của mọi ngưỡng nằm trong văn xuôi cột `note`, nên muốn phân loại phải
/// tìm chuỗi "chưa xác minh" trong câu chữ — hỏng ngay lần đầu ai sửa lời.
///
/// Bốn mức, không phải ba: xem [definitional].
enum EvidenceLevel {
  /// Quy tắc **LÀ** định nghĩa, không có ngưỡng nào để dẫn nguồn.
  ///
  /// "Dị ứng trứng thì loại món có trứng" không cần tổ chức nào công bố.
  /// Mọi quy tắc nhãn thuộc nhóm này — 9 trong 20 quy tắc. Nhồi chúng vào
  /// [published] sẽ thành khẳng định rằng có ai đó công bố điều hiển nhiên.
  definitional('definitional', 'quy tắc định nghĩa'),

  /// Con số lấy nguyên từ một nguồn **đang hiệu lực**.
  ///
  /// WHO: natri dưới 2 000 mg/ngày. Hướng dẫn gút Nhật Bản: purin dưới
  /// 400 mg/ngày. Đây là mức duy nhất được dẫn như khuyến cáo có nguồn.
  published('published', 'có nguồn công bố'),

  /// Nguồn có thật nhưng con số là **phép suy ra**, nên nó chỉ đúng kèm
  /// giả thiết đi theo.
  ///
  /// 48 g đạm của KDIGO đúng cho người 60 kg, không đúng cho người 90 kg;
  /// 25 g đường là 5 % của khẩu phần 2 000 kcal; chất béo tổng được dùng
  /// thay cho béo bão hòa vì bảng thành phần không tách.
  derived('derived', 'suy ra kèm giả thiết'),

  /// Không có nguồn **đang hiệu lực**.
  ///
  /// Hai tình huống khác nhau cùng rơi vào đây, và `note` phân biệt chúng:
  /// ngưỡng cholesterol 300 mg/ngày đã **bị rút** khỏi Dietary Guidelines
  /// 2015 và AHA/ACC 2019; ngưỡng natri 500 mg cho mức nặng thì **chưa**
  /// ai tra. Về mặt trình bày hai thứ như nhau — đều không được dẫn như
  /// khuyến cáo.
  unsupported('unsupported', 'không có nguồn đang hiệu lực');

  const EvidenceLevel(this.code, this.label);

  /// Giá trị trong CSDL.
  final String code;

  /// Câu ngắn cho giao diện.
  final String label;

  /// Ngưỡng này có được dẫn như khuyến cáo có nguồn hay không.
  ///
  /// Chỉ [published]. [derived] kèm giả thiết nên không, [unsupported] thì
  /// không có nguồn nào, và [definitional] không có ngưỡng nào để dẫn.
  bool get canCite => this == EvidenceLevel.published;

  /// Đọc từ mã trong CSDL.
  ///
  /// Mã lạ trả về [derived] — mức **không** dẫn được nguồn. Trả về
  /// [published] khi không nhận ra mã sẽ khiến một giá trị lỗi tự nhận là
  /// có nguồn, đúng kiểu hỏng cần tránh nhất ở đây.
  static EvidenceLevel fromCode(String? code) => switch (code) {
    'definitional' => EvidenceLevel.definitional,
    'published' => EvidenceLevel.published,
    'unsupported' => EvidenceLevel.unsupported,
    _ => EvidenceLevel.derived,
  };
}
