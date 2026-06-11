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
# CẤU HÌNH PHÒNG THI CHUẨN ĐẦU RA
# ==========================================
STUDENT_ID = "B22DCDT003"
TEACHER_PROXY_URL = "http://127.0.0.1:5000/api/v1/proxy"

print("=== Đang nạp mô hình nhúng cục bộ Keepitreal/vietnamese-sbert... ===")
embedding_model = SentenceTransformer("keepitreal/vietnamese-sbert")
print("=== Nạp mô hình nhúng thành công! ===")

openai_client = OpenAI(base_url=TEACHER_PROXY_URL, api_key=STUDENT_ID)

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

DB_FILE = "vector_db.json"
mock_vector_db = []

def load_db():
    """Tự động khôi phục dữ liệu từ đĩa cứng khi khởi động (Cực kỳ quan trọng cho vòng thi lượt True)"""
    global mock_vector_db
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            mock_vector_db = json.load(f)
        print(f"✅ Loaded thành công {len(mock_vector_db)} chunks từ file '{DB_FILE}' có sẵn!")
    else:
        mock_vector_db = []
        print(f"ℹ️ Chưa có cơ sở dữ liệu cũ. Sẵn sàng nhận mới tại lượt chạy document_received=False.")

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(mock_vector_db, f, ensure_ascii=False, indent=4)
    print(f"💾 Đã đồng bộ hóa lưu trữ cấu trúc vào file '{DB_FILE}'.")

def smart_chunking(text: str):
    """Phân khúc chuỗi văn bản dựa vào dấu tách cấu trúc thực tế"""
    return [s.strip() for s in text.split('.') if s.strip()]

def search_relevant_chunks(query: str, top_k: int = 5):
    if not mock_vector_db:
        return []

    query_vector = embedding_model.encode(query, convert_to_numpy=True)
    query_norm = np.linalg.norm(query_vector)
    if query_norm == 0: return []
    query_vector = query_vector / query_norm

    results = []
    for item in mock_vector_db:
        doc_vector = np.array(item['embedding'])
        doc_norm = np.linalg.norm(doc_vector)
        if doc_norm == 0: continue
        doc_vector = doc_vector / doc_norm
        
        score = float(np.dot(query_vector, doc_vector))
        results.append((score, item))

    results.sort(key=lambda x: x[0], reverse=True)
    if not results: return []
    
    max_score = results[0][0]
    # Ngưỡng động thông minh ngăn chặn lỗi Math Error chia toán học
    if max_score > 0:
        filtered_results = [res for res in results if res[0] >= max_score * 0.7]
    else:
        filtered_results = results
        
    return [res[1] for res in filtered_results[:top_k]]

def call_llm_rag(question: str):
    relevant_items = search_relevant_chunks(question)
    if not relevant_items:
        return "A", ["Không tìm thấy ngữ cảnh"]
    
    # 🌟 Đánh số thứ tự từng Đoạn rõ ràng để gpt-4o-mini không bị loạn khi thi 100 câu dồn dập
    context_text = "\n".join([f"Đoạn {i+1}: {item['text']}" for i, item in enumerate(relevant_items)])
    sources = [item['doc_id'] for item in relevant_items]
    
    system_prompt = (
        "Bạn là trợ lý ảo phòng thi. Nhiệm vụ của bạn là giải câu hỏi trắc nghiệm bằng tiếng Việt.\n"
        "CHỈ dựa vào đoạn ngữ cảnh được cung cấp dưới đây để tìm ra đáp án đúng (A, B, C hoặc D).\n"
        "YÊU CẦU BẮT BUỘC: Bạn CHỈ ĐƯỢC PHẢN HỒI DUY NHẤT 1 KÝ TỰ là chữ cái của đáp án đúng. Không giải thích gì thêm."
    )
    user_content = f"--- NGỮ CẢNH ---\n{context_text}\n\n--- CÂU HỎI TRẮC NGHIỆM ---\n{question}"

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.0
        )
        final_answer = response.choices[0].message.content.strip().upper()
        if len(final_answer) > 1:
            for char in final_answer:
                if char in ['A', 'B', 'C', 'D']:
                    final_answer = char
                    break
        if final_answer not in ['A', 'B', 'C', 'D']:
            final_answer = "A"
        return final_answer, sources
    except Exception as e:
        print(f"🚨 Lỗi kết nối Proxy LLM: {str(e)}")
        return "B", ["Fallback Mạng Cục Bộ"]

app = FastAPI(title=f"RAG Student Server V4 - {STUDENT_ID}")

@app.on_event("startup")
def startup_event():
    load_db()

@app.post("/upload", response_model=UploadResponse)
async def upload_document(request: UploadRequest):
    # Làm trống kho RAM cũ trước khi nạp dữ liệu thô mới hoàn toàn
    global mock_vector_db
    mock_vector_db = []
    
    doc_id = request.doc_id or str(uuid.uuid4())
    chunks = smart_chunking(request.text)
    
    if chunks:
        embeddings = embedding_model.encode(chunks, convert_to_numpy=True)
        for i, chunk_text in enumerate(chunks):
            mock_vector_db.append({
                "doc_id": f"{doc_id}_chunk_{i}",
                "text": chunk_text,
                "embedding": embeddings[i].tolist()
            })
        # Ghi cứng xuống ổ đĩa ngay khi hoàn tất xử lý
        save_db()

    return UploadResponse(status="success", doc_id=doc_id, chunks=len(chunks))

@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    answer, sources = call_llm_rag(request.question)
    return AskResponse(answer=answer, sources=sources)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)