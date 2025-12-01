# Microsoft Teams Integration - SmartXDR Middleware

## Tổng quan

Giải pháp **Polling-based Middleware** cho phép tích hợp Microsoft Teams với SmartXDR API một cách an toàn:

- ✅ **Outbound-only**: Không cần mở port inbound
- ✅ **Kiểm soát dữ liệu**: Toàn quyền kiểm soát luồng dữ liệu
- ✅ **Hoạt động sau firewall**: Phù hợp môi trường SOC nội bộ

### Kiến trúc

```
┌─────────────┐         ┌───────────────┐         ┌─────────────────┐
│  Microsoft  │◄──────► │  Graph API    │◄─────── │    Middleware   │
│    Teams    │         │  (Delta Query)│         │    (Polling)    │
└─────────────┘         └───────────────┘         └────────┬────────┘
                                                           │
                                                           ▼
                                                  ┌─────────────────┐
                                                  │   SmartXDR API  │
                                                  │  /api/ai/ask    │
                                                  └─────────────────┘
```

---

## Giai đoạn 1: Cấu hình Azure App Registration

### 1.1. Tạo App Registration

1. Truy cập [Azure Portal](https://portal.azure.com) > **App registrations**
2. Click **New registration**
   - Name: `SmartXDR-Middleware`
   - Supported account types: **Accounts in this organizational directory only**
3. Click **Register**

### 1.2. Lấy thông tin quan trọng

Sau khi tạo, lưu lại:
- **Application (client) ID**: `TEAMS_CLIENT_ID`
- **Directory (tenant) ID**: `TEAMS_TENANT_ID`

### 1.3. Tạo Client Secret

1. Vào **Certificates & secrets** > **New client secret**
2. Đặt tên và chọn thời hạn (ví dụ: 12 months)
3. **Copy Value ngay** (sẽ bị ẩn sau) → `TEAMS_CLIENT_SECRET`

### 1.4. Cấp quyền API

1. Vào **API permissions** > **Add a permission** > **Microsoft Graph**
2. Chọn **Application permissions**
3. Thêm quyền:
   - `ChannelMessage.Read.All` - Đọc tin nhắn
   - `ChannelMessage.Send` - Gửi tin nhắn reply
4. **Click "Grant admin consent for [Organization]"** ⚠️ Quan trọng!

---

## Giai đoạn 2: Lấy Team ID và Channel ID

### 2.1. Từ Microsoft Teams

1. Mở Microsoft Teams
2. Vào Channel muốn bot hoạt động
3. Click `...` > **Get link to channel**
4. Decode URL:

```
https://teams.microsoft.com/l/channel/19%3aXXX%40thread.tacv2/ChannelName?groupId=YYY&tenantId=ZZZ
```

- `TEAMS_TEAM_ID` = `YYY` (phần sau `groupId=`)
- `TEAMS_CHANNEL_ID` = `19:XXX@thread.tacv2` (URL decoded từ `19%3aXXX%40thread.tacv2`)

### 2.2. URL Decode

Thay thế:
- `%3a` → `:`
- `%40` → `@`

---

## Giai đoạn 3: Cấu hình Environment

Thêm vào file `.env`:

```env
# ===========================================
# Microsoft Teams Integration (Graph API)
# ===========================================
# Azure App Registration
TEAMS_TENANT_ID="your_tenant_id"
TEAMS_CLIENT_ID="your_client_id"
TEAMS_CLIENT_SECRET="your_client_secret"

# Teams Channel Configuration (URL Decoded)
TEAMS_TEAM_ID="your_team_id"
TEAMS_CHANNEL_ID="19:xxxxx@thread.tacv2"

# Middleware Settings
TEAMS_POLLING_INTERVAL=3
TEAMS_BOT_MENTION="@SmartXDR"
SMARTXDR_API_URL="http://localhost:8080/api/ai/ask"
```

---

## Giai đoạn 4: Cài đặt Dependencies

```bash
pip install msal beautifulsoup4
# Hoặc cài tất cả
pip install -r requirements.txt
```

---

## Giai đoạn 5: Chạy Middleware

### Option 1: Chạy Standalone

```bash
# Check cấu hình
python run_teams_middleware.py --check

# Chạy middleware
python run_teams_middleware.py

# Chạy với debug logging
python run_teams_middleware.py --debug
```

### Option 2: Chạy cùng Flask App

API endpoints quản lý middleware:

| Endpoint | Method | Mô tả |
|----------|--------|-------|
| `/api/teams/status` | GET | Xem trạng thái middleware |
| `/api/teams/start` | POST | Khởi động middleware |
| `/api/teams/stop` | POST | Dừng middleware |
| `/api/teams/config` | GET | Xem cấu hình (sanitized) |
| `/api/teams/test` | POST | Test kết nối Teams |

```bash
# Test kết nối
curl -X POST http://localhost:8080/api/teams/test

# Khởi động middleware qua API
curl -X POST http://localhost:8080/api/teams/start

# Xem trạng thái
curl http://localhost:8080/api/teams/status
```

### Option 3: Chạy như Systemd Service (Linux)

Tạo file `/etc/systemd/system/smartxdr-teams.service`:

```ini
[Unit]
Description=SmartXDR Teams Middleware
After=network.target

[Service]
Type=simple
User=smartxdr
WorkingDirectory=/path/to/Cyberfortress-SmartXDR-Core
ExecStart=/usr/bin/python3 run_teams_middleware.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable smartxdr-teams
sudo systemctl start smartxdr-teams
```

---

## Testing

### Test thủ công

1. Chạy middleware: `python run_teams_middleware.py`
2. Mở Teams, vào channel đã cấu hình
3. Gửi tin nhắn: *"Kiểm tra IP 8.8.8.8"*
4. Bot sẽ trả lời trong thread

### Test API

```bash
# Test connection
curl -X POST http://localhost:8080/api/teams/test

# Response
{
  "status": "success",
  "message": "All tests passed! Connection ready.",
  "details": {
    "config_valid": true,
    "token_acquired": true,
    "channel_accessible": true,
    "channel_name": "SOC-Alerts"
  }
}
```

---

## Xử lý lỗi thường gặp

### 1. Token acquisition failed

**Nguyên nhân**: Client Secret sai hoặc hết hạn
**Giải pháp**: Tạo Client Secret mới trong Azure Portal

### 2. Channel access denied (403)

**Nguyên nhân**: Thiếu quyền hoặc chưa Grant admin consent
**Giải pháp**: 
- Kiểm tra API permissions
- Click "Grant admin consent"

### 3. Bot trả lời chính nó (infinite loop)

**Đã xử lý**: Code tự động skip tin nhắn từ bot

### 4. Delta link expired (410)

**Đã xử lý**: Code tự động reinitialize delta query

---

## Tính năng nâng cao

### Mention-only mode

Để bot chỉ trả lời khi được mention:

Uncomment trong `teams_middleware_service.py`:

```python
def _should_respond(self, message_text: str) -> bool:
    if self.config.bot_mention.lower() not in message_text.lower():
        return False
    return True
```

### Custom Handler

```python
from app.services.teams_middleware_service import TeamsMiddlewareService

middleware = TeamsMiddlewareService()

def custom_handler(message: str) -> str:
    if "help" in message.lower():
        return "Các lệnh hỗ trợ: /check, /status, /report"
    # Default: gọi SmartXDR API
    return None  # Sẽ dùng default handler

middleware.set_custom_handler(custom_handler)
middleware.start()
```

---

## Security Notes

1. **Không commit Client Secret** vào git
2. **Sử dụng .env.example** cho template
3. **Rotate secret** định kỳ (khuyến nghị 6-12 tháng)
4. **Monitor logs** để phát hiện bất thường

---

## Troubleshooting Commands

```bash
# Check env variables
python -c "from app.services.teams_middleware_service import TeamsConfig; c = TeamsConfig(); print(c.validate())"

# Test Graph API manually
curl -X GET "https://graph.microsoft.com/v1.0/teams/{team-id}/channels/{channel-id}" \
  -H "Authorization: Bearer {access_token}"
```
