# Thử nghiệm với người dùng thật (2 đến 3 người)

Mục đích: có bằng chứng "đã có người dùng thử" trước khi thi, và biết chỗ nào khó hiểu. Chỉ dùng **bộ dữ liệu minh hoạ** (không có khách hàng thật), mỗi người thử khoảng 15 phút.

## Chọn ai
| Người | Vì sao | Cho họ xem |
|---|---|---|
| 1 trưởng phòng Kinh doanh của một team | Họ nhận tin tổng hợp việc của team và giao cho sale | Tin Zalo giả lập, chọn nhiều việc và giao, hồ sơ hợp đồng |
| 1 trưởng nhóm hoặc trưởng phòng DVKH | Họ nhận việc "khách có ý rời", "sự cố lặp" và giao cho CSKH | Phân loại khách hàng, giao việc, hồ sơ hợp đồng |
| 1 điều hành hoặc trưởng phòng Kỹ thuật | Họ nhận việc chờ lắp, sự cố lặp và giao cho KTV | Tồn và lịch hẹn, Chậm do ai, tin Zalo giả lập, giao việc |

## Cách làm (mỗi người)
1. Mở máy: `python scripts/xem_demo_lien_khoi.py`, vào http://127.0.0.1:8060/lienkhoi (hoặc /kt cho người Kỹ thuật). Bấm **Chuẩn bị demo** ở tab Theo dõi & Zalo.
2. Nói một câu: "Đây là dữ liệu mẫu, không phải khách thật. Anh/chị cứ làm theo cách tự nhiên, em không hướng dẫn trước."
3. Giao 3 việc, **không chỉ đường**, ghi thời gian từng việc:
   - "Tìm 3 hợp đồng anh/chị phải xử lý đầu tiên hôm nay."
   - "Cho biết hợp đồng MHAAA0090 đang vướng ở đâu."
   - (Người Kỹ thuật) "Ca nào đang chờ khách, ca nào chờ mình?"
4. Bấm **Gửi việc mới qua Zalo**, cho họ đọc tin tổng hợp của chính họ trong hộp thư giả lập, rồi nhờ họ vào tab Theo dõi, chọn tên mình ở ô **Tôi là**, chọn 3 việc và giao cho một nhân viên. Ghi thời gian và chỗ họ vấp.

## Hỏi sau khi thử (ghi nguyên văn câu trả lời)
1. Có việc nào hệ thống đưa mà anh/chị đã biết từ trước? Có việc nào mới?
2. Việc nào đưa sai người hoặc sai lý do?
3. Tin nhắn Zalo có đủ để làm ngay không, thiếu gì?
4. Anh/chị có chịu vào app giao việc và cập nhật hằng ngày không? Cần bớt thao tác nào?
5. Nếu được nhận việc kiểu này mỗi sáng, anh/chị thấy hữu ích hay phiền? Điểm 1 đến 5.
6. Công cụ tra cứu khách hàng hiện có (CUS 360, bot Zalo công ty) đang làm được những việc này chưa?

## Ghi lại để đưa vào slide
- Số người thử, vai trò, ngày thử.
- Thời gian trung bình tìm ra "việc phải làm đầu tiên" (so với cách họ làm hiện tại, nếu hỏi được).
- Ba câu nhận xét nguyên văn (có xin phép trích dẫn).
- Điều hệ thống làm sai hoặc thiếu, và sẽ sửa gì.

Không đưa màn hình có số điện thoại, tên khách hoặc dữ liệu thật vào ảnh chụp hay slide.
