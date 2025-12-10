# Email Reporting & Daily Scheduler Guide

## Tổng quan

Hệ thống Email Reporting tích hợp 3 chức năng chính:
1. **AI Analysis**: Phân tích cảnh báo với LLM + RAG, đưa ra khuyến nghị (tiếng Việt)
2. **Email Service**: Gửi báo cáo HTML qua SMTP với biểu đồ nhúng
3. **Daily Scheduler**: Tự động gửi báo cáo hàng ngày vào 7h sáng (hoặc tùy chỉnh)

---

## Cấu hình .env

Thêm các biến sau vào file `.env`:

```bash
# Email Configuration
FROM_EMAIL="your-email@gmail.com"
SMTP_SERVER="smtp.gmail.com"
SMTP_PORT=587
EMAIL_PASSWORD="your-app-password"  # Gmail App Password (NOT your regular password)

# Daily Report Settings
DAILY_REPORT_TIME="07:00"  # Format: HH:MM (24-hour)
```

### Lấy Gmail App Password:
1. Đi tới https://myaccount.google.com/security
2. Bật **2-Step Verification**
3. Vào **App Passwords** → Tạo password cho "Mail"
4. Copy password 16 ký tự vào `EMAIL_PASSWORD`

---

## API Endpoints

### 1. Summarize Alerts (với AI Analysis)

```bash
POST /api/triage/summarize-alerts
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "time_window_minutes": 10080,  # 7 ngày (mặc định)
  "source_ip": "192.168.1.100",  # Optional - lọc theo IP
  "include_ai_analysis": true    # Bật AI phân tích
}
```

**Response:**
```json
{
  "success": true,
  "timestamp": "2024-01-15T10:30:00",
  "summary": {
    "total_alerts": 1234,
    "risk_score": 68.5,
    "severity_breakdown": {
      "ERROR": 45,
      "WARNING": 789,
      "INFO": 400
    },
    "grouped_alerts": [
      {
        "pattern": "SSH Brute Force Attempt",
        "count": 156,
        "confidence": 0.95,
        "severity": "ERROR",
        "source_ips": ["10.0.1.50", "10.0.1.51"],
        "mitre_techniques": ["T1110.001"]
      }
    ]
  },
  "ai_analysis": "**Đánh giá mức độ nguy hiểm:** Hệ thống đang hứng chịu tấn công brute force SSH từ 2 địa chỉ IP nội bộ...\n\n**3 hành động ưu tiên:**\n1. Chặn ngay 2 IP 10.0.1.50/51 tại firewall\n2. Kiểm tra tài khoản SSH có dấu hiệu bị xâm nhập\n3. Cấu hình fail2ban cho SSH service\n\n**Kỹ thuật MITRE ATT&CK:** T1110.001 (Password Guessing)..."
}
```

---

### 2. Send Report Email (Manual)

```bash
POST /api/triage/send-report-email
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "to_email": "analyst@company.com",  # Optional - mặc định dùng FROM_EMAIL
  "time_window_minutes": 10080,
  "include_ai_analysis": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Email sent successfully",
  "sent_to": "analyst@company.com",
  "timestamp": "2024-01-15T10:30:00"
}
```

**Email sẽ bao gồm:**
- Header màu động (đỏ/cam/vàng/xanh theo risk score)
- Risk score với biểu đồ gauge
- 4 stat boxes: Total Alerts, High Severity, Risk Score, Time Window
- Bảng Top 5 Attack Patterns với MITRE techniques
- **AI Analysis section** với đánh giá + 3 hành động + MITRE mapping
- Visualization chart (embedded PNG)

---

### 3. Trigger Daily Report (Testing)

```bash
POST /api/triage/daily-report/trigger
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json

{
  "to_email": "test@company.com"  # Optional
}
```

Dùng để test ngay mà không cần đợi 7h sáng.

---

### 4. Health Check

```bash
GET /api/triage/health
```

**Response:**
```json
{
  "status": "healthy",
  "services": {
    "elasticsearch": true,
    "llm_service": true,
    "email_service": true,
    "daily_report": true  # Scheduler đang chạy
  }
}
```

---

## Daily Scheduler

### Cách hoạt động:

1. **Auto-start**: Scheduler tự động khởi động khi Flask app chạy
2. **Background thread**: Chạy nền với smart sleep scheduling
3. **Smart scheduling**: 
   - Tính toán thời gian đến lần gửi tiếp theo
   - Sleep theo chunks (max 1h mỗi chunk để graceful shutdown)
   - Khi còn 10 phút → check mỗi 30s
   - Khi còn 5 phút → check mỗi 60s
4. **Send report**: Khi khớp time → tự động gửi email với AI analysis
5. **Time window**: **24 hours** (alerts từ 7am hôm qua đến 7am hôm nay)
6. **Duplicate prevention**: Track ngày gửi, chỉ gửi 1 lần/ngày
7. **Next send calculation**: Tự động tính thời gian gửi tiếp theo (ngày mai cùng giờ)

### Luồng xử lý:

```
Day 1:
06:55:00 → Wake up (5 min before scheduled time)
  ↓
06:55:30 → Check every 30s (within 10 min window)
  ↓
07:00:00 → Match! Execute send
  ↓
Query alerts: 2025-12-09 07:00 → 2025-12-10 07:00 (24h)
  ↓
Summarize alerts (1440 minutes = 24 hours)
  ↓
Get AI analysis (top 5 patterns)
  ↓
Send email to TO_EMAILS
  ↓
Mark today as sent (prevent duplicate)
  ↓
Calculate next send time: 2025-12-11 07:00
  ↓
Sleep ~23 hours (in 1h chunks for graceful shutdown)
  ↓
Day 2:
06:55:00 → Wake up and repeat
  ↓
07:00:00 → Query alerts: 2025-12-10 07:00 → 2025-12-11 07:00 (24h)
```

### Log messages:

```
✓ Daily report scheduler initialized: 07:00 → laiquanthien15@gmail.com
🚀 Daily report scheduler started (send time: 07:00)
⏰ Sending scheduled daily report...
📊 Generating alert summary...
🤖 Generating AI analysis...
📧 Sending email to laiquanthien15@gmail.com...
✅ Daily report sent successfully
✅ Report sent. Next send: 2025-12-11 07:00 (in 23.5h)
📅 Report already sent today. Next send: 2025-12-11 07:00
```

### Graceful shutdown:

Scheduler tự động stop khi Flask app tắt (atexit handler).

---

## AI Analysis Details

### Prompt template:

```
Dựa trên dữ liệu cảnh báo bảo mật sau (Risk Score: {risk_score}/100):

Top 5 Attack Patterns:
1. SSH Brute Force Attempt (156 lần, IP: 10.0.1.50, 10.0.1.51)
2. SQL Injection Detected (89 lần, IP: 203.0.113.45)
...

Hãy phân tích ngắn gọn (<250 từ):
1. Đánh giá mức độ nguy hiểm
2. Đề xuất 3 hành động ưu tiên
3. Liên kết kỹ thuật MITRE ATT&CK
```

### Output format:

```
**Đánh giá mức độ nguy hiểm:** [1-2 câu tóm tắt]

**3 hành động ưu tiên:**
1. [Action 1 - cụ thể, có thể thực hiện ngay]
2. [Action 2]
3. [Action 3]

**Kỹ thuật MITRE ATT&CK:** T1110.001 (Password Guessing), T1190 (Exploit Public-Facing Application)
```

### RAG Integration:

- Query tự động lấy context từ ChromaDB:
  - Network topology (IP mapping, device info)
  - MITRE ATT&CK techniques (descriptions, mitigations)
  - Historical playbooks (previous incident responses)

---

## Risk Scoring Formula

```python
risk_score = (
    0.5                              # Base score
    + math.log10(total_alerts + 1) * 10  # Volume (logarithmic)
    + (error_pct * 35)               # ERROR severity weight
    + (warning_pct * 15)             # WARNING severity weight
    + (info_pct * 3)                 # INFO severity weight
    + (avg_confidence * 30)          # ML confidence
    + (escalation_level * 20)        # Attack sequence
)
```

### Examples:

| Scenario | Alerts | ERROR | WARNING | INFO | Risk Score |
|----------|--------|-------|---------|------|------------|
| 100 INFO (70% conf) | 100 | 0 | 0 | 100 | 44.5 |
| 100 WARNING (90% conf) | 100 | 0 | 100 | 0 | 62.5 |
| 1000 WARNING (85% conf) | 1000 | 0 | 1000 | 0 | 71.0 |
| 50 ERROR + escalation | 50 | 50 | 0 | 0 | 100.0 |

---

## Troubleshooting

### Email không gửi được:

1. **Check logs:**
   ```bash
   tail -f logs/app.log
   ```
   Tìm error: "SMTP authentication failed", "Connection refused"

2. **Verify config:**
   ```bash
   GET /api/triage/health
   ```
   Check `email_service: false` → Thiếu config .env

3. **Test SMTP manually:**
   ```python
   import smtplib
   smtp = smtplib.SMTP('smtp.gmail.com', 587)
   smtp.starttls()
   smtp.login('your-email@gmail.com', 'app-password')
   smtp.quit()
   ```

### AI analysis trống:

- **Check OpenAI API key:** `echo $OPENAI_API_KEY`
- **Check RAG data:** `GET /api/rag/stats` → Phải có documents
- **Check logs:** Tìm error "Failed to get AI analysis"

### Scheduler không chạy:

- **Check health:** `GET /api/triage/health` → `daily_report: false`
- **Check .env:** `DAILY_REPORT_TIME="07:00"` (đúng format HH:MM)
- **Check FROM_EMAIL:** Phải có email mới bật scheduler
- **Restart Flask:** `python run.py`

### Risk score không thực tế:

- Xem breakdown trong `/summarize-alerts` response
- Formula ưu tiên: ERROR > WARNING > INFO
- Logarithmic scaling → 1000 alerts ≠ 10x risk of 100 alerts

---

## Testing Guide

### 1. Test AI Analysis:

```bash
curl -X POST http://localhost:8080/api/triage/summarize-alerts \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "time_window_minutes": 1440,
    "include_ai_analysis": true
  }'
```

Xem field `ai_analysis` trong response.

### 2. Test Email Sending:

```bash
curl -X POST http://localhost:8080/api/triage/send-report-email \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "to_email": "your-test@gmail.com",
    "time_window_minutes": 1440,
    "include_ai_analysis": true
  }'
```

Check inbox sau 10-30 giây.

### 3. Test Daily Report (Manual Trigger):

```bash
curl -X POST http://localhost:8080/api/triage/daily-report/trigger \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "to_email": "your-test@gmail.com"
  }'
```

### 4. Test Scheduler Time Matching:

Đổi `DAILY_REPORT_TIME` trong .env sang 1-2 phút sau:
```bash
DAILY_REPORT_TIME="14:35"  # Hiện tại là 14:33
```

Restart Flask, đợi 2 phút → Check inbox.

---

## Best Practices

1. **Gmail limits:** 500 emails/day (free), 2000/day (Workspace)
   - Dùng daily report (1/day) thay vì realtime
   - Test với email khác nhau để tránh spam filter

2. **Risk score tuning:**
   - Base 0.5 → Luôn có điểm nền
   - Logarithmic volume → Tránh bùng nổ với alert storm
   - ERROR 35% → Ưu tiên critical alerts

3. **AI analysis:**
   - Giới hạn 250 từ → Email không quá dài
   - Top 5 patterns → Focus vào mối đe dọa lớn nhất
   - Vietnamese prompt → SOC analyst dễ đọc

4. **Scheduler:**
   - DAILY_REPORT_TIME="07:00" → Gửi trước giờ làm việc
   - Daemon thread → Không block Flask shutdown
   - 1-hour cooldown → Tránh duplicate send

5. **Security:**
   - Email credentials trong .env (NEVER commit!)
   - API key required cho tất cả endpoints
   - Gmail App Password (NOT regular password)

---

## Architecture

```
Flask App (run.py)
  ↓
Daily Scheduler (background thread)
  ↓ (every 60s)
Check time == DAILY_REPORT_TIME?
  ↓ (yes)
Alert Summarization Service
  ├─→ Elasticsearch: Query ML-classified alerts (7 days)
  ├─→ Risk Scoring: Calculate with new formula
  ├─→ Pattern Grouping: Top 5 attack patterns
  └─→ AI Analysis:
      ├─→ Extract patterns (count, IPs, MITRE)
      ├─→ Build Vietnamese prompt
      └─→ LLM Service:
          ├─→ RAG Query (network topology, MITRE docs)
          └─→ OpenAI GPT-4: Generate analysis
  ↓
Email Service
  ├─→ Build HTML: Risk-colored header, stats, table, AI section
  ├─→ Embed chart: Base64 PNG via Content-ID
  └─→ SMTP Send: Gmail 587 TLS
  ↓
Recipient inbox ✅
```

---

## Example Email HTML

![Email Preview](../assets/email-preview-example.png)

**Header:** Màu đỏ (Risk Score: 85.2/100)

**Stats Boxes:**
- Total Alerts: 1,234
- High Severity: 45 ERROR
- Risk Score: 85.2/100
- Time Window: 7 days

**Top Attack Patterns:**
| Pattern | Count | Severity | Source IPs | MITRE Techniques |
|---------|-------|----------|------------|------------------|
| SSH Brute Force | 156 | ERROR | 10.0.1.50, 10.0.1.51 | T1110.001 |
| SQL Injection | 89 | ERROR | 203.0.113.45 | T1190 |

**AI Analysis:**
> **Đánh giá mức độ nguy hiểm:** Hệ thống đang hứng chịu tấn công brute force SSH từ 2 IP nội bộ và SQL injection từ IP bên ngoài...
> 
> **3 hành động ưu tiên:**
> 1. Chặn ngay 3 IP tại firewall
> 2. Kiểm tra tài khoản SSH/database có bị xâm nhập
> 3. Deploy WAF rule cho SQL injection
> 
> **Kỹ thuật MITRE ATT&CK:** T1110.001 (Password Guessing), T1190 (Exploit Public-Facing Application)

**Visualization Chart:** [Embedded PNG]

---

## Migration from Old System

Nếu đang dùng hệ thống cũ (manual alerting):

1. **Update .env:** Thêm email config
2. **Restart Flask:** `python run.py`
3. **Check health:** `GET /api/triage/health`
4. **Test manual:** `POST /api/triage/send-report-email`
5. **Enable daily:** Đợi 7h sáng hoặc đổi `DAILY_REPORT_TIME`

**Breaking changes:** NONE - Backward compatible với API cũ.

---

## Support

Issues/questions:
- Check logs: `logs/app.log`
- Check health: `/api/triage/health`
- Test SMTP: Dùng script Python ở Troubleshooting
- Report bug: Create GitHub issue với logs + .env (MASK credentials!)

---

**Version:** 2.0 (January 2024)  
**Author:** Cyberfortress SmartXDR Team
