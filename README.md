# StoryToFB Finder

Nhập link truyện, tool tìm bài viết Facebook xếp cao trên Google có nội dung trùng với truyện. Kết quả gồm 2 ô, mỗi ô có nút sao chép:
1. Link bài viết Facebook
2. Toàn bộ nội dung bài đăng

## Cách tool tìm

1. Đọc trang truyện, lấy **đoạn mở đầu** của phần giới thiệu.
2. Tìm đoạn đó trên Google, giống như bạn copy đoạn mở đầu dán vào google.com.
3. Duyệt kết quả theo đúng thứ hạng Google và chọn **bài Facebook xếp cao nhất có nội dung khớp truyện** (so khớp tiêu đề + đoạn trích với truyện, bỏ qua các bài Facebook không liên quan).
4. Mở bài Facebook đó (bài công khai) và lấy phần nội dung khớp truyện.

## Cài đặt

1. Bấm đúp `start.bat`, trình duyệt sẽ mở http://127.0.0.1:8765
2. Bấm nút **"Chưa có API key"** ở góc trên bên phải, chọn **Serper.dev**, dán API key rồi bấm Lưu.
   - Lấy key tại https://serper.dev (có 2.500 lượt tìm miễn phí).
   - Cũng dùng được SerpAPI hoặc Google Custom Search. Key được lưu trong file `.env` (xem `.env.example`).

Khi chưa có API key, tool chuyển sang chế độ thủ công: có nút mở Google với đúng đoạn mở đầu truyện, bạn dán link Facebook vào là tool lấy nội dung.

## Chạy bằng lệnh

```bash
pip install -r requirements.txt
python app.py
```

Yêu cầu máy có Google Chrome hoặc Microsoft Edge (dùng để đọc bài Facebook).
