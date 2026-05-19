# Hệ Thống RAG Competition - FastAPI Student Server

Tài liệu hướng dẫn và đặc tả API dành cho sinh viên tham gia cuộc thi cuối kỳ Offline RAG (Retrieval-Augmented Generation) Competition. Sinh viên có nhiệm vụ xây dựng một hệ thống API Endpoint sử dụng framework **FastAPI** để tiếp nhận tài liệu, thực hiện phân mảnh (Chunking), lưu trữ vào Vector Database, và thực hiện truy vấn thông qua mô hình ngôn ngữ lớn (LLM).

---

## 🧭 Luồng Nghiệp Vụ Hệ Thống

Hệ thống hoạt động theo mô hình điều phối hai chiều giữa **Teacher Server** (Proxy Competition Server) và **Student Server** (Máy của sinh viên).


```

+----------------+                    +----------------+
|                |  1. /register      |                |
|                |------------------->|                |
|                |  2. /evaluate      |                |
|                |------------------->|                |
| Student Server |                    | Teacher Server |
|  (Local Host)  |  3. /upload (Doc)  | (192.168.50.218|
|                |<-------------------|     :8000)     |
|                |  4. /ask (10 lần)  |                |
|                |<-------------------|                |
|                |  5. Proxy LLM      |                |
|                |------------------->|                |
+----------------+                    +----------------+

```

### Kiến trúc tổng quan bao gồm:
* **Teacher Server:** Đóng vai trò là API Gateway trung gian, bộ điều phối timeout/queue chống rate-limit, quản lý cấu trúc đề thi, tự động gọi chấm điểm và proxy API tới Public LLM.
* **Student Server:** Hệ thống do sinh viên tự triển khai tại máy cục bộ để xử lý trích xuất tri thức, nhúng văn bản (Embedding), quản lý VectorDB và đưa ra câu trả lời trắc nghiệm (A/B/C/D).

---

## 🛠️ Yêu Cầu Kỹ Thuật Đặc Biệt

### 1. Embedding Model Chạy Local
Để đảm bảo tính độc lập và tốc độ xử lý khi không có kết nối mạng internet bên ngoài, sinh viên **BẮT BUỘC** sử dụng mô hình nhúng sau:
* **Model:** `keepitreal/vietnamese-sbert`
* **Yêu cầu:** Tải về máy và cấu hình gọi local (Mô hình dung lượng nhẹ, tối ưu tốt cho tiếng Việt và có thể chạy mượt mà trên CPU của Laptop).

### 2. Phương Thức Gọi Proxy LLM
Trong môi trường thi offline không có mạng diện rộng, việc tương tác với LLM (ví dụ: `gpt-4o-mini`) sẽ được thực hiện thông qua cổng **Proxy API** tích hợp sẵn trên Teacher Server. Sinh viên sử dụng thư viện `openai` chuẩn để kết nối theo cấu hình sau:

```python
from openai import OpenAI

client = OpenAI(
    base_url="[http://192.168.50.218:8000/api/v1/proxy](http://192.168.50.218:8000/api/v1/proxy)",
    api_key="B21DCCN629" # Sử dụng Mã Số Sinh Viên viết hoa của bạn làm API KEY
)

res = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Nội dung câu hỏi kèm ngữ cảnh..."}]
)
print(res.choices[0].message.content)

```

---

## 📑 Chi Tiết API Endpoints

### 1. Teacher Server APIs (Sinh viên chủ động gọi)

* **Base URL:** `http://192.168.50.218:8000/api/v1`
* *Lưu ý:* Tất cả các request gửi lên Teacher Server đều **bắt buộc** kèm theo Header: `X-Student-ID: <Mã Sinh viên viết hoa>`.

#### 🔗 Đăng ký Student Server (`POST /competition/register`)

* **Chức năng:** Khai báo URL của Student Server với Teacher Server để hệ thống ghi nhận.
* **Body Request Schema:**
```json
{
  "server_url": "string"
}

```


* **Ví dụ Request:**
```bash
curl -X POST "[http://192.168.50.218:8000/api/v1/competition/register](http://192.168.50.218:8000/api/v1/competition/register)" \
     -H "X-Student-ID: B21DCCN629" \
     -H "Content-Type: application/json" \
     -d '{"server_url": "[http://192.168.1.15:5000](http://192.168.1.15:5000)"}'

```


* **Ví dụ Response:**
```json
{
  "message": "Đăng ký thành công!",
  "student_id": "B21DCCN629",
  "server_url": "[http://192.168.1.15:5000](http://192.168.1.15:5000)"
}

```



#### 🔗 Kích hoạt Chấm điểm (`POST /competition/evaluate`)

* **Chức năng:** Ra lệnh cho Teacher Server bắt đầu tiến trình thi. Lúc này, Teacher Server sẽ đóng vai trò như một Client, tự động gửi tài liệu qua endpoint `/upload` của sinh viên, sau đó thực hiện gọi liên tiếp 10 lần vào endpoint `/ask`.
* **Body Request Schema:** Trống (Không cần Content Body).
* **Ví dụ Response (Trả về sau khi hoàn thành toàn bộ tiến trình):**
```json
{
  "student_id": "B21DCCN629",
  "score": 8.0,
  "status": "completed",
  "detail": [ ... ]
}

```



#### 🔗 Khởi động lại Trạng thái (`POST /competition/reset`)

* **Chức năng:** Xóa bỏ kết quả cũ, đưa trạng thái thi về ban đầu để chuẩn bị chạy lại (hữu ích trong trường hợp mã nguồn của sinh viên bị crash hoặc gặp lỗi trong khi đang chấm).
* **Body Request Schema:** Trống.
* **Ví dụ Response:**
```json
{
  "status": "success",
  "message": "Đã reset trạng thái cho sinh viên B21DCCN629"
}

```



#### 🔗 Xem kết quả hiện tại (`GET /competition/result`)

* **Chức năng:** Kiểm tra tiến độ chấm thi, điểm số hiện tại và câu hỏi đang xử lý.
* **Body Request Schema:** Trống.
* **Ví dụ Response (Trong tiến trình đang đánh giá):**
```json
{
  "student_id": "B21DCCN629",
  "score": 5.0,
  "status": "evaluating",
  "current_question": 6
}

```



---

### 2. Student Server APIs (Sinh viên bắt buộc phải tự lập trình)

Sinh viên cần cấu hình ứng dụng FastAPI chạy trên máy local của mình đảm bảo đáp ứng chuẩn xác cấu trúc định dạng cấu hình dưới đây.

#### 📥 Tiếp nhận Tài liệu (`POST /upload`)

* **Chức năng:** Tiếp nhận văn bản tri thức gốc từ Teacher Server. Sinh viên thực hiện các tác vụ: Tách nhỏ văn bản (Chunking), chuyển đổi sang vector (Embedding bằng `vietnamese-sbert`) và lưu trữ vào VectorDB (Ví dụ: ChromaDB, FAISS, Qdrant,...).
* **Thời gian phản hồi tối đa (Timeout):** 120 giây.
* **Request Body:**
```json
{
  "doc_id": "none",
  "text": "Nội dung tài liệu RAG chứa dữ liệu tri thức dùng để tra cứu..."
}

```


* **Response Schema (Trả về từ Student Server):**
```json
{
  "status": "success",
  "doc_id": "abc_doc",
  "chunks": 42
}

```



#### ❓ Trả lời câu hỏi (`POST /ask`)

* **Chức năng:** Tiếp nhận câu hỏi trắc nghiệm. Sinh viên thực hiện truy vấn các đoạn văn bản tương quan nhất (Retrieve Context) từ VectorDB, thiết lập prompt gửi tới Proxy LLM để trích xuất ra đáp án chính xác nhất.
* **Thời gian phản hồi tối đa cho mỗi câu (Timeout):** 60 giây (Lặp lại tổng cộng 10 lần cho 10 câu hỏi độc lập).
* **Quy định về đáp án:** Trường `answer` **BẮT BUỘC** chỉ được phép trả về duy nhất 1 ký tự hoa đại diện cho phương án đúng: `A`, `B`, `C`, hoặc `D`.
* **Request Body:**
```json
{
  "question": "RAG viết tắt của từ gì? A. Retrieval-Augmented Generation B. Read-And-Gain C. Real-Agent-Ground D. Row-All-Grid"
}

```


* **Response Schema (Trả về từ Student Server):**
```json
{
  "answer": "A",
  "sources": [
    "chunk_1_content_tóm_tắt_về_định_nghĩa_RAG...",
    "chunk_2_content_thông_tin_bổ_trợ..."
  ]
}

```



---

## 💡 Gợi ý khung triển khai code FastAPI cơ bản cho Sinh viên

```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="RAG Competition - Student Server")

class UploadRequest(BaseModel):
    doc_id: Optional[str] = None
    text: str

class UploadResponse(BaseModel):
    status: str
    doc_id: Optional[str] = None
    chunks: int

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str
    sources: List[str] = []

@app.post("/upload", response_model=UploadResponse)
async def upload_document(payload: UploadRequest):
    # 1. Thực hiện Chunking text
    # 2. Gọi Embedding model (keepitreal/vietnamese-sbert) local
    # 3. Lưu dữ liệu vào VectorDB cục bộ
    return UploadResponse(status="success", doc_id=payload.doc_id or "default_id", chunks=10)

@app.post("/ask", response_model=AskResponse)
async def ask_question(payload: AskRequest):
    # 1. Sử dụng payload.question để truy vấn VectorDB lấy context thích hợp
    # 2. Xây dựng Prompt và gửi tới Proxy LLM qua OpenAI Client
    # 3. Trích xuất duy nhất ký tự A/B/C/D từ câu trả lời của LLM
    return AskResponse(answer="A", sources=["Đoạn text ngữ cảnh 1", "Đoạn text ngữ cảnh 2"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

```