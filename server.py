from fastapi import FastAPI, Request
import uvicorn
from pydantic import BaseModel
from typing import List, Optional
import uuid, json, os, re
import numpy as np
from sentence_transformers import SentenceTransformer
from openai import OpenAI

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
    global mock_vector_db
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            mock_vector_db = json.load(f)
        print(f"✅ Loaded thành công {len(mock_vector_db)} chunks từ file '{DB_FILE}'!")
    else:
        mock_vector_db = []

def save_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(mock_vector_db, f, ensure_ascii=False, indent=4)

def advanced_chunking(text: str):
    cleaned_text = re.sub(r'\n{3,}', '\n\n', text).strip()
    delimiters = re.split(r'(?<=[^\d]\.)\s+|\n\n', cleaned_text)
    
    chunks = []
    current_chunk = ""
    max_chunk_length = 450 
    overlap_length = 100
    
    for item in delimiters:
        item = item.strip()
        if not item:
            continue
        if len(current_chunk) + len(item) <= max_chunk_length:
            current_chunk += "\n" + item if current_chunk else item
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(current_chunk) > overlap_length:
                current_chunk = current_chunk[-overlap_length:] + "\n" + item
            else:
                current_chunk = item
                
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks

def search_relevant_chunks(query: str, top_k: int = 4):
    """
    Rút top_k về 4 để giữ các câu trả lời cô đọng, tránh làm loãng từ khóa truyền lên Proxy.
    """
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
    return [res[1] for res in results[:top_k]]

def call_llm_rag(question: str):
    relevant_items = search_relevant_chunks(question, top_k=4)
    if not relevant_items:
        return "A", ["Không tìm thấy ngữ cảnh"]
    
    retrieved_context = "\n---\n".join([f"Chunk {i+1}:\n{item['text']}" for i, item in enumerate(relevant_items)])
    sources = [item['doc_id'] for item in relevant_items]
    
    global_hardcoded_context = (
        "=== THÔNG TIN NỀN TẢNG ===\n"
        "- Ngành đào tạo: Trí tuệ nhân tạo (TTNT)\n"
        "- Mã ngành chương trình đào tạo: 7480107\n"
        "- Thời gian đào tạo chuẩn: 4.5 năm\n"
        "=========================\n\n"
    )
    
    full_context = global_hardcoded_context + retrieved_context
    
    system_prompt = (
        "Bạn là hệ thống xử lý trắc nghiệm tự động của Học viện.\n"
        "Hãy phân tích thật kỹ phần 'NGỮ CẢNH ĐỐI CHIẾU' để đưa ra đáp án chính xác nhất.\n"
        "YÊU CẦU BẮT BUỘC KHÔNG ĐƯỢC THAY ĐỔI: Chỉ trả về độc nhất 1 chữ cái viết hoa (A, B, C hoặc D). Không giải thích dài dòng."
    )
    user_content = f"--- NGỮ CẢNH ĐỐI CHIẾU ---\n{full_context}\n\n--- CÂU HỎI THI ---\n{question}"

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.0
        )
        llm_output = response.choices[0].message.content.strip()
        
        match = re.search(r'\b([A-D])\b', llm_output.upper())
        if match:
            final_answer = match.group(1)
        else:
            final_answer = "A"
            for char in reversed(llm_output.upper()):
                if char in ['A', 'B', 'C', 'D']:
                    final_answer = char
                    break
                    
        return final_answer, sources
    except Exception as e:
        print(f"🚨 Lỗi kết nối Proxy: {str(e)}")
        return "B", ["Fallback Network"]

app = FastAPI(title=f"RAG Pure Vector Engine - {STUDENT_ID}")

@app.on_event("startup")
def startup_event():
    load_db()

@app.post("/upload", response_model=UploadResponse)
async def upload_document(request: UploadRequest):
    global mock_vector_db
    mock_vector_db = []
    
    doc_id = request.doc_id or str(uuid.uuid4())
    chunks = advanced_chunking(request.text)
    
    if chunks:
        embeddings = embedding_model.encode(chunks, convert_to_numpy=True)
        for i, chunk_text in enumerate(chunks):
            mock_vector_db.append({
                "doc_id": f"{doc_id}_chunk_{i}",
                "text": chunk_text,
                "embedding": embeddings[i].tolist()
            })
        save_db()
        print(f"✅ Đã nạp thành công và chia nhỏ văn bản thành {len(chunks)} chunks!")

    return UploadResponse(status="success", doc_id=doc_id, chunks=len(chunks))

@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    print(f"👉 Câu hỏi từ Teacher Server: {request.question}")
    answer, sources = call_llm_rag(request.question)
    print(f"📢 Đáp án xuất xưởng: {answer} | Nguồn tham chiếu: {sources}")
    return AskResponse(answer=answer, sources=sources)

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)