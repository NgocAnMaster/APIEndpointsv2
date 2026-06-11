from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import uvicorn
from pydantic import BaseModel
from typing import List, Optional
import uuid, json, os
import numpy as np
from sentence_transformers import SentenceTransformer
from openai import OpenAI

# ==========================================
# 0. CẤU HÌNH THÔNG TIN PHÒNG THI (THAY ĐỔI TẠI ĐÂY)
# ==========================================
STUDENT_ID = "B22DCDT003"  # <--- THAY BẰNG MÃ SINH VIÊN CỦA BẠN (VIẾT HOA)
TEACHER_PROXY_URL = "http://127.0.0.1:5000/api/v1/proxy"

# ==========================================
# 1. KHỞI TẠO EMBEDDING MODEL & OPENAI CLIENT
# ==========================================
print("=== Đang nạp mô hình nhúng cục bộ Keepitreal/vietnamese-sbert... ===")
# Hệ thống sẽ tải về trong lần chạy đầu tiên, các lần sau sẽ tự động đọc từ cache local
embedding_model = SentenceTransformer("keepitreal/vietnamese-sbert")
print("=== Nạp mô hình nhúng thành công! ===")

# Khởi tạo OpenAI Client kết nối qua Proxy Server của Giảng viên
openai_client = OpenAI(
    base_url=TEACHER_PROXY_URL,
    api_key=STUDENT_ID
)

# ==========================================
# 2. ĐỊNH NGHĨA SCHEMAS (Đúng chuẩn đề bài yêu cầu)
# ==========================================
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

# ==========================================
# 3. CƠ SỞ DỮ LIỆU VECTOR (Vector DB & Persistence)
# ==========================================
DB_FILE = "vector_db.json"
mock_vector_db = []

def load_db():
    global mock_vector_db
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            mock_vector_db = json.load(f)
        print(f"Loaded {len(mock_vector_db)} chunks từ {DB_FILE}")
    else:
        mock_vector_db = []
        print(f"Chưa có DB cũ. Khởi tạo kho lưu trữ mới.")

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(mock_vector_db, f, ensure_ascii=False, indent=4)
    print(f"Đã đồng bộ hóa {len(mock_vector_db)} chunks vào {DB_FILE}")

def smart_chunking(text: str):
    """Chia nhỏ văn bản dựa trên dấu câu để giữ toàn vẹn ngữ nghĩa."""
    return [s.strip() for s in text.split('.') if s.strip()]

def search_relevant_chunks(query: str, top_k: int = 5):
    """Tìm kiếm ngữ nghĩa sử dụng Cosine Similarity và bộ lọc ngưỡng 0.7."""
    if not mock_vector_db:
        return []

    # 1. Tính toán embedding cho câu hỏi truyền vào
    query_vector = embedding_model.encode(query, convert_to_numpy=True)
    
    # Chuẩn hóa vector câu hỏi
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0:
        return []
    query_vector = query_vector / query_norm

    results = []
    for item in mock_vector_db:
        # Lấy vector có sẵn từ DB
        doc_vector = np.array(item['embedding'])
        doc_norm = np.linalg.norm(doc_vector)
        if doc_norm == 0:
            continue
        doc_vector = doc_vector / doc_norm
        
        # Tính toán độ tương đồng Cosine (Dot product của vector đã chuẩn hóa)
        score = float(np.dot(query_vector, doc_vector))
        results.append((score, item))

    # Sắp xếp theo điểm tương đồng giảm dần
    results.sort(key=lambda x: x[0], reverse=True)
    if not results:
        return []
    
    # Bộ lọc giữ lại các chunk đạt tối thiểu 70% điểm số của chunk cao nhất
    max_score = results[0][0]
    # Đảm bảo max_score dương và áp dụng ngưỡng lọc 70% một cách an toàn
    if max_score > 0:
        filtered_results = [res for res in results if res[0] >= max_score * 0.7]
    else:
        filtered_results = results
    
    return [res[1] for res in filtered_results[:top_k]]

def call_llm_rag(question: str):
    """Rút trích ngữ cảnh, xây dựng Prompt trắc nghiệm và gọi Proxy LLM."""
    relevant_items = search_relevant_chunks(question)
    
    # Trường hợp không tìm thấy tài liệu liên quan nào phù hợp
    if not relevant_items:
        # Trả về mặc định ngẫu nhiên một đáp án để tránh mất điểm trắng
        return "A", ["Không tìm thấy ngữ cảnh phù hợp"]
    
    # Hợp nhất các đoạn văn bản làm ngữ cảnh nền cho câu hỏi
    # context_text = " ".join([item['text'] for item in relevant_items])
    context_text = "\n".join([f" Đoạn {i+1}: {item['text']}" for i, item in enumerate(relevant_items)])
    sources = [item['doc_id'] for item in relevant_items]
    
    # Thiết lập System Prompt cực kỳ nghiêm ngặt để ép đầu ra là đáp án trắc nghiệm
    system_prompt = (
        "Bạn là trợ lý ảo phòng thi. Nhiệm vụ của bạn là giải câu hỏi trắc nghiệm bằng tiếng Việt.\n"
        "CHỈ dựa vào đoạn ngữ cảnh được cung cấp dưới đây để tìm ra đáp án đúng (A, B, C hoặc D).\n"
        "YÊU CẦU BẮT BUỘC: Bạn CHỈ ĐƯỢC PHẢN HỒI DUY NHẤT 1 KÝ TỰ là chữ cái của đáp án đúng (Ví dụ: 'A' hoặc 'B' hoặc 'C' hoặc 'D'). "
        "Không giải thích, không viết thêm bất kỳ từ ngữ nào khác."
    )
    
    user_content = f"--- NGỮ CẢNH ---\n{context_text}\n\n--- CÂU HỎI TRẮC NGHIỆM ---\n{question}"

    try:
        # Thực hiện gọi API thật qua Teacher Proxy
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.0  # Đặt bằng 0 để kết quả ra mang tính nhất quán, chính xác cao nhất
        )
        # Chuẩn hóa chuỗi kết quả (Xóa khoảng trắng thừa, viết hoa)
        final_answer = response.choices[0].message.content.strip().upper()
        
        # Bảo vệ cấu trúc: nếu LLM lỡ tay trả về chuỗi dài, trích xuất ký tự đầu tiên hợp lệ
        if len(final_answer) > 1:
            for char in final_answer:
                if char in ['A', 'B', 'C', 'D']:
                    final_answer = char
                    break
        
        # Nếu vẫn sai định dạng, gán mặc định "A" để tránh lỗi Schema hệ thống thi
        if final_answer not in ['A', 'B', 'C', 'D']:
            final_answer = "A"
            
        return final_answer, sources

    except Exception as e:
        print(f"🚨 Lỗi kết nối tới Teacher Proxy LLM: {str(e)}")
        # Xử lý fallback an toàn khi rớt mạng LAN hoặc timeout
        return "B", ["Lỗi kết nối API Gateway"]

# ==========================================
# 4. KHỞI TẠO VÀ ĐỊNH TUYẾN FASTAPI APP
# ==========================================
app = FastAPI(title=f"RAG Student Server - {STUDENT_ID}")

@app.on_event("startup")
def startup_event():
    load_db()

# --- ENDPOINT 1: UPLOAD DOCUMENT ---
@app.post("/upload", response_model=UploadResponse)
async def upload_document(request: UploadRequest):
    doc_id = request.doc_id or str(uuid.uuid4())
    chunks = smart_chunking(request.text)
    
    # Sinh embedding hàng loạt cho toàn bộ các chunks của tài liệu mới nạp
    if chunks:
        embeddings = embedding_model.encode(chunks, convert_to_numpy=True)
        
        for i, chunk_text in enumerate(chunks):
            mock_vector_db.append({
                "doc_id": f"{doc_id}_chunk_{i}",
                "text": chunk_text,
                "embedding": embeddings[i].tolist() # Chuyển mảng numpy sang list để lưu được vào tệp JSON
            })
        save_db()

    return UploadResponse(
        status="success",
        doc_id=doc_id,
        chunks=len(chunks)
    )

# --- ENDPOINT 2: ASK QUESTION ---
@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    # Gọi tổ hợp xử lý RAG + kết nối Proxy LLM để tìm đáp án trắc nghiệm
    answer, sources = call_llm_rag(request.question)
    
    print(f"👉 Câu hỏi từ Teacher Server: {request.question}")
    print(f"📢 Đáp án xuất xưởng: {answer} | Nguồn tham chiếu: {sources}")
    
    return AskResponse(
        answer=answer,
        sources=sources
    )

# --- FRONTEND ROUTE (Giữ lại để tự kiểm tra thủ công bằng mắt nếu cần) ---
@app.get("/", response_class=HTMLResponse)
async def get_frontend():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>RAG Dashboard Phòng Thi</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-white min-h-screen p-8">
        <div class="max-w-2xl mx-auto space-y-6">
            <h1 class="text-2xl font-bold text-center text-indigo-400">RAG Monitor System</h1>
            <div class="bg-slate-800 p-6 rounded-lg shadow-lg border border-slate-700">
                <p class="text-sm text-slate-400">Trạng thái server sinh viên: <span class="text-emerald-400 font-bold">READY</span></p>
                <p class="text-sm text-slate-400 mt-2">Mã định danh đăng ký thi: <span class="text-amber-400 font-mono font-bold">""" + STUDENT_ID + """</span></p>
            </div>
        </div>
    </body>
    </html>
    """

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",  # CHÚ Ý: Bắt buộc đổi sang 0.0.0.0 để máy Teacher Server trong mạng LAN có thể truy cập
        port=8000,
        reload=False     # Tắt reload khi thi thật để tối ưu hóa bộ nhớ, tránh reload lại model embedding nặng
    )