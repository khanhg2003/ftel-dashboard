"""Trang Hướng dẫn sử dụng - viết cho người lần đầu mở app, không dùng từ kỹ thuật."""
from __future__ import annotations

from dash import dcc, html

from app.ui.components import card
from app.ui.icons import icon


def topbar():
    return [html.Div([html.H1("Hướng dẫn sử dụng"),
                      html.Div("Quy trình hằng ngày, ý nghĩa từng màn hình và cách xử lý "
                               "sự cố", className="sub")])]


def _buoc(so: str, tieu_de: str, noi_dung):
    return html.Div([
        html.Div(so, className="buoc-so"),
        html.Div([html.Div(tieu_de, className="buoc-ten"),
                  html.Div(noi_dung, className="buoc-noi-dung")]),
    ], className="buoc")


def _muc(tieu_de: str, cau_hoi: str, noi_dung):
    return html.Div([
        html.Div(tieu_de, className="hd-ten"),
        html.Div(cau_hoi, className="hd-hoi"),
        html.Div(noi_dung, className="hd-noi"),
    ], className="hd-muc")


def layout():
    return html.Div([
        card([
            html.P("Hệ thống thay cho file Google Sheet báo cáo hằng ngày: nạp 3 file export "
                   "quen thuộc, toàn bộ chỉ số được tính lại theo đúng mẫu báo cáo đang dùng.",
                   className="hd-mo-dau"),
            html.Div([
                _buoc("1", "Nạp dữ liệu", [
                    "Vào ", html.B("Nạp dữ liệu"), ", chọn cùng lúc 3 file export (Internet, Truyền "
                    "hình, Camera) rồi bấm ", html.B("Lưu tất cả vào hệ thống"), ". Đầu tháng nạp thêm "
                    "file NSLĐ - app tự nhận tháng từ nội dung file."]),
                _buoc("2", "Kiểm tra dữ liệu", [
                    "Mở ", html.B("Chất lượng dữ liệu"), ": 6 mục kiểm tra (đủ 3 file cùng ngày, hợp "
                    "đồng chưa gán phòng, acc lạ, NSLĐ, danh mục sai…). Mục nào chưa ổn có sẵn cách "
                    "xử lý."]),
                _buoc("3", "Xem và gửi báo cáo", [
                    "Vào ", html.B("Báo cáo Tổng"), ", bấm ", html.B("Chụp ảnh (PNG)"),
                    " để có ảnh đầy đủ gửi nhóm, hoặc ", html.B("Excel"), " nếu cần tính tiếp."]),
            ], className="buoc-list"),
        ], title="Quy trình hằng ngày"),

        card([
            html.Div([
                _muc("Báo cáo Tổng", "Bức tranh của cả kỳ, theo phòng", [
                    "Mỗi dòng một phòng, cuối mỗi bầy có dòng tổng, tiếp theo là Tổng DNG, Tổng QNM "
                    "và tổng toàn chi nhánh. Chọn ", html.B("kỳ báo cáo từ ngày - đến ngày"),
                    " (mặc định luỹ kế từ ngày 01) hoặc dùng Chọn nhanh; cột Cùng kỳ là cùng khoảng "
                    "ngày tháng trước. Nhóm cột cuối là kết quả riêng của ngày cuối kỳ. Màu ô: xanh "
                    "đạt, vàng sát ngưỡng, đỏ cần xử lý."]),
                _muc("Báo cáo phòng", "Trưởng phòng theo dõi phòng và từng nhân sự", [
                    "Sáu chỉ số và hạng của phòng, bảng nhân sự xếp hạng trong phòng, mức cần chú ý "
                    "của từng người (Trao đổi ngay / Theo dõi - xem mục Thuật ngữ). Bấm một người để xem chi "
                    "tiết. Nút ", html.B("Chụp ảnh"), " tạo ảnh gửi nhóm Zalo của phòng. Trưởng phòng "
                    "chỉ xem được phòng mình phụ trách."]),
                _muc("Phân tích bán hàng", "Bán có tốt không, đang tắc ở đâu", [
                    "Tỷ lệ bán kèm V.VIP / Camera, trả trước, online trong 1 ngày theo từng phòng và "
                    "nhân viên - màu so với mức chung chi nhánh. Mục ", html.B("Số tồn theo thời "
                    "gian chờ"), " có danh sách hợp đồng chờ từ 7 ngày để đôn đốc."]),
                _muc("Diễn biến & So sánh", "Số đi thế nào theo thời gian", [
                    html.B("Tab 1 Theo từng ngày"), ": mỗi cột là một ngày, màu ô so với mức trung bình "
                    "của chính phòng đó (xanh ngày tốt, đỏ ngày hụt). ", html.B("Tab 2 So sánh hai kỳ"),
                    ": chọn hai khoảng ngày (có nút gợi ý), xem chênh lệch theo phòng và Top giảm sâu "
                    "nhất - danh sách cần trao đổi trước."]),
                _muc("Nhân sự & NSLĐ", "Năng suất theo từng người", [
                    "Chọn phòng ở thanh lọc. Tab 1 Bán hàng trong kỳ: luỹ kế đến ngày chọn. "
                    "Tab 2 NSLĐ: NSLĐ ITN theo tháng (tổng ITN / số người được xét) và NSLĐ tân binh "
                    "theo tháng làm việc (Tháng thứ 1, 2, 3…). Để tất cả phòng thì xem theo phòng, chọn "
                    "một phòng thì tự xem từng nhân sự. Mục ",
                    html.B("Cần trao đổi sớm"), " dùng cùng quy tắc với Báo cáo phòng và ghi sẵn lý do "
                    "từng người. Cột ", html.B("So với cùng thâm niên"),
                    " cho biết người đó bán hơn hay kém người cùng mốc thâm niên."]),
                _muc("Chất lượng dữ liệu", "Soát lỗi trước khi chốt số", [
                    "6 mục: dữ liệu mới nhất của 3 file, hợp đồng chưa gán phòng, ngày thiếu dữ liệu, "
                    "acc cần xem, nhân sự kinh doanh thiếu NSLĐ, danh mục khai sai hoặc trùng. Đầu "
                    "trang ghi số mục ổn và danh sách việc cần làm."]),
                _muc("Nạp dữ liệu", "Đưa file export vào hệ thống",
                     "Chọn nhiều file cùng lúc, xem trước rồi mới lưu; kết quả lưu hiện ngay dưới nút "
                     "Lưu. File export 3 "
                     "tháng nạp lại bao nhiêu lần cũng không nhân đôi số: hợp đồng đã có được cập "
                     "nhật, tháng nào tự về tháng đó theo Ngày online. Cuối trang là lịch sử nạp - "
                     "nạp nhầm thì gỡ bỏ ở đây."),
                _muc("Quản trị", "Chỉ Quản trị (BGĐ)",
                     "5 tab: Tài khoản (cấp theo vai trò, Trưởng phòng chọn phòng phụ trách) · Danh mục "
                     "nhân sự (acc người bán thuộc phòng nào) · Cơ cấu tổ chức (bầy, phòng, cơ cấu theo "
                     "tháng) · Chỉ tiêu tháng · Nhật ký thao tác. Thay đổi nhiều thì Tải file mẫu → sửa → "
                     "Import Excel."),
            ], className="hd-list"),
        ], title="Các màn hình chính"),

        card([
            html.Div([
                _muc("Bộ lọc đi theo khi chuyển trang", "", [
                    "Chọn kỳ báo cáo, chi nhánh, phòng ở trang nào thì sang trang khác vẫn giữ. Đường "
                    "dẫn trên trình duyệt ghi sẵn lựa chọn đó - ", html.B("gửi link"),
                    " là người nhận mở đúng kỳ bạn đang xem (vẫn theo quyền của người nhận)."]),
                _muc("Bấm tên phòng để xem chi tiết", "", [
                    "Ở Báo cáo Tổng, Diễn biến & So sánh, Phân tích bán hàng: bấm tên một phòng để mở ",
                    html.B("Báo cáo phòng"), " của phòng đó. Trong Báo cáo phòng, bấm một nhân sự để mở "
                    "chi tiết người đó."]),
                _muc("Dòng tình trạng dữ liệu", "", [
                    "Góc trên bên phải mọi trang ghi số đến ngày nào. Hiện ô vàng khi có file nạp thiếu "
                    "ngày (vd Camera mới đến hôm qua) - bấm vào để mở Chất lượng dữ liệu."]),
                _muc("Rê chuột lên chữ viết tắt", "", "Tiêu đề cột và ô chỉ số có HTKH, PTTB, V.VIP, CNQL, "
                                                      "NSLĐ... hiện giải thích khi rê chuột."),
                _muc("Trưởng phòng", "", "Đăng nhập là vào thẳng Báo cáo phòng của mình."),
            ], className="hd-list"),
        ], title="Mẹo dùng nhanh"),

        card([
            html.Div([
                _muc("Số online", "", "Hợp đồng đã online, khách bắt đầu sử dụng - cơ sở "
                                          "tính thành tích."),
                _muc("Số tồn", "", "Đã ký hợp đồng nhưng chưa online, và còn nằm trong file mới nhất."),
                _muc("V.VIP", "", "Hợp đồng có gói truyền hình V.VIP, đã gồm cả V.VIP Plus."),
                _muc("PTTB CNQL", "", "Hợp đồng do chi nhánh quản lý sau bán."),
                _muc("Bầy", "", "Nhóm nhiều phòng kinh doanh, xếp lại được theo từng tháng."),
                _muc("Acc inside", "", "Tài khoản nhân viên trên hệ thống bán hàng "
                                       "(vd: DNG.HongDTA3) - căn cứ gán hợp đồng về phòng."),
                _muc("Tỷ lệ HTKH", "", "Tỷ lệ hoàn thành chỉ tiêu tháng. Dòng tổng chi nhánh không "
                                       "cộng nhân sự và chỉ tiêu của ANCS (như Google Sheet)."),
                _muc("NSLĐ · ITN", "", "Năng suất lao động theo file NSLĐ hằng tháng; ITN là điểm "
                                       "Internet. NSLĐ phòng = tổng ITN / số người được xét."),
                _muc("Tân binh · Tháng thứ k", "", "Người vào làm trong năm đang xem. Tháng vào làm "
                                                   "là tháng thứ 1."),
                _muc("Trao đổi ngay", "", "Từ 7 ngày không có số online nào."),
                _muc("Theo dõi", "", "Từ 3 ngày liền chưa có số, tuần này giảm từ một nửa so với tuần "
                                     "trước, hoặc NSLĐ chưa đạt."),
                _muc("Kèm V.VIP / Kèm Camera", "", "Hợp đồng Internet online trong kỳ có thêm "
                                                   "V.VIP / Camera (ghép theo số hợp đồng)."),
                _muc("Bán ngoại tỉnh", "", "Khách thuộc tỉnh khác (CN Quản lý ngoài DNG/QNM) do "
                                           "mình bán online, số tính cho tỉnh khác."),
            ], className="hd-list"),
        ], title="Thuật ngữ"),

        card([
            html.Div([
                _muc("Số liệu lệch so với file Sheet cũ", "", [
                    "Mỗi hợp đồng chỉ được đếm một lần. Kỳ 01-11/09 sheet cũ ghi 1.397 số online, "
                    "hệ thống ra 1.394 - chênh do 4 dòng trùng và 1 dòng bị sót trong sheet."]),
                _muc("Hợp đồng rơi vào “Chưa gán phòng”", "", [
                    "Acc người bán chưa có trong danh mục. Vào ",
                    html.B("Quản trị → Danh mục nhân sự"), ", thêm acc, rồi bấm “Tính lại việc "
                    "gán phòng” - áp cho cả dữ liệu đã nạp trước đó. Danh sách acc cần thêm có sẵn ở "
                    "trang Chất lượng dữ liệu."]),
                _muc("Nạp nhầm file", "", [
                    html.B("Nạp dữ liệu → Lịch sử nạp"), " → tick dòng → ", html.B("Gỡ bỏ"),
                    ". Toàn bộ số của lần nạp đó được rút khỏi báo cáo."]),
                _muc("Bảng rộng hơn màn hình", "", [
                    "Ô ", html.B("Cỡ bảng"), " mặc định “Vừa màn hình”. Cần ảnh nét để gửi nhóm "
                    "thì dùng ", html.B("Chụp ảnh (PNG)"), " - ảnh luôn đủ cột."]),
                _muc("Đổi mật khẩu", "", [
                    "Bấm ", html.B("Tài khoản"), " ở cuối menu bên trái → nhập mật khẩu hiện tại và "
                    "mật khẩu mới. Nên đổi ngay mật khẩu được cấp lần đầu."]),
                _muc("Quên mật khẩu", "", [
                    "Người có quyền Quản trị vào ", html.B("Quản trị → Tài khoản người dùng"),
                    ", chọn tài khoản rồi bấm “Đặt lại mật khẩu”. Sai 5 lần liên tiếp, tài khoản "
                    "bị khoá 15 phút."]),
                _muc("Truy cập từ máy khác, điện thoại", "",
                     "Mở trình duyệt, vào địa chỉ do quản trị cung cấp và đăng nhập - không cần cài "
                     "đặt thêm. Trên điện thoại, bấm nút ☰ để mở menu."),
            ], className="hd-list"),
        ], title="Xử lý sự cố thường gặp"),

        card([
            html.P("Phải đăng nhập mới xem được. Số chung theo phòng, bầy, chi nhánh: mọi tài khoản "
                   "xem toàn chi nhánh. Chi tiết từng nhân sự: Quản trị (BGĐ) xem mọi phòng, Trưởng "
                   "phòng chỉ phòng mình phụ trách, Nhập liệu không xem. Mọi thao tác nạp, sửa, xoá, "
                   "xuất file đều được ghi nhật ký.", className="hd-noi"),
            html.Div([
                dcc.Link([icon("upload", 14), html.Span("Bắt đầu: nạp dữ liệu")],
                         href="/upload", className="btn primary"),
                dcc.Link([icon("dashboard", 14), html.Span("Xem Báo cáo Tổng")], href="/",
                         className="btn"),
            ], style={"display": "flex", "gap": "8px", "marginTop": "14px"}),
        ], title="Dữ liệu và phân quyền"),
    ])


def register(app):
    """Trang tĩnh - không cần callback."""
    return None
