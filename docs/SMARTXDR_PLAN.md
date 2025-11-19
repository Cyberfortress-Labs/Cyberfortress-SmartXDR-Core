**GIẢI PHÁP TÍCH HỢP AI GATEWAY CHO HỆ THỐNG SOC**

# 1. Giới thiệu {#giới-thiệu}

Trong mô hình SOC hiện tại, các thành phần như SIEM -- SOAR - OpenXDR đã
tạo nên một nền tảng giám sát -- phát hiện -- phản ứng hoàn chỉnh. Tuy
nhiên, quy trình vận hành vẫn tồn tại điểm nghẽn lớn: phần lớn các tác
vụ phân tích (analysis), phân loại (triage) và ra quyết định vẫn phụ
thuộc vào con người và mang tính thủ công. Điều này dẫn đến thời gian
phản ứng (MTTR) cao và nguy cơ bỏ sót sự cố do quá tải cảnh báo (Alert
Fatigue).

Để giải quyết vấn đề này mà không yêu cầu hạ tầng phần cứng chuyên dụng
(GPU) cho việc huấn luyện mô hình, nhóm nghiên cứu đề xuất giải pháp
tích hợp **Generative AI** thông qua API (OpenAI GPT-5.1, Google Gemini
2.5 Pro).

Giải pháp được triển khai thông qua một lớp **Middleware (AI Gateway)**
tự xây dựng, giúp biến hệ thống SOC truyền thống thành một \"Cognitive
SOC\" có khả năng suy luận và hỗ trợ ra quyết định.

# 2. Yêu cầu và Mục tiêu ứng dụng AI {#yêu-cầu-và-mục-tiêu-ứng-dụng-ai}

Giải pháp AI được thiết kế để đáp ứng các yêu cầu kỹ thuật sau:

\- **Tự động hóa phân tích (Automated Triage):** Phân tích và tóm tắt sự
kiện bảo mật từ log thô (Suricata, Wazuh, Zeek...) thành ngôn ngữ tự
nhiên.

\- **Làm giàu dữ liệu thông minh (Smart Enrichment):** Tự động tương
quan dữ liệu log với thông tin tình báo (CTI) từ VirusTotal, IntelOwl,
MISP để đánh giá rủi ro.

\- **Giảm thiểu cảnh báo giả (False Positive Reduction):** Sử dụng khả
năng hiểu ngữ cảnh (context-aware) của LLM để lọc bỏ các cảnh báo không
nguy hiểm.

\- **Hỗ trợ quy trình (Dynamic Playbook):** Đề xuất các bước xử lý sự cố
cụ thể dựa trên khung MITRE ATT&CK.

\- **Báo cáo tự động (Automated Reporting):** Sinh báo cáo sự cố và báo
cáo tổng hợp hằng ngày.

# 3. Kiến trúc tổng thể: Flask-based AI Gateway {#kiến-trúc-tổng-thể-flask-based-ai-gateway}

Thay vì tích hợp trực tiếp các công cụ SOC với API của bên thứ 3, giải
pháp sử dụng mô hình **Centralized AI Gateway**. Đây là một vi dịch vụ
(Microservice) được phát triển bằng **Python Flask**, đóng vai trò trung
gian kiểm soát luồng dữ liệu.

## 3.1. Vai trò chiến lược của AI Gateway {#vai-trò-chiến-lược-của-ai-gateway}

Dịch vụ AI chạy trên Cloud (OpenAI/Gemini) tiềm ẩn rủi ro rò rỉ dữ liệu
hạ tầng nếu gửi log thô (raw logs) chứa IP nội bộ, tài khoản quản trị,
hoặc cấu trúc mạng doanh nghiệp. Do đó, AI Gateway đóng vai trò là lớp
**Data Sanitization Layer** (Lớp làm sạch dữ liệu) với các cơ chế bảo
mật chuyên sâu:

### 3.1.1. Cơ chế Ẩn danh hóa dữ liệu (Anonymization & Tokenization) {#cơ-chế-ẩn-danh-hóa-dữ-liệu-anonymization-tokenization}

Gateway sử dụng một **Cơ sở dữ liệu ánh xạ cục bộ (Private Mapping
Database)** để thay thế dữ liệu thật bằng các mã định danh (placeholder)
trước khi gửi đi:

\- **Cơ chế:** Khi phát hiện IP nội bộ (ví dụ: 192.168.85.23) hoặc
Username nhạy cảm (ví dụ: admin_ldap), Gateway sẽ thay thế bằng các
token như \<IP_SRC_1\>, \<USER_ADMIN\>.

\- **Quy trình:**

\+ *Gửi đi (Request):* Failed SSH login for user \<USER_1\> from
\<IP_1\>. AI chỉ nhìn thấy mẫu hình (pattern), không thấy dữ liệu định
danh.

\+ *Nhận về (Response):* Sau khi AI trả về phân tích, Gateway thực hiện
ánh xạ ngược (Reverse Mapping) để trả lại dữ liệu thật cho Analyst trên
giao diện IRIS.

**3.1.2. Kỹ thuật Zero-Knowledge Prompting & Masking**

Giải pháp áp dụng triệt để nguyên tắc \"Zero-Knowledge\" đối với nhà
cung cấp AI:

\- **Phân tách hành vi (Behavior Separation):** Chỉ gửi các đặc tả về
hành vi (Payload SQLi, mã lỗi, tần suất request) mà không gửi kèm đối
tượng thực hiện nếu không cần thiết.

\- **Masking/Hashing:** Đối với các thông tin không cần giải mã lại,
Gateway thực hiện làm mờ (Masking: thienlq@cyberfotress.local
\$\rightarrow\$ t\*\*\*\*@c\*\*\*) hoặc băm một chiều (Hashing: SHA256)
để đảm bảo AI không bao giờ đọc được giá trị gốc.

### 3.1.3. Tối ưu hiệu năng và quản trị {#tối-ưu-hiệu-năng-và-quản-trị}

**Caching Strategy (Redis/In-memory):** Lưu trữ kết quả phân tích của
các mẫu log lặp lại. Nếu một sự cố tương tự xảy ra trong thời gian ngắn,
Gateway trả về kết quả từ Cache, giảm độ trễ xuống mức mili-giây và tiết
kiệm chi phí API.

**Quản lý Prompt tập trung:** Tách biệt logic xử lý ngôn ngữ (Prompt
Engineering) khỏi logic điều phối, giúp dễ dàng tinh chỉnh độ chính xác
của AI.

## 3.2. Luồng hoạt động {#luồng-hoạt-động}

1.  **Detection:** Suricata/Wazuh/Zeek -\> Elasticsearch -\> ElastAlert2
    phát hiện bất thường.

2.  **Routing:** n8n gửi dữ liệu log thô (Raw JSON) đến **Flask AI
    Gateway**.

3.  **Gateway Processing:**

    - Check Cache.

    - **Sanitization:** Thực hiện Tokenization/Masking dựa trên Regex và
      whitelist.

    - Inject Prompt: Ghép dữ liệu đã làm sạch vào khuôn mẫu kỹ thuật.

    - Call API: Gửi request đến Gemini/OpenAI.

4.  **Response:** Gateway nhận kết quả, thực hiện **Reverse Mapping**
    (trả lại IP/User thật) -\> Chuẩn hóa JSON -\> Trả về **IRIS/n8n**.

5.  **Action:** IRIS cập nhật Case, n8n thực thi Playbook.

# 4. Các chức năng AI chính được triển khai {#các-chức-năng-ai-chính-được-triển-khai}

## 4.1. AI Triage & Alert Summarization (Điều tra viên ảo) {#ai-triage-alert-summarization-điều-tra-viên-ảo}

**- Chức năng:** Nhận đầu vào là log JSON phức tạp. AI thực hiện dịch
log sang tiếng Việt, giải thích hành vi và ánh xạ với kỹ thuật trong ma
trận MITRE ATT&CK.

\- **Đầu ra:** Bản tóm tắt ngắn gọn + Điểm rủi ro (Risk Score 1-10) giúp
Analyst sơ cấp (Tier 1) nhanh chóng nắm bắt tình hình.

## 4.2. Intelligent False Positive Reduction (Thẩm phán ảo) {#intelligent-false-positive-reduction-thẩm-phán-ảo}

**- Cơ chế:** AI phân tích ngữ cảnh (Context) của cảnh báo dựa trên dữ
liệu hành vi đã được làm sạch.

\- **Ví dụ:** Gateway gửi ngữ cảnh: \"User \<USER_1\> (Role: Admin) thực
hiện lệnh quét mạng vào giờ bảo trì\". AI đánh giá đây là hành động hợp
lệ và đề xuất đóng Case (False Positive), giúp giảm tải cho nhân viên
trực.

## 4.3. Dynamic Playbook Generator (Tham mưu trưởng) {#dynamic-playbook-generator-tham-mưu-trưởng}

**- Chức năng:** Thay vì sử dụng Playbook tĩnh, AI sinh ra quy trình xử
lý động.

\- **Quy trình:** Dựa trên loại tấn công (VD: SQL Injection) và danh
sách công cụ hiện có (được khai báo dưới dạng metadata ẩn danh), AI đề
xuất Action Plan dưới dạng JSON để n8n thực thi.

## 4.4. Automated Reporting (Thư ký ảo) {#automated-reporting-thư-ký-ảo}

**Chức năng:** Tổng hợp dữ liệu Case (đã được làm sạch hoặc phục hồi tùy
cấu hình) để soạn thảo \"Báo cáo sự cố\" (Incident Report) chuẩn chỉnh,
bao gồm: Nguyên nhân gốc rễ, Diễn biến, Khắc phục và Bài học kinh
nghiệm.

# 5. Đánh giá giải pháp {#đánh-giá-giải-pháp}

## 5.1. Ưu điểm {#ưu-điểm}

**- Bảo mật cao:** Giải quyết triệt để vấn đề lộ lọt dữ liệu nhạy cảm
khi sử dụng Public LLM nhờ lớp Sanitization chủ động.

\- **Triển khai nhanh & Linh hoạt:** Không tốn tài nguyên huấn luyện mô
hình. Kiến trúc lỏng lẻo (loosely coupled) cho phép thay thế AI Provider
dễ dàng.

\- **Hiệu quả chi phí:** Tối ưu hóa nhờ Caching và lựa chọn model phù
hợp.

## 5.2. Hạn chế & Giải pháp khắc phục {#hạn-chế-giải-pháp-khắc-phục}

|                                |                                                                  |                                                                                                                                                                                                                             |
|--------------------------------|------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Hạn chế**                    | **Rủi ro**                                                       | **Giải pháp khắc phục (Mitigation Strategy)**                                                                                                                                                                               |
| **Bảo mật dữ liệu**            | Gửi log chứa IP/User thật ra ngoài gây lộ lọt thông tin hạ tầng. | Triển khai **Data Sanitization Layer** tại Gateway: Áp dụng Tokenization, Hashing và Private Mapping Database để đảm bảo AI chỉ nhận được dữ liệu ẩn danh (Zero-Knowledge).                                                 |
| **Độ trễ (Latency)**           | API Call mất 3-10s, làm chậm quy trình phản ứng thời gian thực.  | Sử dụng cơ chế xử lý bất đồng bộ (**Async Processing**) trong n8n. Hệ thống không chờ AI trả lời mà tiếp tục các tác vụ khác, kết quả AI sẽ được cập nhật sau (Callback).                                                   |
| **Ảo giác AI (Hallucination)** | AI có thể bịa ra thông tin sai lệch hoặc đề xuất lệnh nguy hiểm. | Áp dụng nguyên tắc **\"Human-in-the-loop\"**: Các đề xuất tác động mạnh (Block IP, Delete File) bắt buộc phải có sự phê duyệt của con người trên IRIS trước khi thực thi. Yêu cầu AI trích dẫn nguồn log trong câu trả lời. |
| **Chi phí API**                | Tấn công DDoS log có thể làm tăng vọt chi phí API.               | Thiết lập **Rate Limiting** và **Budget Alert** tại Gateway. Tận dụng triệt để Caching cho các alert lặp lại.                                                                                                               |

# 6. Từ Smart XDR đến Intelligent SOC Ecosystem {#từ-smart-xdr-đến-intelligent-soc-ecosystem}

Dựa trên nền tảng AI Gateway đã xây dựng, hệ thống được nâng cấp từ mô
hình SOC truyền thống lên mô hình **Smart XDR**. Phần này mô tả chi tiết
cách thức hoạt động đồng bộ của toàn hệ thống.

## 6.1. Định nghĩa Smart XDR trong bối cảnh đề tài {#định-nghĩa-smart-xdr-trong-bối-cảnh-đề-tài}

Smart XDR trong đề tài này là sự kết hợp giữa **OpenXDR** làm tầng thu
thập/thực thi và **AI Gateway** làm tầng trí tuệ nhân tạo.

Hệ thống không chỉ thu thập log từ nhiều nguồn (Endpoint, Network,
Cloud) mà còn có khả năng **hiểu** nội dung log đó để tự động hóa quy
trình phản ứng.

## 6.2. Quy trình hoạt động End-to-End {#quy-trình-hoạt-động-end-to-end}

Quy trình xử lý một sự cố điển hình (ví dụ: Tấn công Brute Force vào Web
Server) trong hệ thống Smart XDR diễn ra như sau:

**Bước 1: Phát hiện (Detection)**

- **Suricata** phát hiện lưu lượng bất thường đến cổng 80.

- **Wazuh Agent** trên Web Server phát hiện nhiều lần đăng nhập thất bại
  (Event ID 4625).

- Log được đẩy về **Elasticsearch**. **ElastAlert2** khớp rule và phát
  sinh cảnh báo (Alert).

**Bước 2: Phân tích & Triage thông minh (AI Analysis)**

- ElastAlert2 gửi JSON cảnh báo đến **Flask AI Gateway**.

- **Gateway** thực hiện:

  1.  **Sanitization:** Mã hóa IP đích (Web Server) thành
      \<ASSET_WEB_01\>, IP nguồn thành \<ATTACKER_IP\>.

  2.  **Enrichment:** Gọi API VirusTotal kiểm tra \<ATTACKER_IP\> (nếu
      là IP Public).

  3.  **AI Query:** Gửi dữ liệu đã làm sạch + Kết quả VirusTotal đến
      Gemini/OpenAI với prompt: *\"Phân tích mức độ nghiêm trọng và đề
      xuất hành động\"*.

- **Kết quả:** AI xác định đây là tấn công Brute Force có chủ đích, mức
  độ High, đề xuất Block IP.

**Bước 3: Điều phối và Ra quyết định (Orchestration)**

- Gateway trả kết quả về **n8n**.

- **n8n** tạo một Case mới trên **IRIS** với tiêu đề: \[AI-CONFIRMED\]
  Brute Force Attack on Web Server.

- Nội dung Case bao gồm bản phân tích tiếng Việt từ AI và điểm rủi ro.

**Bước 4: Phản ứng tự động (Response)**

- Dựa trên đề xuất \"Block IP\" từ AI, **n8n** kích hoạt workflow phản
  ứng:

  1.  Gửi tin nhắn Teams cho Admin: *\"AI phát hiện tấn công. Nhấn
      \[BLOCK\] để chặn ngay.\"*

  2.  Nếu Admin nhấn nút (hoặc nếu cấu hình Auto-Block), n8n gọi API của
      **pfSense** để thêm IP tấn công vào Blacklist.

  3.  Gọi API **Wazuh** để tạm thời cô lập (Isolate) tiến trình bị tấn
      công nếu cần.

**Bước 5: Hậu kiểm và Báo cáo (Post-Incident)**

- Sau khi xử lý xong, Admin đóng Case trên IRIS.

- Gateway tự động tổng hợp lại toàn bộ quá trình thành file báo cáo .md
  lưu trữ làm tài liệu, phục vụ audit sau này.

## 6.3. Intelligent SOC Ecosystem {#intelligent-soc-ecosystem}

Nếu như **Smart XDR** là \"cánh tay phải\" giúp xử lý sự cố nhanh chóng,
thì **Intelligent SOC Ecosystem** chính là \"bộ não toàn diện\" kết nối
mọi thành phần lại với nhau thành một thực thể thống nhất.

Đây là bước phát triển cao hơn của hệ thống, nơi không chỉ có công cụ
giao tiếp với nhau mà còn có sự luân chuyển của tri thức (Intelligence).
Hệ sinh thái này được cấu thành từ 3 tầng chính hoạt động liên tục và bổ
trợ lẫn nhau:

### 6.3.1. Lớp Thực thi & Cảm biến (Execution & Sensor Layer) {#lớp-thực-thi-cảm-biến-execution-sensor-layer}

**- Thành phần:** Elastic Agent, Wazuh Agent, Suricata, Zeek, pfSense,
ModSecurity.

\- **Vai trò:** Đóng vai trò như các giác quan và tay chân của hệ thống.
Chúng thu thập tín hiệu (Logs/Events) từ môi trường và thực thi các hành
động vật lý (Block/Isolate) khi có lệnh. Trong mô hình Intelligent SOC,
các cảm biến này không chỉ gửi log thụ động mà có thể được điều chỉnh
cấu hình động (Dynamic Reconfiguration) dựa trên các chỉ dấu tấn công
(IoC) mới nhất.

### 6.3.2. Lớp Điều phối & Tự động hóa (Orchestration & Automation Layer) {#lớp-điều-phối-tự-động-hóa-orchestration-automation-layer}

**- Thành phần:** IRIS, n8n.

\- **Vai trò:** Hệ thần kinh trung ương, nơi kết nối các công cụ rời
rạc. Tại đây, các quy trình xử lý sự cố (Playbooks) được số hóa. Điểm
khác biệt trong hệ sinh thái thông minh là khả năng **Adaptive
Orchestration**: n8n có thể tự động chọn nhánh xử lý phù hợp dựa trên
điểm rủi ro từ AI mà không cần kịch bản cứng nhắc.

### 6.3.3. Lớp Nhận thức & Tri thức (Cognitive & Intelligence Layer) {#lớp-nhận-thức-tri-thức-cognitive-intelligence-layer}

**- Thành phần:** AI Gateway (Flask + LLM), MISP (Threat Intel),
IntelOwl.

\- **Vai trò:** Bộ não của hệ thống. Đây là nơi dữ liệu thô biến thành
thông tin có giá trị.

> \+ **MISP** cung cấp tri thức về các mối đe dọa toàn cầu.
>
> \+ **AI Gateway** cung cấp khả năng suy luận logic và hiểu ngữ cảnh.
>
> \+ Sự kết hợp này tạo ra **Contextual Awareness** (Nhận thức ngữ
> cảnh): Hệ thống biết được một file hash lạ có nguy hiểm hay không
> không chỉ dựa trên rule, mà dựa trên sự tương quan với các chiến dịch
> tấn công đang diễn ra trên thế giới.

## 6.4. Điểm khác biệt so với SOC truyền thống {#điểm-khác-biệt-so-với-soc-truyền-thống}

| **Đặc điểm**           | **SOC có XDR Truyền thống**           | **SOC có Smart XDR (Intelligent SOC Ecosystem)** |
|------------------------|---------------------------------------|--------------------------------------------------|
| **Xử lý log thô**      | Con người phải đọc JSON/XML phức tạp. | AI dịch log sang ngôn ngữ tự nhiên, dễ hiểu.     |
| **Triage (Phân loại)** | Thủ công, tốn thời gian, dễ bỏ sót.   | Tự động hóa, tốc độ xử lý nhanh                  |
| **False Positive**     | Dựa vào whitelist tĩnh (IP, User).    | Dựa vào ngữ cảnh hành vi (Context-aware).        |
| **Playbook**           | Cứng nhắc (Static), khó thay đổi.     | Động (Dynamic), AI gợi ý theo tình huống cụ thể. |
| **Bảo mật dữ liệu**    | Phụ thuộc vào quy trình nội bộ.       | Được đảm bảo bởi lớp Sanitization tự động.       |

# 7. Kết luận {#kết-luận}

Việc xây dựng giải pháp AI dựa trên kiến trúc **Flask AI Gateway** kết
hợp API của OpenAI và Google Gemini là mảnh ghép tối ưu để hoàn thiện hệ
thống SOC. Phương pháp này không chỉ giải quyết bài toán về tài nguyên
phần cứng (No-GPU) mà còn đặt ưu tiên hàng đầu cho **An toàn dữ liệu
(Data Privacy)** thông qua cơ chế Sanitization và Zero-Knowledge
Prompting.

Đây là bước tiến quan trọng giúp chuyển đổi mô hình giám sát thụ động
sang **Intelligent SOC**, đảm bảo khả năng phản ứng nhanh, chính xác và
an toàn trong môi trường đe dọa mạng ngày càng phức tạp.
