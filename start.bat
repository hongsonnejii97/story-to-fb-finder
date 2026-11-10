@echo off
chcp 65001 >nul
title Facebook Story Matcher Tool
echo ========================================================
echo   Facebook Story Matcher - Tìm Bài Viết Facebook Từ Truyện
echo ========================================================
echo.
echo Đang kiểm tra môi trường Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LỖI] Không tìm thấy Python trên máy tính. Vui lòng cài đặt Python!
    pause
    exit /b 1
)

echo Đang khởi động Server FastAPI...
echo Mở trình duyệt tại http://127.0.0.1:8765
echo.

start "" "http://127.0.0.1:8765"
python -m uvicorn app:app --host 127.0.0.1 --port 8765

pause

