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
                    "Vào ", html.B("Nạp dữ liệu"), ", chọn 3 file export (Internet, Truyền hình, "
                    "Camera) rồi bấm Lưu. Đầu tháng nạp thêm file NSLĐ kèm tháng tương ứng."]),
                _buoc("2", "Hệ thống xử lý", [
                    "Loại dữ liệu được nhận diện theo tên cột, số liệu được gán về phòng theo acc "
                    "người bán. Dòng lỗi hoặc trùng đều được liệt kê rõ, không bỏ qua âm thầm."]),
                _buoc("3", "Xem và gửi báo cáo", [
                    "Vào ", html.B("Báo cáo Tổng"), ", bấm ", html.B("Chụp ảnh (PNG)"),
                    " để có ảnh đầy đủ gửi nhóm, hoặc ", html.B("Excel"), " nếu cần tính tiếp."]),
            ], className="buoc-list"),
        ], title="Quy trình hằng ngày"),

        card([
            html.Div([
                _muc("Báo cáo Tổng", "Bức tranh của cả kỳ, theo phòng", [
                    "Mỗi dòng một phòng, cuối mỗi bầy có dòng tổng, dưới cùng là tổng chi nhánh. ",
                    html.B("Số liệu cộng dồn"), " từ ngày 01 đến ngày đang chọn; nhóm cột cuối là "
                    "kết quả riêng của ngày đó. Màu ô: xanh đạt, vàng sát ngưỡng, đỏ cần xử lý."]),
                _muc("Báo cáo phòng", "Trưởng phòng theo dõi phòng và từng nhân sự", [
                    "Sáu chỉ số và hạng của phòng, bảng nhân sự xếp hạng trong phòng, người cần chú ý "
                    "(nhiều ngày chưa có số, tuần sụt, hợp đồng chờ lâu). Bấm một người để xem chi "
                    "tiết. Nút ", html.B("Chụp ảnh"), " tạo ảnh gửi nhóm Zalo của phòng. Trưởng phòng "
                    "chỉ xem được phòng mình phụ trách."]),
                _muc("Phân tích bán hàng", "Bán có tốt không, đang tắc ở đâu", [
                    "Tỷ lệ bán kèm V.VIP / Camera, trả trước, online trong 1 ngày theo từng phòng và "
                    "nhân viên - màu so với mức chung chi nhánh. Mục ", html.B("Số tồn theo thời "
                    "gian chờ"), " có danh sách hợp đồng chờ từ 7 ngày để đôn đốc."]),
                _muc("Tracking ngày", "Diễn biến từng ngày của từng phòng", [
                    "Mỗi cột là một ngày. Màu ô so với mức trung bình của chính phòng đó: xanh là "
                    "ngày tốt, đỏ là ngày hụt. Đọc ngang một dòng thấy ngay phòng đang lên hay "
                    "xuống."]),
                _muc("So sánh kỳ", "Đối chiếu hai khoảng thời gian", [
                    "Chọn hai khoảng ngày (có ba nút gợi ý). Kết quả gồm chênh lệch theo phòng và ",
                    html.B("Top giảm sâu nhất"), " - danh sách cần trao đổi trước."]),
                _muc("Hiệu suất nhân sự", "Năng suất theo từng người", [
                    "Chọn phòng ở thanh lọc. Tab 1 Bán hàng trong kỳ: luỹ kế đến ngày chọn. "
                    "Tab 2 NSLĐ: NSLĐ ITN theo tháng (tổng ITN / số NVKD) và NSLĐ tân binh theo "
                    "tháng làm việc, xem theo phòng hoặc từng người. Mục ",
                    html.B("Cần trao đổi sớm"), " ghi sẵn lý do từng người: 7 ngày chưa có số, "
                    "tuần này giảm từ một nửa, NSLĐ chưa đạt. Cột ", html.B("So với cùng thâm niên"),
                    " cho biết người đó bán hơn hay kém người cùng mốc thâm niên."]),
                _muc("Chất lượng dữ liệu", "Soát lỗi trước khi chốt số", [
                    "Kiểm 5 điểm: hợp đồng chưa gán phòng, acc ngoài danh mục, ngày thiếu dữ "
                    "liệu, đơn tồn quá 7 ngày, hợp đồng đã huỷ. Mỗi mục có sẵn hướng xử lý."]),
                _muc("Nạp dữ liệu", "Đưa file export vào hệ thống",
                     "Chọn nhiều file cùng lúc, xem trước 20 dòng đầu rồi mới lưu. File export 3 "
                     "tháng nạp lại bao nhiêu lần cũng không nhân đôi số: hợp đồng đã có được cập "
                     "nhật, tháng nào tự về tháng đó theo Ngày online. Cuối trang là lịch sử nạp - "
                     "nạp nhầm thì gỡ bỏ ở đây."),
                _muc("Quản trị", "Tài khoản, danh mục nhân sự",
                     "Cấp tài khoản theo vai trò (Trưởng phòng chọn phòng phụ trách), khai acc người bán thuộc phòng nào. "
                     "Thay đổi nhiều thì Tải file mẫu → sửa → Import Excel."),
                _muc("Cấu hình", "Cơ cấu tổ chức và chỉ tiêu",
                     "Thêm bầy, thêm phòng, xếp lại cơ cấu theo từng tháng, nhập chỉ tiêu - "
                     "không cần can thiệp phần mềm."),
            ], className="hd-list"),
        ], title="Các màn hình chính"),

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
                _muc("Tỷ lệ HTKH", "", "Tỷ lệ hoàn thành chỉ tiêu tháng."),
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
                    "gán phòng” - áp cho cả dữ liệu đã nạp trước đó."]),
                _muc("Nạp nhầm file", "", [
                    html.B("Nạp dữ liệu → Lịch sử nạp"), " → tick dòng → ", html.B("Gỡ bỏ"),
                    ". Toàn bộ số của lần nạp đó được rút khỏi báo cáo."]),
                _muc("Bảng rộng hơn màn hình", "", [
                    "Ô ", html.B("Cỡ bảng"), " mặc định “Vừa màn hình”. Cần ảnh nét để gửi nhóm "
                    "thì dùng ", html.B("Chụp ảnh (PNG)"), " - ảnh luôn đủ cột."]),
                _muc("Quên mật khẩu", "", [
                    "Người có quyền Quản trị vào ", html.B("Quản trị → Tài khoản người dùng"),
                    ", chọn tài khoản rồi bấm “Đặt lại mật khẩu”. Sai 5 lần liên tiếp, tài khoản "
                    "bị khoá 15 phút."]),
                _muc("Truy cập từ máy khác", "",
                     "Mọi máy trong mạng nội bộ mở trình duyệt và vào địa chỉ do quản trị cung "
                     "cấp, không cần cài đặt thêm."),
            ], className="hd-list"),
        ], title="Xử lý sự cố thường gặp"),

        card([
            html.P("Dữ liệu lưu trên máy chủ của chi nhánh. Mỗi tài khoản chỉ thấy phạm vi "
                   "được cấp: trưởng phòng thấy phòng mình, giám đốc bầy thấy các phòng trong "
                   "bầy, Ban Giám đốc thấy toàn chi nhánh. Mọi thao tác nạp, sửa, xoá đều được "
                   "ghi nhật ký.", className="hd-noi"),
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
