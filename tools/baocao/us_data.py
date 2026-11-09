# -*- coding: utf-8 -*-
"""Nội dung 18 User story, lấy đúng 18 use case trong Diagram.mdj.

Tiêu chuẩn chấp nhận bám vào hệ thống đã dựng thật — danh mục 318 món, Bộ
lọc F1, vector 20 chiều, ngưỡng lệch năng lượng 10 %, ngưỡng vi chất theo
ngày — chứ không viết chung chung, đúng yêu cầu "rõ ràng, đo được và không
mơ hồ" của tài liệu hướng dẫn.

Mỗi User story tách làm hai danh sách, đúng cách trình bày của đồ án mẫu:

    criteria  → "Tiêu chuẩn chấp nhận": hành vi quan sát được của hệ thống.
    rules     → "Ràng buộc dữ liệu": giới hạn giá trị và quy tắc nghiệp vụ.
                Để rỗng nếu User story đó không có ràng buộc riêng.

Viết bằng câu tiếng Việt thường, không dùng khuôn Given – When – Then: đồ
án mẫu không dùng khuôn này, và điều kiện của mỗi tiêu chuẩn đã nằm sẵn
trong mệnh đề "… thì …" nên thêm khuôn ngoại ngữ chỉ làm câu khó đọc.

Mã ID_US KHÔNG ghi ở đây — build_us.py tự đánh theo thứ tự trong danh sách.
Chèn một User story vào giữa thì chỉ việc đặt nó đúng chỗ, toàn bộ mã phía
sau tự dồn xuống; ghi tay thì mỗi lần chèn là một lần sửa mười mấy chỗ.

Thứ tự đã sắp theo luồng người dùng: xác thực → hồ sơ và khẩu vị → thực đơn
hằng ngày → nhật ký và theo dõi → phần của quản trị viên.
"""

# (tên mục, tác nhân, ưu tiên, vai trò, mong muốn, giá trị,
#  yêu cầu người dùng, [tiêu chuẩn chấp nhận], [ràng buộc dữ liệu])
STORIES = [
    (
        "Đăng ký",
        "Người dùng",
        "Cao",
        "một khách truy cập chưa có tài khoản",
        "đăng ký tài khoản bằng địa chỉ email và mật khẩu",
        "có hồ sơ riêng lưu lại khẩu vị, tình trạng sức khỏe và thực đơn "
        "của tôi",
        "Người dùng nhập email, mật khẩu, xác nhận mật khẩu và tên hiển "
        "thị.",
        [
            "Email chưa tồn tại trong hệ thống và biểu mẫu hợp lệ thì hệ "
            "thống tạo tài khoản và chuyển sang bước khai báo hồ sơ sức "
            "khỏe.",
            "Bỏ trống bất kỳ trường bắt buộc nào thì hiển thị “Vui lòng "
            "nhập đầy đủ thông tin”.",
        ],
        [
            "Email phải đúng định dạng và là duy nhất. Trùng email thì "
            "hiển thị “Email đã được sử dụng”.",
            "Mật khẩu tối thiểu 8 ký tự, gồm cả chữ và số. Hệ thống chỉ "
            "lưu bản băm, không lưu mật khẩu gốc.",
            "Tài khoản mới mặc định mang vai trò “người dùng”. Vai trò "
            "“quản trị viên” chỉ được cấp từ trang quản trị.",
        ],
    ),
    (
        "Đăng nhập",
        "Người dùng, Quản trị viên",
        "Cao",
        "người dùng đã có tài khoản",
        "đăng nhập bằng email và mật khẩu",
        "truy cập thực đơn, nhật ký ăn uống và các chức năng dành riêng "
        "cho tôi",
        "Người dùng nhập email và mật khẩu đã đăng ký.",
        [
            "Nhập đúng email và mật khẩu thì hệ thống cấp một mã thông "
            "hành (token) để xác thực các yêu cầu tiếp theo.",
            "Sai email hoặc sai mật khẩu đều chỉ hiển thị một thông báo "
            "chung “Email hoặc mật khẩu không đúng”, không nói rõ sai ở "
            "đâu để không lộ email nào đã đăng ký.",
            "Sau khi đăng nhập, hệ thống điều hướng theo vai trò: người "
            "dùng vào màn hình thực đơn, quản trị viên vào trang quản trị.",
            "Người dùng chưa khai báo hồ sơ sức khỏe thì được đưa thẳng "
            "tới bước khai báo thay vì vào thực đơn.",
        ],
        [
            "Tài khoản đã bị ngừng hoạt động thì không đăng nhập được.",
        ],
    ),
    (
        "Quên mật khẩu",
        "Người dùng",
        "Cao",
        "người dùng đã có tài khoản nhưng quên mật khẩu",
        "đặt lại mật khẩu qua địa chỉ email đã đăng ký",
        "lấy lại được hồ sơ sức khỏe và thực đơn đã tích lũy, thay vì phải "
        "tạo tài khoản mới từ đầu",
        "Người dùng nhập email đã đăng ký, mở liên kết nhận được trong hộp "
        "thư rồi đặt mật khẩu mới.",
        [
            "Email có trong hệ thống thì hệ thống gửi tới hộp thư đó một "
            "liên kết đặt lại mật khẩu.",
            "Email không có trong hệ thống vẫn hiển thị đúng thông báo như "
            "trường hợp có — “Nếu email đã đăng ký, hướng dẫn đặt lại mật "
            "khẩu đã được gửi” — để không lộ email nào đã đăng ký.",
            "Mở liên kết còn hiệu lực thì người dùng đặt được mật khẩu mới "
            "và đăng nhập lại ngay bằng mật khẩu đó.",
            "Liên kết đã hết hạn hoặc đã dùng rồi thì hệ thống báo “Liên "
            "kết đã hết hiệu lực” và cho yêu cầu gửi lại.",
        ],
        [
            "Liên kết đặt lại chỉ dùng được một lần và hết hiệu lực sau 15 "
            "phút kể từ lúc gửi.",
            "Mật khẩu mới theo đúng quy tắc khi đăng ký: tối thiểu 8 ký tự, "
            "gồm cả chữ và số; hệ thống chỉ lưu bản băm.",
            "Đặt lại mật khẩu thành công thì mọi mã thông hành (token) đang "
            "có của tài khoản đó hết hiệu lực, buộc đăng nhập lại trên mọi "
            "thiết bị — vì mật khẩu cũ được coi là đã lộ.",
        ],
    ),
    (
        "Đổi mật khẩu",
        "Người dùng, Quản trị viên",
        "Trung bình",
        "người dùng đang đăng nhập",
        "đổi mật khẩu hiện tại sang một mật khẩu mới",
        "giữ an toàn cho tài khoản khi nghi ngờ mật khẩu đã bị lộ",
        "Người dùng nhập mật khẩu hiện tại, mật khẩu mới và ô xác nhận mật "
        "khẩu mới.",
        [
            "Mật khẩu hiện tại đúng và mật khẩu mới hợp lệ thì hệ thống đổi "
            "mật khẩu và báo đổi thành công.",
            "Mật khẩu hiện tại sai thì hệ thống từ chối và giữ nguyên mật "
            "khẩu cũ.",
            "Mật khẩu mới và ô xác nhận không khớp thì hiển thị “Mật khẩu "
            "xác nhận không khớp” và không lưu.",
            "Đổi xong, phiên đang dùng vẫn giữ nguyên; các phiên trên thiết "
            "bị khác bị đăng xuất.",
        ],
        [
            "Mật khẩu mới theo đúng quy tắc khi đăng ký và phải khác mật "
            "khẩu hiện tại.",
            "Chỉ người đã đăng nhập mới đổi được, và chỉ đổi được mật khẩu "
            "của chính mình — kể cả quản trị viên cũng không đổi hộ mật "
            "khẩu của người khác.",
            "Hệ thống không hiển thị mật khẩu cũ dưới bất kỳ dạng nào, kể "
            "cả khi người dùng đã nhập đúng nó.",
        ],
    ),
    (
        "Khai báo thông tin cá nhân và tình trạng sức khỏe",
        "Người dùng",
        "Cao",
        "người dùng",
        "khai báo giới tính, ngày sinh, chiều cao, cân nặng, mức vận "
        "động, mục tiêu cân nặng, bệnh lý và dị ứng",
        "hệ thống tính đúng nhu cầu năng lượng và loại bỏ những món không "
        "an toàn với tôi",
        "Người dùng điền biểu mẫu hồ sơ và chọn các bệnh lý, dị ứng đang "
        "có (hoặc chọn “Không có”).",
        [
            "Hồ sơ đã đủ giới tính, ngày sinh, chiều cao, cân nặng và mức "
            "vận động thì khi lưu, hệ thống tính BMI, chuyển hóa cơ bản "
            "theo công thức Mifflin-St Jeor, tổng năng lượng tiêu hao và "
            "hạn mức năng lượng mỗi ngày.",
            "Người dùng chọn được nhiều bệnh lý và nhiều loại dị ứng cùng "
            "lúc.",
            "Mỗi lần hồ sơ thay đổi, hạn mức năng lượng và các ràng buộc "
            "dinh dưỡng được tính lại ngay, không chờ tới lần sinh thực "
            "đơn sau.",
        ],
        [
            "Chiều cao nhận giá trị 50–250 cm, cân nặng 20–300 kg. Ngoài "
            "khoảng thì báo lỗi và không lưu.",
            "Ba tỷ lệ đạm – bột đường – béo phải cộng lại đúng 100 %.",
            "Bệnh lý và dị ứng đã khai là đầu vào bắt buộc của Bộ lọc F1 "
            "ở các User story phía sau.",
        ],
    ),
    (
        "Lựa chọn món ăn yêu thích",
        "Người dùng",
        "Cao",
        "người dùng mới",
        "chọn những món tôi thích hoặc không thích trong một bộ món khảo "
        "sát",
        "hệ thống hiểu khẩu vị của tôi ngay từ lần dùng đầu tiên, không "
        "phải chờ tích lũy lịch sử",
        "Người dùng lần lượt chọn mức độ yêu thích cho từng món trong bộ "
        "khảo sát.",
        [
            "Người dùng đã khai bệnh lý và dị ứng thì mọi món hiện ra "
            "trong phiên khảo sát đều đã qua Bộ lọc F1 — không món nào "
            "chứa dị nguyên người dùng đã khai.",
            "Mỗi món có bốn lựa chọn: Thích, Bình thường, Không thích và "
            "Chưa từng ăn.",
            "Kết thúc phiên, hệ thống dựng vector sở thích 20 chiều gồm "
            "tỷ lệ ba chất sinh năng lượng, năng lượng, vị ngọt, vị mặn, "
            "chất xơ, mức cay và nhóm món.",
            "Người dùng làm lại phiên khảo sát được; vector được tính lại "
            "từ toàn bộ lượt chọn mới nhất.",
        ],
        [
            "Lựa chọn “Chưa từng ăn” bị loại khỏi phép tính, không quy về "
            "mức trung bình: người dùng nói chưa từng ăn là không có "
            "thông tin về khẩu vị, khác hẳn với thấy bình thường.",
        ],
    ),
    (
        "Xem thực đơn ngày",
        "Người dùng",
        "Cao",
        "người dùng",
        "xem thực đơn gợi ý cho cả ngày, chia theo bữa sáng, trưa, tối và "
        "bữa phụ",
        "biết hôm nay nên ăn gì mà không phải tự tính toán dinh dưỡng",
        "Người dùng mở màn hình thực đơn của ngày hiện tại.",
        [
            "Thực đơn có đủ bốn bữa, mỗi bữa có cấu trúc hợp lý với món "
            "chính, món mặn, món rau và món canh.",
            "Danh mục món không đủ để thỏa một ngưỡng và hệ thống đã thử "
            "hết các phép thay món thì thực đơn vẫn được trình bày nhưng "
            "kèm cảnh báo ghi rõ ngưỡng nào chưa đạt và số liệu thực tế "
            "là bao nhiêu — không trình bày như đã đạt.",
            "Mỗi món hiển thị tên, năng lượng và ba chất sinh năng lượng.",
        ],
        [
            "Tổng năng lượng cả ngày lệch không quá 10 % so với hạn mức "
            "tính từ hồ sơ sức khỏe.",
            "Không món nào trong thực đơn vi phạm ràng buộc dị ứng hoặc "
            "chế độ ăn mà người dùng đã khai.",
            "Các ngưỡng dinh dưỡng của bệnh lý được kiểm trên tổng CẢ "
            "NGÀY chứ không trên từng món, ví dụ natri dưới 2000 mg mỗi "
            "ngày với người tăng huyết áp.",
        ],
    ),
    (
        "Xem chi tiết món ăn",
        "Người dùng",
        "Trung bình",
        "người dùng",
        "xem chi tiết thành phần dinh dưỡng và nhãn của một món",
        "tự đánh giá món đó có phù hợp với mình không trước khi quyết "
        "định ăn",
        "Người dùng chọn một món trong thực đơn hoặc trong danh mục.",
        [
            "Hiển thị khẩu phần, năng lượng, đạm, bột đường, béo, chất "
            "xơ, đường, natri, cholesterol, canxi, sắt, kẽm, vitamin A và "
            "vitamin C.",
            "Hiển thị đầy đủ nhãn của món theo ba nhóm: dị nguyên, chế độ "
            "ăn và dinh dưỡng.",
            "Món chứa dị nguyên người dùng đã khai thì khi mở chi tiết, "
            "hệ thống hiển thị cảnh báo nổi bật ngay đầu màn hình.",
            "Với những chất có trong bảng nhu cầu khuyến nghị, hiển thị "
            "thêm tỷ lệ phần trăm so với nhu cầu mỗi ngày của chính người "
            "dùng đó.",
        ],
        [
            "Chất nào bảng thành phần thực phẩm không công bố thì hiển "
            "thị “chưa có số liệu”, không hiển thị số 0 — thiếu số liệu "
            "khác hẳn với bằng không.",
        ],
    ),
    (
        "Đổi món ăn trong thực đơn",
        "Người dùng",
        "Cao",
        "người dùng",
        "đổi một món trong thực đơn sang món khác",
        "thực đơn hợp với nguyên liệu sẵn có và tâm trạng ăn uống của tôi "
        "hôm đó",
        "Người dùng chọn một suất trong thực đơn và yêu cầu đổi món.",
        [
            "Chọn một suất trong thực đơn rồi bấm “Đổi món” thì hệ thống "
            "hiển thị danh sách món thay thế cùng vai trò trong bữa, xếp "
            "theo điểm phù hợp giảm dần.",
            "Thao tác đổi sinh ra hai tín hiệu huấn luyện cùng lúc: món "
            "bị bỏ nhận nhãn ưa thích thấp, món được chọn nhận nhãn cao.",
        ],
        [
            "Mọi món thay thế đều đã qua Bộ lọc F1.",
            "Sau khi đổi, tổng năng lượng cả ngày được tính lại và vẫn "
            "phải nằm trong ngưỡng lệch 10 %.",
            "Món đã có trong thực đơn không xuất hiện ở danh sách thay "
            "thế của suất khác, để một ngày không bị trùng món.",
        ],
    ),
    (
        "Thêm món ăn của tôi vào thực đơn",
        "Người dùng",
        "Trung bình",
        "người dùng hay ăn những món không có trong danh mục chung",
        "tự thêm món của mình và đưa được món đó vào thực đơn",
        "thực đơn sát với những gì tôi thực sự nấu và ăn, thay vì phải "
        "chọn một món gần giống",
        "Người dùng khai tên món, nhóm món, vai trò trong bữa, khẩu phần "
        "và thành phần dinh dưỡng, rồi chọn món đó cho một suất trong "
        "thực đơn.",
        [
            "Món do người dùng thêm chỉ mình người đó nhìn thấy: không "
            "xuất hiện trong danh mục chung và không được gợi ý cho bất "
            "kỳ người dùng nào khác.",
            "Thêm xong, món xuất hiện ngay trong danh sách thay thế khi "
            "đổi món, ở đúng vai trò trong bữa đã khai.",
            "Tên món riêng được phép trùng với món trong danh mục chung — "
            "hai người nấu “Canh chua” theo hai cách là chuyện thường; hệ "
            "thống chỉ cấm trùng tên trong phạm vi món của chính người đó.",
            "Người dùng sửa và ngừng dùng món của mình; món đã ngừng vẫn "
            "còn nguyên trong thực đơn cũ và nhật ký ăn uống.",
        ],
        [
            "Bắt buộc có: tên món, nhóm món, vai trò trong bữa, khẩu phần, "
            "năng lượng, đạm, bột đường và béo. Chất nào bỏ trống thì hiển "
            "thị “chưa có số liệu”.",
            "Người dùng phải tự gắn nhãn dị nguyên cho món của mình. "
            "Thiếu nhãn thì Bộ lọc F1 không có căn cứ để loại món, nên hệ "
            "thống cảnh báo trước khi lưu.",
            "Món riêng vẫn chịu đúng các ngưỡng dinh dưỡng theo ngày như "
            "món trong danh mục chung.",
        ],
    ),
    (
        "Đánh giá món ăn trong thực đơn",
        "Người dùng",
        "Trung bình",
        "người dùng",
        "chấm điểm và viết nhận xét cho món đã ăn",
        "những lần gợi ý sau sát với khẩu vị của tôi hơn",
        "Người dùng chọn số sao và nhập nhận xét cho một món đã có trong "
        "thực đơn.",
        [
            "Đánh giá được dùng làm mẫu huấn luyện và được phản ánh vào "
            "vector khẩu vị ở lần sinh thực đơn kế tiếp.",
            "Người dùng xem lại và sửa được đánh giá của chính mình.",
        ],
        [
            "Điểm đánh giá nhận giá trị từ 1 đến 5 sao; ngoài khoảng này "
            "hệ thống từ chối lưu.",
            "Nhận xét là tùy chọn, tối đa 1000 ký tự.",
            "Mỗi người dùng chỉ có một đánh giá cho mỗi món; đánh giá lại "
            "sẽ ghi đè đánh giá cũ chứ không tạo thêm dòng mới.",
        ],
    ),
    (
        "Ghi nhật ký ăn uống",
        "Người dùng",
        "Cao",
        "người dùng",
        "ghi lại những món tôi đã thực sự ăn trong ngày và ăn bao nhiêu "
        "suất",
        "hệ thống biết tôi có ăn theo thực đơn hay không và không gợi lại "
        "món tôi vừa ăn hôm trước",
        "Người dùng chọn món đã ăn, chọn bữa và nhập số suất đã ăn.",
        [
            "Người dùng ghi được cả món có trong thực đơn hôm đó lẫn món "
            "ăn ngoài thực đơn.",
            "Mỗi bản ghi gồm ngày ăn, bữa (sáng, trưa, tối, bữa phụ), món "
            "và số suất đã ăn.",
            "Số suất nhập theo phần ăn chứ không theo gam: 0,5 là nửa "
            "suất, 1,5 là suất lớn. Người dùng biết mình ăn hết một tô "
            "hay nửa tô, chứ không biết tô đó nặng bao nhiêu gam.",
            "Người dùng xem lại, sửa và xóa được bản ghi của chính mình.",
            "Màn hình nhật ký hiển thị tổng năng lượng và ba chất sinh "
            "năng lượng đã nạp trong ngày, đặt cạnh hạn mức tính từ hồ sơ "
            "sức khỏe.",
        ],
        [
            "Số suất nhận giá trị từ 0,1 đến 5.",
            "Nhật ký là nguồn số liệu duy nhất cho hai việc: tính tỷ lệ "
            "tuân thủ thực đơn ở màn hình thống kê, và loại những món đã "
            "ăn gần đây ra khỏi danh sách gợi ý.",
            "Món đã ngừng hiển thị vẫn còn nguyên trong nhật ký cũ; vì "
            "vậy món chỉ được xóa mềm, không xóa khỏi cơ sở dữ liệu.",
        ],
    ),
    (
        "Theo dõi tình trạng cơ thể",
        "Người dùng",
        "Trung bình",
        "người dùng đang theo một mục tiêu cân nặng",
        "ghi lại cân nặng theo thời gian và xem nó thay đổi ra sao",
        "biết mình có đang đi đúng hướng không, và hệ thống tính lại hạn "
        "mức năng lượng theo thể trạng hiện tại chứ không theo số đã khai "
        "từ ngày đăng ký",
        "Người dùng nhập cân nặng của ngày hôm đó và xem biểu đồ diễn "
        "biến.",
        [
            "Lưu cân nặng mới thì hệ thống tính lại ngay BMI, chuyển hóa "
            "cơ bản, tổng năng lượng tiêu hao và hạn mức năng lượng mỗi "
            "ngày theo số mới.",
            "Màn hình hiển thị biểu đồ cân nặng và BMI theo thời gian, "
            "kèm mốc cân nặng mục tiêu.",
            "Hiển thị phân loại thể trạng theo ngưỡng BMI dành cho người "
            "châu Á.",
            "Người dùng ghi kèm một ghi chú ngắn cho mỗi lần cân.",
        ],
        [
            "Mỗi ngày tối đa một bản ghi. Cân lại trong cùng ngày thì ghi "
            "đè bản cũ, không tạo thêm một điểm nữa trên biểu đồ.",
            "Cân nặng nhận giá trị từ 20 đến 300 kg.",
            "Chỉ ghi cân nặng, không ghi chiều cao: chiều cao người "
            "trưởng thành gần như không đổi nên lấy từ hồ sơ sức khỏe. Hệ "
            "quả là BMI của các mốc cũ được tính bằng chiều cao hiện tại.",
        ],
    ),
    (
        "Cập nhật thông tin món ăn",
        "Quản trị viên",
        "Cao",
        "quản trị viên",
        "thêm, sửa và ngừng hiển thị món ăn cùng số liệu dinh dưỡng của "
        "chúng",
        "danh mục món luôn đúng và đủ cho bộ sinh thực đơn hoạt động",
        "Quản trị viên nhập hoặc chỉnh sửa thông tin món qua giao diện "
        "quản trị.",
        [
            "Khi lưu số liệu dinh dưỡng, hệ thống đối chiếu năng lượng "
            "khai báo với công thức Atwater (4 × đạm + 4 × bột đường + "
            "9 × béo) và cảnh báo nếu lệch quá 12 %.",
            "Quản trị viên gắn được nhãn dị nguyên, chế độ ăn và dinh "
            "dưỡng cho món. Nhãn dị nguyên phải khớp với nguyên liệu, vì "
            "đây là căn cứ duy nhất để Bộ lọc F1 loại món.",
            "Mọi thay đổi có hiệu lực ngay ở lần sinh thực đơn kế tiếp.",
        ],
        [
            "Thêm món cần tối thiểu: tên món, nhóm món, vai trò trong "
            "bữa, khẩu phần, năng lượng, đạm, bột đường và béo.",
            "Tên món không được trùng trong danh mục chung.",
            "Món không dùng nữa thì ngừng hiển thị (xóa mềm), không xóa "
            "khỏi cơ sở dữ liệu: thực đơn cũ và nhật ký ăn uống của người "
            "dùng vẫn trỏ tới món đó.",
        ],
    ),
    (
        "Quản lý bệnh lý và ngưỡng dinh dưỡng",
        "Quản trị viên",
        "Cao",
        "quản trị viên",
        "thêm và sửa các bệnh lý cùng bộ quy tắc dinh dưỡng đi kèm",
        "Bộ lọc F1 bám theo khuyến nghị y khoa mới nhất mà không phải sửa "
        "mã nguồn",
        "Quản trị viên chọn một bệnh lý và chỉnh các quy tắc lọc của bệnh "
        "lý đó.",
        [
            "Mỗi quy tắc khai được: loại quy tắc (giới hạn chất, loại "
            "nhãn, bắt buộc nhãn), chất hoặc nhãn áp dụng, phép so sánh, "
            "ngưỡng, phạm vi áp dụng và mức độ bệnh tối thiểu.",
            "Quy tắc đánh dấu là cứng thì món vi phạm bị loại hẳn; quy "
            "tắc mềm chỉ bị trừ điểm phù hợp.",
            "Trước khi lưu, hệ thống thử áp quy tắc mới lên toàn bộ danh "
            "mục và báo số món còn lại ở từng vai trò trong bữa.",
            "Quy tắc làm một vai trò nào đó không còn món nào thì hệ "
            "thống cảnh báo rõ, vì khi đó không dựng nổi thực đơn cho "
            "người mang bệnh lý này.",
        ],
        [
            "Mỗi quy tắc phải ghi nguồn của ngưỡng vào ô ghi chú, ví dụ "
            "WHO cho natri hay KDIGO cho đạm. Ngưỡng không có nguồn thì "
            "không lưu.",
            "Ngưỡng cứng khai theo tổng cả ngày, ngưỡng mềm khai theo "
            "từng suất: mọi hướng dẫn y khoa đều phát biểu theo ngày, đặt "
            "ngưỡng cứng theo suất sẽ loại gần hết danh mục.",
            "Không xóa được bệnh lý đang có người dùng khai.",
            "Sửa quy tắc có hiệu lực ngay ở lần sinh thực đơn kế tiếp, "
            "không làm đổi những thực đơn đã sinh trước đó.",
        ],
    ),
    (
        "Quản lý tài khoản người dùng",
        "Quản trị viên",
        "Trung bình",
        "quản trị viên",
        "xem danh sách tài khoản và khóa hoặc mở lại một tài khoản",
        "xử lý được tài khoản vi phạm mà không làm mất dữ liệu đã tích "
        "lũy",
        "Quản trị viên tra cứu tài khoản và đổi trạng thái hoạt động của "
        "tài khoản đó.",
        [
            "Danh sách hiển thị email, tên, vai trò, trạng thái và thời "
            "điểm tạo; tìm kiếm được theo email hoặc tên.",
            "Khóa tài khoản chỉ đổi trạng thái sang ngừng hoạt động: "
            "người đó không đăng nhập được nhưng toàn bộ dữ liệu vẫn còn.",
        ],
        [
            "Hệ thống không cho xóa cứng tài khoản. Xóa sẽ kéo theo nhật "
            "ký, đánh giá và mẫu huấn luyện của người đó, làm hỏng tính "
            "tái lập của tập dữ liệu đã đóng băng để huấn luyện mô hình.",
            "Quản trị viên không tự khóa được tài khoản của chính mình.",
            "Hệ thống không hiển thị mật khẩu dưới bất kỳ dạng nào, kể cả "
            "với quản trị viên.",
        ],
    ),
    (
        "Xem số liệu phân tích người dùng",
        "Quản trị viên",
        "Trung bình",
        "quản trị viên",
        "xem thống kê tổng hợp về người dùng của hệ thống",
        "biết hệ thống đang phục vụ những ai và nhóm nào còn chưa được "
        "phục vụ tốt",
        "Quản trị viên mở màn hình thống kê người dùng và chọn khoảng "
        "thời gian.",
        [
            "Hiển thị tổng số tài khoản, số tài khoản đang hoạt động và "
            "số người đã hoàn tất phiên khảo sát khẩu vị.",
            "Hiển thị phân bố theo giới tính, nhóm tuổi, mục tiêu cân "
            "nặng và bệnh lý đã khai.",
            "Hiển thị tỷ lệ thực đơn sinh ra đạt ngưỡng lệch năng lượng "
            "10 %, và tỷ lệ người dùng thực sự ăn theo thực đơn, lấy từ "
            "nhật ký ăn uống.",
            "Lọc được theo khoảng thời gian.",
        ],
        [
            "Số liệu chỉ trình bày ở dạng tổng hợp, không hiển thị thông "
            "tin định danh của bất kỳ cá nhân nào.",
        ],
    ),
    (
        "Xem số liệu phân tích món ăn",
        "Quản trị viên",
        "Trung bình",
        "quản trị viên",
        "xem thống kê về danh mục món ăn",
        "biết món nào được ưa chuộng, món nào bị đổi nhiều và nhóm món "
        "nào còn thiếu",
        "Quản trị viên mở màn hình thống kê món ăn và chọn tiêu chí xếp "
        "hạng.",
        [
            "Xếp hạng món theo số lượt thích, số lượt bị đổi và điểm đánh "
            "giá trung bình.",
            "Thống kê số món theo nhóm món và theo vai trò trong bữa.",
            "Chọn một chế độ ăn hoặc một bệnh lý thì thống kê hiển thị số "
            "món còn lại ở từng vai trò sau khi lọc và cảnh báo vai trò "
            "nào không đủ để dựng một ngày ăn.",
            "Thống kê độ phủ số liệu của từng chất dinh dưỡng trong danh "
            "mục, để biết chất nào còn thiếu nhiều.",
            "Lọc được theo khoảng thời gian và xuất được kết quả ra tệp.",
        ],
        [
            "Thống kê chỉ tính trên danh mục chung. Món riêng của từng "
            "người dùng không gộp vào, vì đó là dữ liệu cá nhân.",
        ],
    ),
]
