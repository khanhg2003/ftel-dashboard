# Thử nghiệm với người dùng thật (2 đến 3 người)

Mục đích: có bằng chứng "đã có người dùng thử" trước khi thi, và biết chỗ nào khó hiểu. Chỉ dùng **bộ dữ liệu minh hoạ** (không có khách hàng thật), mỗi người thử khoảng 15 phút.

## Chọn ai
| Người | Vì sao | Cho họ xem |
|---|---|---|
| 1 sale hoặc trưởng phòng Kinh doanh | Họ nhận việc "chờ online lâu" và "khách có ý rời" | Việc cần làm, tin Zalo giả lập, hồ sơ hợp đồng |
| 1 nhân viên hoặc đội trưởng DVKH | Họ nhận việc "khách có ý rời", "sự cố lặp" | Phân loại khách hàng, hồ sơ hợp đồng |
| 1 KTV hoặc đội trưởng Kỹ thuật | Họ là người bị giao việc và bị nhắc | Tồn và lịch hẹn, Chậm do ai, tin Zalo giả lập |

## Cách làm (mỗi người)
1. Mở máy: `python scripts/xem_demo_lien_khoi.py`, vào http://127.0.0.1:8060/lienkhoi (hoặc /kt cho người Kỹ thuật). Bấm **Chuẩn bị demo** ở tab Theo dõi & Zalo.
2. Nói một câu: "Đây là dữ liệu mẫu, không phải khách thật. Anh/chị cứ làm theo cách tự nhiên, em không hướng dẫn trước."
3. Giao 3 việc, **không chỉ đường**, ghi thời gian từng việc:
   - "Tìm 3 hợp đồng anh/chị phải xử lý đầu tiên hôm nay."
   - "Cho biết hợp đồng MHAAA0090 đang vướng ở đâu."
   - (Người Kỹ thuật) "Ca nào đang chờ khách, ca nào chờ mình?"
4. Với người nhận việc: bấm **Gửi việc mới qua Zalo** rồi cho họ đọc tin của chính họ trong hộp thư giả lập, hỏi có hiểu việc gì, hạn nào không.

## Hỏi sau khi thử (ghi nguyên văn câu trả lời)
1. Có việc nào hệ thống đưa mà anh/chị đã biết từ trước? Có việc nào mới?
2. Việc nào đưa sai người hoặc sai lý do?
3. Tin nhắn Zalo có đủ để làm ngay không, thiếu gì?
4. Anh/chị có chịu nhắn "xong / không làm được" mỗi lần không? Nếu không thì vì sao?
5. Nếu được nhận việc kiểu này mỗi sáng, anh/chị thấy hữu ích hay phiền? Điểm 1 đến 5.
6. Công cụ tra cứu khách hàng hiện có (CUS 360, bot Zalo công ty) đang làm được những việc này chưa?

## Ghi lại để đưa vào slide
- Số người thử, vai trò, ngày thử.
- Thời gian trung bình tìm ra "việc phải làm đầu tiên" (so với cách họ làm hiện tại, nếu hỏi được).
- Ba câu nhận xét nguyên văn (có xin phép trích dẫn).
- Điều hệ thống làm sai hoặc thiếu, và sẽ sửa gì.

Không đưa màn hình có số điện thoại, tên khách hoặc dữ liệu thật vào ảnh chụp hay slide.
