# -*- coding: utf-8 -*-
"""Nội dung phần Tóm tắt, Nhiệm vụ đồ án, Mở đầu và các mục 1.1 – 1.3.

Tách khỏi build_noidung.py để sửa chữ không phải đụng tới phần dựng XML.

Mỗi khối là một danh sách phần tử, mỗi phần tử là một cặp (kiểu, nội dung):

    ("h2", "…")      mục cấp 2, Word tự đánh số 1.x
    ("h3", "…")      mục cấp 3, Word tự đánh số 1.x.y
    ("md", "…")      mục Mở đầu, style Mu, Word tự đánh số 1. 2. 3.
    ("mda", "…")     mục con a. b. trong Mở đầu, style Mca
    ("p", "…")       đoạn văn thường
    ("b", "…")       đoạn văn in đậm, dùng làm nhãn nhóm
    ("ul", [...])    danh sách gạch đầu dòng, style NormalBullet
    ("bang", {...})  bảng, xem build_noidung.py

Số liệu trong đây lấy từ chính hệ thống đã dựng (cơ sở dữ liệu 22 bảng,
318 món, 13 bệnh lý, 20 quy tắc lọc), không phải con số ước chừng.
"""

TEN_DE_TAI = ("Ứng dụng di động khuyến nghị thực đơn dinh dưỡng cá nhân hóa "
              "sử dụng học máy dựa trên lịch sử người dùng và mục tiêu sức "
              "khỏe")

# ── TÓM TẮT ───────────────────────────────────────────────────────────────
TOM_TAT = [
    # Ba dòng định danh thay cho nhãn "Nội dung tóm tắt" của biểu mẫu,
    # theo bản đã soạn trong Word.
    ("p", f"Tên đề tài: {TEN_DE_TAI}"),
    ("p", "Sinh viên thực hiện: Trần Lâm Nghĩa"),
    ("p2", "Mã SV: 22115053122231 	Lớp: 22T2"),
    ("p",
     f"Đề tài “{TEN_DE_TAI}” xây dựng một ứng dụng di động sinh thực đơn cho "
     "từng ngày, phù hợp với thể trạng, bệnh lý và khẩu vị của riêng từng "
     "người dùng. Đề tài xuất phát từ một khoảng trống thực tế: phần lớn ứng "
     "dụng dinh dưỡng phổ biến hiện nay dừng lại ở việc ghi chép và đếm năng "
     "lượng, còn câu hỏi “hôm nay nên ăn gì” vẫn do người dùng tự trả lời."),
    ("p",
     "Hệ thống được xây dựng theo mô hình client – server. Ứng dụng di động "
     "đa nền tảng viết bằng Flutter, dịch vụ phía máy chủ dạng RESTful viết "
     "bằng ASP.NET Core, dữ liệu lưu trên hệ quản trị cơ sở dữ liệu MySQL, "
     "model khuyến nghị cài đặt bằng Python với thư viện scikit-learn."),
    ("p",
     "Thuật toán khuyến nghị gồm bốn bước. Bước một tính hạn mức năng lượng "
     "và các ràng buộc dinh dưỡng của người dùng từ chỉ số khối cơ thể, công "
     "thức Mifflin-St Jeor và tổng năng lượng tiêu hao. Bước hai loại khỏi "
     "danh mục những món không an toàn với bệnh lý và dị ứng đã khai. Bước "
     "ba xếp hạng các món còn lại theo độ tương đồng cosin giữa vector đặc "
     "trưng món ăn hai mươi chiều và vector sở thích của người dùng. Bước "
     "bốn ghép các món đã xếp hạng thành thực đơn một ngày sao cho tổng năng "
     "lượng lệch không quá 10 % so với hạn mức và các ngưỡng vi chất tính "
     "theo ngày đều được tôn trọng."),
    ("p",
     "Kết quả đạt được gồm: một cơ sở dữ liệu quan hệ 22 bảng; tập dữ liệu "
     "318 món ăn Việt Nam có thành phần dinh dưỡng quy đổi từ Bảng thành "
     "phần thực phẩm Việt Nam của Viện Dinh dưỡng – Bộ Y tế; bộ quy tắc lọc "
     "gồm 13 bệnh lý và chế độ ăn cùng 20 quy tắc dinh dưỡng, mỗi quy tắc "
     "đều dẫn nguồn khuyến nghị y khoa; và ứng dụng di động hiện thực luồng "
     "khai báo hồ sơ sức khỏe, khảo sát khẩu vị và xem thực đơn ngày."),
    ("p",
     "Hệ thống có khả năng mở rộng: khi lịch sử tương tác của người dùng đủ "
     "lớn, mô hình khuyến nghị chuyển dần từ lọc theo nội dung sang mô hình "
     "học máy có giám sát."),
]

# ── NHIỆM VỤ ĐỒ ÁN TỐT NGHIỆP ─────────────────────────────────────────────
NHIEM_VU = [
    ("p2", "Giảng viên hướng dẫn: ThS. Nguyễn Tấn Thuận"),
    ("p2", "Sinh viên thực hiện: Trần Lâm Nghĩa\tMã SV: 22115053122231"),
    ("b", "1. Tên đề tài"),
    ("p", TEN_DE_TAI),
    ("b", "2. Các số liệu, tài liệu ban đầu"),
    ("ul", [
        "Viện Dinh dưỡng Quốc gia – Bộ Y tế (2007), Bảng thành phần thực "
        "phẩm Việt Nam, NXB Y học, Hà Nội — số liệu năng lượng và thành phần "
        "dinh dưỡng của nguyên liệu dùng để tính cho từng món ăn.",
        "Viện Dinh dưỡng Quốc gia (2016), Nhu cầu dinh dưỡng khuyến nghị cho "
        "người Việt Nam — nhu cầu khuyến nghị theo giới tính và nhóm tuổi.",
        "Mifflin M.D., St Jeor S.T. và cộng sự (1990), “A new predictive "
        "equation for resting energy expenditure in healthy individuals” — "
        "công thức tính chuyển hóa cơ bản.",
        "WHO Expert Consultation (2004), “Appropriate body-mass index for "
        "Asian populations” — ngưỡng phân loại thể trạng cho người châu Á.",
        "Manning C.D., Raghavan P., Schütze H. (2008), Introduction to "
        "Information Retrieval — mô hình không gian vector, độ đo cô-sin và "
        "thuật toán Rocchio.",
        "Tài liệu chính thức của Flutter, ASP.NET Core, MySQL 8.0 và "
        "scikit-learn — nền tảng triển khai hệ thống.",
    ]),
    ("b", "3. Nội dung chính của đồ án"),
    ("ul", [
        "Mở đầu;",
        "Chương 1: Cơ sở lý thuyết — lý thuyết dinh dưỡng và các chỉ số thể "
        "trạng, hệ khuyến nghị theo nội dung, học máy có giám sát, bài toán "
        "tối ưu tổ hợp có ràng buộc và các độ đo đánh giá;",
        "Chương 2: Phân tích thiết kế hệ thống — khảo sát hiện trạng, đặc tả "
        "yêu cầu, mô hình hóa bằng UML, thiết kế cơ sở dữ liệu, thiết kế "
        "thuật toán khuyến nghị bốn bước và cơ chế ba giai đoạn cho bài toán "
        "khởi đầu nguội;",
        "Chương 3: Xây dựng chương trình — xây dựng tập dữ liệu dinh dưỡng, "
        "cài đặt mô-đun tính nhu cầu và mô-đun khuyến nghị, xây dựng dịch vụ "
        "phía máy chủ và ứng dụng di động, thực nghiệm và đánh giá;",
        "Kết luận và hướng phát triển.",
    ]),
    ("b", "4. Các sản phẩm dự kiến"),
    ("ul", [
        "Tập dữ liệu dinh dưỡng các món ăn phổ biến của Việt Nam đã được "
        "chuẩn hóa, có đầy đủ năng lượng và ba chất sinh năng lượng;",
        "Mô-đun khuyến nghị thực đơn cá nhân hóa kết hợp lọc theo nội dung, "
        "bộ quy tắc ràng buộc dinh dưỡng và mô hình học máy có giám sát;",
        "Dịch vụ phía máy chủ cung cấp các giao diện lập trình quản lý người "
        "dùng, hồ sơ sức khỏe, món ăn, thực đơn, nhật ký ăn uống và phản hồi;",
        "Ứng dụng di động cho phép khai báo hồ sơ sức khỏe, nhận thực đơn gợi "
        "ý hằng ngày, ghi nhật ký ăn uống và đánh giá món ăn;",
        "Cơ sở dữ liệu hệ thống cùng bộ tài liệu phân tích thiết kế; mã nguồn "
        "hoàn chỉnh, báo cáo đồ án và slide bảo vệ.",
    ]),
    ("b", "5. Ngày giao đồ án: 30/08/2026"),
    ("b", "6. Ngày nộp đồ án: 20/12/2026"),
]

# ── MỞ ĐẦU ────────────────────────────────────────────────────────────────
MO_DAU = [
    ("md", "Tổng quan đề tài"),
    ("p",
     "Ăn uống đúng với thể trạng là việc ai cũng biết là cần, nhưng rất ít "
     "người làm được đều đặn. Người khỏe mạnh phải tự ước lượng mình cần bao "
     "nhiêu năng lượng mỗi ngày; người mang bệnh mạn tính như tăng huyết áp, "
     "đái tháo đường, gút hay bệnh thận còn phải nhớ thêm hàng loạt ngưỡng "
     "natri, đường, purin, đạm mà bác sĩ dặn. Việc quy đổi những ngưỡng đó "
     "thành bữa ăn cụ thể cho từng ngày là một công việc lặp đi lặp lại và "
     "dễ bỏ cuộc."),
    ("p",
     f"Đề tài “{TEN_DE_TAI}” hướng tới một ứng dụng di động làm thay người "
     "dùng phần việc tính toán đó: từ hồ sơ sức khỏe đã khai, hệ thống tự "
     "tính nhu cầu năng lượng, tự loại những món không an toàn và tự ghép "
     "các món còn lại thành thực đơn cho cả ngày."),
    ("p",
     "Điểm khác biệt của hệ thống nằm ở chỗ nó phải thỏa mãn cùng lúc hai "
     "yêu cầu vốn mâu thuẫn nhau: thực đơn phải đúng về mặt dinh dưỡng, và "
     "phải hợp khẩu vị thì người dùng mới ăn. Một thực đơn đúng chuẩn nhưng "
     "toàn món người dùng không thích thì cũng không ai theo được quá vài "
     "ngày. Vì vậy hệ thống kết hợp một bộ lọc cứng theo bệnh lý với một mô "
     "hình khuyến nghị học dần khẩu vị từ lịch sử tương tác của chính người "
     "dùng đó."),

    ("md", "Mục tiêu đề tài"),
    ("ul", [
        "Xây dựng ứng dụng di động cho phép người dùng khai báo hồ sơ sức "
        "khỏe gồm giới tính, tuổi, chiều cao, cân nặng, mức vận động, mục "
        "tiêu cân nặng, bệnh lý và dị ứng thực phẩm.",
        "Cài đặt mô-đun tính nhu cầu năng lượng và tỷ lệ ba chất sinh năng "
        "lượng cho từng người dùng từ các chỉ số BMI, BMR và TDEE.",
        "Xây dựng tập dữ liệu món ăn Việt Nam có thành phần dinh dưỡng, nhóm "
        "món, vai trò trong bữa và nhãn dị nguyên đầy đủ, đủ để bộ sinh thực "
        "đơn hoạt động.",
        "Thiết kế và cài đặt thuật toán khuyến nghị thực đơn theo quy trình "
        "bốn bước, bảo đảm thực đơn không vi phạm ràng buộc bệnh lý và dị "
        "ứng của người dùng.",
        "Cá nhân hóa gợi ý theo khẩu vị bằng mô hình khuyến nghị theo nội "
        "dung, chuyển dần sang mô hình học máy có giám sát khi lịch sử người "
        "dùng đủ lớn.",
        "Xây dựng trang quản trị cho phép quản lý danh mục món ăn, bộ quy "
        "tắc dinh dưỡng theo bệnh lý và theo dõi số liệu vận hành của hệ "
        "thống.",
    ]),

    ("md", "Đối tượng nghiên cứu và phạm vi nghiên cứu"),
    ("mda", "Đối tượng nghiên cứu"),
    ("ul", [
        "Bài toán khuyến nghị thực đơn cá nhân hóa có ràng buộc dinh dưỡng: "
        "chọn một tổ hợp món ăn cho các bữa trong ngày sao cho vừa hợp khẩu "
        "vị vừa thỏa các ngưỡng dinh dưỡng bắt buộc.",
        "Các phương pháp khuyến nghị theo nội dung và các thuật toán học máy "
        "có giám sát dùng để học khẩu vị người dùng từ lịch sử tương tác.",
        "Thành phần dinh dưỡng của món ăn Việt Nam và các khuyến nghị y khoa "
        "về giới hạn dinh dưỡng theo từng nhóm bệnh lý.",
        "Người dùng hệ thống: người dùng cuối và quản trị viên.",
    ]),
    ("mda", "Phạm vi nghiên cứu"),
    ("ul", [
        "Hệ thống gồm một ứng dụng di động dành cho người dùng cuối và một "
        "trang quản trị trên nền web dành cho quản trị viên.",
        "Danh mục món ăn giới hạn trong các món phổ biến của Việt Nam, số "
        "liệu dinh dưỡng tính từ Bảng thành phần thực phẩm Việt Nam; không "
        "đặt mục tiêu chính xác tuyệt đối tới từng món như một nghiên cứu "
        "công nghệ thực phẩm.",
        "Hệ thống hỗ trợ một nhóm bệnh lý và chế độ ăn phổ biến đã được "
        "khảo sát, không bao quát toàn bộ các bệnh lý có liên quan tới dinh "
        "dưỡng.",
        "Hệ thống đưa ra gợi ý mang tính tham khảo, không thay thế chỉ định "
        "của bác sĩ hay chuyên gia dinh dưỡng.",
        "Đồ án không đi sâu vào triển khai ở quy mô lớn hoặc tích hợp với "
        "các hệ thống y tế bên ngoài.",
    ]),

    ("md", "Phương pháp nghiên cứu"),
    ("ul", [
        "Nghiên cứu tài liệu: tổng hợp các công thức và ngưỡng dinh dưỡng từ "
        "tài liệu của Viện Dinh dưỡng, WHO và các hướng dẫn điều trị chuyên "
        "ngành; nghiên cứu lý thuyết hệ khuyến nghị và học máy từ các giáo "
        "trình và bài báo gốc.",
        "Khảo sát và phân tích hiện trạng: dùng thử và đối chiếu các ứng "
        "dụng dinh dưỡng đang phổ biến để xác định khoảng trống chức năng.",
        "Phương pháp mô hình hóa: mô hình hóa cấu trúc hệ thống bằng UML và "
        "mô hình thực thể – liên kết, mô hình hóa khẩu vị người dùng bằng "
        "vector đặc trưng, và mô hình hóa bài toán ghép thực đơn thành bài "
        "toán tối ưu có ràng buộc — xem mục a dưới đây.",
        "Phương pháp thực nghiệm: cài đặt hệ thống, chạy bộ sinh thực đơn "
        "trên tập dữ liệu thật và đo kết quả theo các ngưỡng dinh dưỡng đã "
        "đặt ra, thay vì chỉ mô tả bằng lời.",
    ]),

    ("mda", "Phương pháp mô hình hóa"),
    ("p",
     "Hệ thống được mô hình hóa ở ba tầng khác nhau, vì ba câu hỏi cần trả "
     "lời không cùng một loại. Tầng thứ nhất là cấu trúc: phân tích và thiết "
     "kế theo hướng đối tượng với UML, còn dữ liệu được mô hình hóa theo mô "
     "hình thực thể – liên kết rồi hiện thực hóa thành lược đồ quan hệ gồm "
     "22 bảng, 212 cột, 29 khóa ngoại và 16 ràng buộc kiểm tra. Điểm đáng "
     "nói ở tầng này là bộ quy tắc bệnh lý được lưu dưới dạng dữ liệu trong "
     "một bảng riêng chứ không viết cứng trong mã: thêm một "
     "bệnh lý là thêm dòng, không phải sửa chương trình."),
    ("p",
     "Tầng thứ hai là khẩu vị người dùng. Mỗi món ăn được mô hình hóa thành "
     "một vector 20 chiều gồm ba tỷ lệ năng lượng từ đạm – bột đường – chất "
     "béo, bốn chiều cảm quan đã chuẩn hóa về đoạn [0, 1] (năng lượng, độ "
     "ngọt, độ mặn, chất xơ), mức cay, và 12 chiều one-hot cho nhóm món. Sở "
     "thích của một người được tổng hợp thành một vector cùng không gian đó "
     "bằng thuật toán Rocchio: hồ sơ là trung bình có trọng số các vector "
     "món người đó đã đánh giá, với trọng số +1 cho món thích, 0 cho món "
     "bình thường và −1 cho món không thích; lượt “chưa từng ăn” bị loại "
     "khỏi cả tử số và mẫu số, vì nó không nói gì về khẩu vị. Độ phù hợp "
     "giữa người và món là độ tương đồng cosin, đưa về đoạn [0, 1] bằng phép "
     "(1 + cos) / 2 để dùng chung thang với điểm của mô hình học máy."),
    ("p",
     "Vì một người dùng mới chưa để lại hành vi nào, mô hình khuyến nghị "
     "không phải một mô hình duy nhất mà là bốn giai đoạn chuyển tiếp "
     "theo số tín hiệu n mà người đó đã cung cấp: giai đoạn nguội (n = 0) "
     "xếp hạng thuần theo luật dinh dưỡng và độ phổ biến; giai đoạn nội dung "
     "(0 < n < 30) dùng lọc theo nội dung với hồ sơ Rocchio; giai đoạn pha "
     "trộn (30 ≤ n ≤ 100) trộn tuyến tính hai nguồn điểm theo hệ số α tăng "
     "dần đều từ 0 lên 1; giai đoạn học máy (n > 100) để mô hình học máy "
     "chiếm toàn bộ trọng số. Cách bố trí này cho hệ thống hoạt động được "
     "ngay từ người dùng đầu tiên thay vì chờ tích lũy dữ liệu, và chuyển "
     "tiếp mượt thay vì đổi đột ngột khi vừa vượt ngưỡng."),
    ("p",
     "Tầng thứ ba là mô hình học máy. Đồ án so sánh ba thuật toán học có "
     "giám sát — hồi quy logistic, rừng ngẫu nhiên và tăng cường gradient — "
     "trên cùng một tập đặc trưng gồm thuộc tính người dùng, vector món, độ "
     "phổ biến của món và các đặc trưng tương tác chéo giữa hồ sơ và món. "
     "Cả ba được huấn luyện dưới dạng bài toán phân lớp nhị phân nên điểm "
     "dự đoán của chúng cùng nằm trên thang [0, 1] với điểm cosin, điều kiện "
     "bắt buộc để phép trộn theo α có nghĩa."),
    ("p",
     "Ràng buộc dinh dưỡng được mô hình hóa tách khỏi khẩu vị, theo ba mức "
     "khác nhau về hệ quả. Ràng buộc cứng theo khẩu phần loại hẳn món khỏi "
     "tập ứng viên trước mọi phép chấm điểm, nên một món chống chỉ định "
     "không thể nổi lên nhờ điểm khẩu vị cao. Ràng buộc cứng theo ngày không "
     "loại món nào mà được thi hành ở bước ghép thực đơn, vì mọi hướng dẫn "
     "y khoa đều phát biểu theo ngày chứ không theo từng món — chia nhỏ "
     "xuống mỗi suất là tự đặt ra một ràng buộc chặt hơn nguồn. Ràng buộc "
     "mềm chỉ nhân điểm với một hệ số nhỏ hơn 1 để hạ bậc món, giữ nó lại "
     "trong tập ứng viên làm đường xoay xở cho bước tối ưu."),
    ("p",
     "Bước ghép thực đơn được mô hình hóa thành bài toán cái túi đa chiều: "
     "chọn tập món tối đa tổng điểm ưa thích, đồng thời thỏa hạn mức năng "
     "lượng, ba hạn mức chất sinh năng lượng và các ngưỡng vi chất theo "
     "ngày, dưới một cấu trúc bữa cho trước. Hàm mục tiêu cộng thêm hai số "
     "hạng phạt theo độ lệch năng lượng và độ lệch macro so với mục tiêu."),
    ("p",
     "Hiệu quả của mô hình được đánh giá bằng kiểm định chéo chia theo người "
     "dùng — mọi mẫu của một người nằm trọn trong một fold, vì chia "
     "theo mẫu sẽ để lịch sử của chính người đó rò rỉ sang tập kiểm tra và "
     "cho ra kết quả đẹp giả. Mô hình được đối chiếu với bốn phương án nền "
     "(chỉ độ phổ biến, chỉ luật dinh dưỡng, chỉ lọc theo nội dung, và bản "
     "pha trộn) trên tám chỉ số thuộc ba nhóm: xếp hạng (nDCG@k, Precision@k, "
     "Recall@k, MAP), hồi quy (MAE, RMSE) và phân lớp (F1, AUC)."),

    ("md", "Giải pháp công nghệ"),
    ("ul", [
        "Ứng dụng di động: Flutter — một mã nguồn chạy được trên cả Android "
        "và iOS, phù hợp với phạm vi một đồ án tốt nghiệp.",
        "Dịch vụ phía máy chủ: ASP.NET Core, cung cấp các giao diện lập "
        "trình dạng RESTful.",
        "Cơ sở dữ liệu: MySQL 8.0, dùng để lưu người dùng, hồ sơ sức khỏe, "
        "danh mục món ăn, thực đơn, nhật ký ăn uống và dữ liệu huấn luyện.",
        "Mô-đun khuyến nghị: Python cùng thư viện scikit-learn để trích chọn "
        "đặc trưng, huấn luyện và đánh giá mô hình.",
        "Công cụ hỗ trợ: StarUML để vẽ các biểu đồ phân tích thiết kế, Git "
        "để quản lý mã nguồn.",
    ]),

    ("md", "Cấu trúc đồ án"),
    ("p", "Nội dung đồ án được trình bày theo bố cục sau:"),
    ("ul", [
        "Mở đầu;",
        "Chương 1: Cơ sở lý thuyết;",
        "Chương 2: Phân tích thiết kế hướng đối tượng;",
        "Chương 3: Xây dựng chương trình;",
        "Kết luận và hướng phát triển.",
    ]),
]

# ── 1.1 – 1.3 trong Chương 1 ──────────────────────────────────────────────
CHUONG1 = [
    ("h2", "Giới thiệu"),

    ("h3", "Mục tiêu của ứng dụng"),
    ("p", "Ứng dụng được xây dựng nhằm mục đích:"),
    ("ul", [
        "Thay người dùng thực hiện toàn bộ phần tính toán dinh dưỡng: từ hồ "
        "sơ sức khỏe đã khai, hệ thống tự tính nhu cầu năng lượng mỗi ngày "
        "và tỷ lệ ba chất sinh năng lượng tương ứng.",
        "Bảo đảm thực đơn gợi ra luôn an toàn với tình trạng sức khỏe của "
        "người dùng: không chứa món gây dị ứng, không vi phạm chế độ ăn và "
        "không vượt các ngưỡng dinh dưỡng của bệnh lý đã khai.",
        "Cá nhân hóa gợi ý theo khẩu vị của từng người, để thực đơn đúng về "
        "dinh dưỡng nhưng vẫn là món người dùng thực sự muốn ăn.",
        "Giảm công sức ra quyết định hằng ngày: người dùng mở ứng dụng là có "
        "ngay thực đơn cho cả ba bữa, thay vì phải tự nghĩ và tự tra cứu.",
        "Ghi nhận phản hồi của người dùng để gợi ý của những lần sau sát hơn "
        "với khẩu vị và thói quen ăn uống thực tế.",
        "Cung cấp cho quản trị viên công cụ quản lý danh mục món ăn và bộ "
        "quy tắc dinh dưỡng, để hệ thống bám theo khuyến nghị y khoa mà "
        "không phải sửa mã nguồn.",
    ]),

    ("h3", "Vấn đề giải quyết"),
    ("ul", [
        "Người dùng không biết mình cần bao nhiêu năng lượng mỗi ngày, và "
        "càng khó quy đổi con số đó thành món ăn cụ thể cho từng bữa.",
        "Người mang bệnh mạn tính phải nhớ cùng lúc nhiều ngưỡng dinh dưỡng "
        "khác nhau; việc kiểm tra từng món ăn có vượt ngưỡng hay không là "
        "quá sức với người không có chuyên môn.",
        "Người dị ứng thực phẩm phải tự rà nguyên liệu của từng món, trong "
        "khi một sai sót nhỏ có thể gây hậu quả nghiêm trọng.",
        "Các ứng dụng dinh dưỡng phổ biến chủ yếu phục vụ việc ghi chép và "
        "đếm năng lượng sau khi đã ăn, chứ không trả lời câu hỏi nên ăn gì "
        "trước bữa ăn.",
        "Những ứng dụng có gợi ý thực đơn thì thường dùng thực đơn mẫu cố "
        "định, không thay đổi theo khẩu vị và tình trạng sức khỏe của từng "
        "người.",
        "Các thực đơn mẫu phổ biến trên mạng hầu hết là món nước ngoài, "
        "không hợp với bữa ăn và nguyên liệu thường gặp của người Việt.",
    ]),

    ("h3", "Yêu cầu chức năng"),
    ("b", "Đối với người dùng:"),
    ("ul", [
        "Đăng ký, đăng nhập, quên mật khẩu và đổi mật khẩu.",
        "Khai báo và cập nhật hồ sơ sức khỏe: giới tính, ngày sinh, chiều "
        "cao, cân nặng, mức vận động, mục tiêu cân nặng, bệnh lý và dị ứng.",
        "Thực hiện phiên khảo sát khẩu vị để hệ thống hiểu sở thích ngay từ "
        "lần dùng đầu tiên.",
        "Xem thực đơn gợi ý cho từng ngày, chia theo bữa sáng, trưa, tối.",
        "Xem chi tiết thành phần dinh dưỡng và nhãn của từng món.",
        "Đổi một món trong thực đơn sang món khác cùng vai trò trong bữa.",
        "Thêm món ăn của riêng mình và đưa món đó vào thực đơn.",
        "Đánh giá món ăn, ghi nhật ký ăn uống và theo dõi diễn biến thể "
        "trạng theo thời gian.",
    ]),
    ("b", "Đối với quản trị viên:"),
    ("ul", [
        "Thêm, sửa và ngừng hiển thị món ăn cùng số liệu dinh dưỡng và nhãn "
        "của món.",
        "Quản lý danh mục bệnh lý, chế độ ăn và bộ quy tắc dinh dưỡng đi "
        "kèm từng bệnh lý.",
        "Quản lý tài khoản người dùng: tra cứu, khóa và mở lại tài khoản.",
        "Xem số liệu phân tích về người dùng và danh mục món ăn.",
    ]),

    ("h3", "Yêu cầu phi chức năng"),
    ("b", "Tính đúng đắn của số liệu:"),
    ("ul", [
        "Thành phần dinh dưỡng của món ăn phải truy được về nguồn công bố; "
        "chất nào nguồn không công bố thì hiển thị “chưa có số liệu” chứ "
        "không hiển thị số 0.",
        "Mỗi ngưỡng dinh dưỡng theo bệnh lý phải dẫn được khuyến nghị y khoa "
        "tương ứng.",
    ]),
    ("b", "Hiệu năng:"),
    ("ul", [
        "Thời gian sinh thực đơn ngày không vượt quá vài giây trên tập "
        "dữ liệu hiện có.",
        "Giao diện phản hồi mượt, không để người dùng chờ mà không có thông "
        "báo trạng thái.",
    ]),
    ("b", "An toàn và bảo mật:"),
    ("ul", [
        "Mật khẩu chỉ lưu dưới dạng bản băm; hệ thống không hiển thị mật "
        "khẩu dưới bất kỳ dạng nào.",
        "Mỗi người dùng chỉ truy cập được dữ liệu của chính mình; số liệu "
        "thống kê chỉ trình bày ở dạng tổng hợp.",
    ]),
    ("b", "Tính dễ dùng và khả năng mở rộng:"),
    ("ul", [
        "Giao diện tiếng Việt, thao tác khai báo hồ sơ và chọn khẩu vị đơn "
        "giản, phù hợp với người không có kiến thức dinh dưỡng.",
        "Danh mục món ăn, bệnh lý và quy tắc dinh dưỡng được quản lý bằng dữ "
        "liệu, thêm bớt không cần sửa mã nguồn.",
    ]),

    ("h3", "Tính năng nổi bật"),
    ("b", "Bộ lọc an toàn theo bệnh lý và dị ứng:"),
    ("ul", [
        "Mỗi bệnh lý và chế độ ăn gắn với một bộ quy tắc lọc riêng, chia làm "
        "quy tắc cứng (loại hẳn món vi phạm) và quy tắc mềm (chỉ trừ điểm "
        "phù hợp).",
        "Mọi món đưa tới người dùng — dù trong phiên khảo sát khẩu vị, trong "
        "thực đơn hay trong danh sách đổi món — đều đã đi qua bộ lọc này.",
    ]),
    ("b", "Khuyến nghị theo nội dung dựa trên vector đặc trưng:"),
    ("ul", [
        "Mỗi món ăn được biểu diễn thành một vector đặc trưng hai mươi "
        "chiều gồm tỷ lệ ba chất sinh năng lượng, năng lượng, vị ngọt, vị "
        "mặn, chất xơ, mức cay và nhóm món.",
        "Hồ sơ sở thích của người dùng cũng là một vector cùng không gian, "
        "cập nhật dần theo thuật toán Rocchio sau mỗi lượt phản hồi.",
        "Độ phù hợp giữa món ăn và người dùng tính bằng độ tương đồng cosin "
        "giữa hai vector đó.",
    ]),
    ("b", "Ghép thực đơn có ràng buộc dinh dưỡng theo ngày:"),
    ("ul", [
        "Các ngưỡng dinh dưỡng của bệnh lý được kiểm trên tổng cả ngày chứ "
        "không trên từng món, đúng như cách các hướng dẫn y khoa phát biểu.",
        "Tổng năng lượng cả ngày được giữ trong khoảng lệch không quá 10 % "
        "so với hạn mức tính từ hồ sơ.",
        "Khi danh mục không đủ để thỏa một ngưỡng, hệ thống vẫn trình bày "
        "thực đơn nhưng ghi rõ ngưỡng nào chưa đạt và số liệu thực tế là bao "
        "nhiêu, thay vì trình bày như đã đạt.",
    ]),
    ("b", "Giải quyết bài toán cold-start:"),
    ("ul", [
        "Người dùng mới chưa có lịch sử vẫn nhận được gợi ý hợp khẩu vị nhờ "
        "một phiên khảo sát ngắn thực hiện một lần lúc khởi tạo tài khoản.",
        "Khi lịch sử tương tác tích lũy đủ, hệ thống chuyển dần trọng số từ "
        "mô hình theo nội dung sang mô hình học máy có giám sát.",
    ]),

    ("h3", "Lợi ích mang lại"),
    ("b", "Tiết kiệm thời gian và công sức:"),
    ("ul", [
        "Người dùng không phải tự tính nhu cầu năng lượng và tự tra cứu "
        "thành phần của từng món.",
        "Thực đơn cho cả ngày được sinh tự động, có thể đổi từng món nếu "
        "không hợp nguyên liệu sẵn có.",
    ]),
    ("b", "Nâng cao mức độ an toàn:"),
    ("ul", [
        "Món chứa dị nguyên đã khai bị loại khỏi mọi gợi ý, không phụ thuộc "
        "vào việc người dùng có nhớ rà nguyên liệu hay không.",
        "Các ngưỡng dinh dưỡng theo bệnh lý được kiểm tự động trên tổng cả "
        "ngày.",
    ]),
    ("b", "Tăng khả năng duy trì chế độ ăn:"),
    ("ul", [
        "Gợi ý bám theo khẩu vị thực tế nên người dùng dễ theo lâu dài hơn "
        "so với một thực đơn mẫu cố định.",
        "Nhật ký ăn uống và biểu đồ thể trạng cho người dùng thấy được tiến "
        "độ của chính mình.",
    ]),

    ("h2", "Thu thập yêu cầu"),

    ("h3", "Phương pháp thu thập thông tin"),
    ("b", "Nghiên cứu tài liệu chuyên ngành:"),
    ("p",
     "Tổng hợp các công thức tính nhu cầu năng lượng và các ngưỡng dinh "
     "dưỡng từ tài liệu của Viện Dinh dưỡng Quốc gia, khuyến nghị của Tổ "
     "chức Y tế Thế giới và các hướng dẫn điều trị chuyên ngành, để xác định "
     "những ràng buộc mà hệ thống bắt buộc phải tôn trọng."),
    # Mục "Khảo sát các ứng dụng tương tự" đã bỏ khỏi báo cáo; phần đối
    # chiếu với các cách làm hiện nay nằm trong bảng so sánh ở dưới.
    ("b", "Khảo sát người dùng:"),
    ("p",
     "Thu thập ý kiến của những người đang hoặc từng theo một chế độ ăn — "
     "giảm cân, tăng cân, ăn chay hoặc ăn kiêng theo bệnh lý — về khó khăn "
     "khi lên thực đơn, về việc có duy trì được chế độ ăn hay không và lý do "
     "bỏ dở."),
    ("b", "Tham khảo nguồn dữ liệu chuẩn:"),
    ("p",
     "Đối chiếu Bảng thành phần thực phẩm Việt Nam với các cơ sở dữ liệu "
     "dinh dưỡng mở để kiểm chứng số liệu và bổ sung những chất mà một nguồn "
     "không công bố."),

    ("h3", "Phân tích thông tin thu thập được"),
    ("ul", [
        "Người dùng cần biết nên ăn gì trước bữa ăn, chứ không chỉ cần biết "
        "mình vừa ăn bao nhiêu năng lượng sau khi đã ăn xong.",
        "Yêu cầu bắt buộc, không thể thỏa hiệp, là thực đơn phải an toàn với "
        "dị ứng và bệnh lý đã khai.",
        "Yêu cầu quyết định việc người dùng có theo lâu dài hay không lại là "
        "khẩu vị: thực đơn đúng chuẩn nhưng không hợp miệng thì bị bỏ sau "
        "vài ngày.",
        "Người dùng mong muốn thực đơn gồm món ăn Việt Nam quen thuộc, nấu "
        "được bằng nguyên liệu dễ mua.",
        "Người dùng cần đổi được món trong thực đơn, vì nguyên liệu sẵn có "
        "và tâm trạng ăn uống thay đổi theo từng ngày.",
        "Các ngưỡng dinh dưỡng trong hướng dẫn y khoa đều phát biểu theo "
        "ngày, nên hệ thống phải kiểm trên tổng cả ngày thay vì trên từng "
        "món.",
        "Quản trị viên cần sửa được danh mục món và bộ quy tắc dinh dưỡng "
        "khi khuyến nghị y khoa thay đổi, mà không phải sửa mã nguồn.",
    ]),
    ("p", "Từ đó xác định được các tác nhân của hệ thống như sau:"),
    ("bang", {
        "widths": [709, 2126, 6237],
        "head": ["STT", "Tác nhân (Actor)", "Mô tả vai trò"],
        "rows": [
            ["1", "Người dùng (User)",
             "Là người sử dụng ứng dụng di động. Người dùng khai báo hồ sơ "
             "sức khỏe, thực hiện phiên khảo sát khẩu vị, xem và điều chỉnh "
             "thực đơn hằng ngày, thêm món ăn của riêng mình, đánh giá món "
             "ăn, ghi nhật ký ăn uống và theo dõi diễn biến thể trạng."],
            ["2", "Quản trị viên (Admin)",
             "Là người quản lý hệ thống qua trang quản trị trên nền web. "
             "Quản trị viên cập nhật danh mục món ăn và số liệu dinh dưỡng, "
             "quản lý danh mục bệnh lý cùng bộ quy tắc dinh dưỡng, quản lý "
             "tài khoản người dùng và xem các số liệu phân tích."],
            ["3", "Hệ thống (System)",
             "Tự động thực hiện phần việc không cần người can thiệp: "
             "tính nhu cầu năng lượng từ hồ sơ, lọc món theo bệnh lý và dị "
             "ứng, xếp hạng món theo khẩu vị, ghép thực đơn ngày và cập "
             "nhật hồ sơ sở thích sau mỗi lượt phản hồi."],
        ],
        "caption": "Các tác nhân và vai trò trong hệ thống",
    }),

    ("h3", "Lý do xây dựng ứng dụng"),
    ("p", "Ứng dụng được xây dựng nhằm:"),
    ("ul", [
        "Giải quyết trọn vẹn khâu còn thiếu của các ứng dụng dinh dưỡng hiện "
        "có: trả lời câu hỏi nên ăn gì, thay vì chỉ ghi lại đã ăn gì.",
        "Đưa các ngưỡng dinh dưỡng trong hướng dẫn y khoa — vốn khó áp dụng "
        "với người không có chuyên môn — thành thực đơn cụ thể cho từng "
        "ngày.",
        "Loại bỏ rủi ro dị ứng và vi phạm chế độ ăn bằng một bộ lọc tự động, "
        "thay vì trông chờ người dùng tự rà nguyên liệu.",
        "Xây dựng một tập dữ liệu món ăn Việt Nam có thành phần dinh dưỡng "
        "và nhãn dị nguyên đầy đủ, điều mà các nguồn dữ liệu mở hiện nay còn "
        "thiếu đối với món Việt.",
        "Áp dụng lý thuyết hệ khuyến nghị và học máy vào một bài toán có "
        "ràng buộc cứng, nơi gợi ý sai không chỉ là bất tiện mà còn có thể "
        "ảnh hưởng tới sức khỏe.",
    ]),

    ("h3", "Những điểm nổi bật của ứng dụng"),
    ("ul", [
        "Kết hợp hai lớp: một bộ lọc cứng bảo đảm an toàn y khoa và một mô "
        "hình khuyến nghị học khẩu vị, thay vì chỉ dùng một trong hai.",
        "Ràng buộc dinh dưỡng được kiểm trên tổng cả ngày, đúng cách các "
        "hướng dẫn y khoa phát biểu, chứ không áp máy móc lên từng món.",
        "Mỗi ngưỡng dinh dưỡng trong hệ thống đều dẫn được nguồn khuyến "
        "nghị, không phải con số tự đặt.",
        "Giải quyết bài toán khởi đầu nguội bằng một phiên khảo sát khẩu vị "
        "ngắn, nên người dùng mới không phải chờ tích lũy lịch sử.",
        "Khi thiếu dữ liệu, hệ thống nói rõ là thiếu: chất chưa có số liệu "
        "hiển thị “chưa có số liệu”, thực đơn chưa đạt ngưỡng hiển thị cảnh "
        "báo kèm số liệu thực tế.",
        "Danh mục món ăn gồm các món Việt Nam quen thuộc, tính từ nguyên "
        "liệu theo Bảng thành phần thực phẩm Việt Nam.",
    ]),

    ("h3", "Giá trị mang lại"),
    ("b", "Đối với người dùng:"),
    ("ul", [
        "Có thực đơn phù hợp cho từng ngày mà không cần kiến thức dinh "
        "dưỡng.",
        "Yên tâm về mặt an toàn: món gây dị ứng và món vi phạm chế độ ăn "
        "không xuất hiện trong gợi ý.",
        "Theo dõi được nhật ký ăn uống và diễn biến thể trạng của chính "
        "mình.",
    ]),
    ("b", "Đối với quản trị viên:"),
    ("ul", [
        "Quản lý danh mục món ăn và bộ quy tắc dinh dưỡng bằng giao diện, "
        "không phải can thiệp vào cơ sở dữ liệu.",
        "Nắm được hệ thống đang phục vụ nhóm người dùng nào và nhóm món nào "
        "còn thiếu, thông qua các màn hình thống kê.",
    ]),
    ("b", "Đối với hệ thống:"),
    ("ul", [
        "Tập dữ liệu và bộ quy tắc được tổ chức theo dữ liệu nên mở rộng "
        "thêm món, thêm bệnh lý không cần sửa mã nguồn.",
        "Lịch sử tương tác tích lũy theo thời gian làm chất lượng gợi ý tốt "
        "dần lên.",
    ]),

    ("h2", "Đánh giá sản phẩm"),
    ("p",
     "Để thấy rõ vị trí của hệ thống đề xuất, phần này đối chiếu hệ thống "
     "với hai cách làm phổ biến hiện nay: người dùng tự tra cứu, và các ứng "
     "dụng dinh dưỡng thiên về ghi chép – đếm năng lượng."),
    ("bang", {
        "widths": [2300, 1130, 1130, 1130, 1130, 1130, 1122],
        "head": ["Cách làm", "Tính nhu cầu năng lượng",
                 "Lọc theo bệnh lý, dị ứng", "Cá nhân hóa theo khẩu vị",
                 "Sinh thực đơn cả ngày", "Ràng buộc theo ngày",
                 "Học từ lịch sử"],
        "rows": [
            ["Tự tra cứu và tự lên thực đơn", "", "", "X", "", "", ""],
            ["Ứng dụng ghi chép – đếm năng lượng", "X", "", "", "", "", ""],
            ["Ứng dụng gợi ý thực đơn mẫu cố định", "X", "", "", "X", "", ""],
            ["Hệ thống đề xuất của đồ án", "X", "X", "X", "X", "X", "X"],
        ],
        "caption": "So sánh hệ thống đề xuất với các cách làm hiện nay",
    }),
    ("b", "Chú thích:"),
    ("ul", [
        "Tự tra cứu và tự lên thực đơn: hợp khẩu vị vì chính người dùng "
        "chọn, nhưng toàn bộ phần tính nhu cầu năng lượng và kiểm tra ngưỡng "
        "dinh dưỡng đều phụ thuộc vào kiến thức và sự kiên trì của người "
        "dùng.",
        "Ứng dụng ghi chép – đếm năng lượng: tính được nhu cầu năng lượng và "
        "thống kê lượng đã nạp, nhưng chỉ làm việc đó sau khi người dùng đã "
        "ăn và tự nhập món.",
        "Ứng dụng gợi ý thực đơn mẫu cố định: có thực đơn sẵn cho cả ngày "
        "nhưng giống nhau với mọi người dùng, không đổi theo bệnh lý và khẩu "
        "vị của từng người.",
        "Hệ thống đề xuất của đồ án: thực hiện đủ cả sáu khâu, trong đó hai "
        "khâu lọc theo bệnh lý và ràng buộc dinh dưỡng theo ngày là phần mà "
        "các cách làm trên đều bỏ trống.",
    ]),
]


# ── TÀI LIỆU THAM KHẢO ─────────────────────────────────────────────────────
#
# Chỉ gồm nguồn ĐƯỢC NÊU TÊN trong thân bài hoặc được dẫn trong
# `condition_rules.note` và `rda_reference.source`. Không thêm nguồn cho dày
# danh sách: một tài liệu có trong đây mà không chỗ nào dùng tới thì hội
# đồng hỏi là không trả lời được.
#
# `tools/check_nguon.py` soát theo chiều ngược lại — mọi nguồn đang dẫn
# trong CSDL phải có mặt ở đây — nên thêm một quy tắc bệnh lý với nguồn mới
# mà quên bổ sung thì phép kiểm sai ngay.
#
# HAI MỤC CẦN BẠN BỔ SUNG, đã ghi rõ trong ngoặc: năm bản của ADA Standards
# of Care và phiên bản hướng dẫn gút của Nhật Bản. Tôi không điền số mình
# không chắc vào tài liệu tham khảo của đồ án.
TAI_LIEU = [
    # ── Nguồn số liệu dinh dưỡng ──
    ("tl",
     "Viện Dinh dưỡng Quốc gia, Bộ Y tế, “Bảng thành phần thực phẩm Việt "
     "Nam”, Nhà xuất bản Y học, Hà Nội, 2007."),
    ("tl",
     "Viện Dinh dưỡng Quốc gia, Bộ Y tế, “Nhu cầu dinh dưỡng khuyến nghị "
     "cho người Việt Nam”, 2016."),
    ("tl",
     "United States Department of Agriculture, “FoodData Central”, "
     "https://fdc.nal.usda.gov (bộ dữ liệu SR Legacy và Foundation)."),

    # ── Khuyến nghị và hướng dẫn điều trị ──
    ("tl",
     "World Health Organization, “Guideline: Sodium intake for adults and "
     "children”, Geneva, 2012."),
    ("tl",
     "World Health Organization, “Carbohydrate intake for adults and "
     "children: WHO guideline”, Geneva, 2023."),
    ("tl",
     "WHO Expert Consultation, “Appropriate body-mass index for Asian "
     "populations and its implications for policy and intervention "
     "strategies”, The Lancet, vol. 363, no. 9403, pp. 157–163, 2004."),
    ("tl",
     "Kidney Disease: Improving Global Outcomes (KDIGO), “2024 Clinical "
     "Practice Guideline for the Evaluation and Management of Chronic Kidney "
     "Disease”, Kidney International, vol. 105, no. 4S, 2024."),
    ("tl",
     "American Diabetes Association, “Standards of Care in Diabetes”, "
     "Diabetes Care (xuất bản hằng năm) [bổ sung năm bản đã dùng]."),
    ("tl",
     "United States Department of Agriculture và Department of Health and "
     "Human Services, “Dietary Guidelines for Americans 2015–2020”, 8th "
     "edition, 2015."),
    ("tl",
     "American College of Cardiology và American Heart Association, “2019 "
     "ACC/AHA Guideline on the Primary Prevention of Cardiovascular "
     "Disease”, Circulation, vol. 140, no. 11, 2019."),
    ("tl",
     "Japanese Society of Gout and Uric & Nucleic Acids, “Guideline for the "
     "Management of Hyperuricemia and Gout” [bổ sung phiên bản và năm]."),
    ("tl",
     "M. D. Mifflin, S. T. St Jeor, L. A. Hill, B. J. Scott, S. A. "
     "Daugherty và Y. O. Koh, “A new predictive equation for resting energy "
     "expenditure in healthy individuals”, The American Journal of Clinical "
     "Nutrition, vol. 51, no. 2, pp. 241–247, 1990."),

    # ── Hệ khuyến nghị và học máy ──
    ("tl",
     "J. J. Rocchio, “Relevance Feedback in Information Retrieval”, trong "
     "G. Salton (chủ biên), The SMART Retrieval System: Experiments in "
     "Automatic Document Processing, Prentice-Hall, pp. 313–323, 1971."),
    ("tl",
     "G. Salton, A. Wong và C. S. Yang, “A Vector Space Model for Automatic "
     "Indexing”, Communications of the ACM, vol. 18, no. 11, pp. 613–620, "
     "1975."),
    ("tl",
     "K. Järvelin và J. Kekäläinen, “Cumulated gain-based evaluation of IR "
     "techniques”, ACM Transactions on Information Systems, vol. 20, no. 4, "
     "pp. 422–446, 2002."),
    ("tl",
     "E. B. Wilson, “Probable Inference, the Law of Succession, and "
     "Statistical Inference”, Journal of the American Statistical "
     "Association, vol. 22, no. 158, pp. 209–212, 1927."),
    ("tl",
     "F. Ricci, L. Rokach và B. Shapira (chủ biên), “Recommender Systems "
     "Handbook”, Springer, 2022."),
    ("tl",
     "F. Pedregosa và cộng sự, “Scikit-learn: Machine Learning in Python”, "
     "Journal of Machine Learning Research, vol. 12, pp. 2825–2830, 2011."),

    # ── Công cụ và nền tảng ──
    ("tl", "Google, “Flutter documentation”, https://docs.flutter.dev."),
    ("tl",
     "Microsoft, “ASP.NET Core documentation”, "
     "https://learn.microsoft.com/aspnet/core."),
    ("tl",
     "Oracle, “MySQL 8.0 Reference Manual”, "
     "https://dev.mysql.com/doc/refman/8.0/en."),
]
