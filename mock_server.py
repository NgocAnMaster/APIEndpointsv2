import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import requests
import json
import time
import threading
import re

app = FastAPI(title="Mock Teacher Server (Phòng thi giả lập)")

# Lưu trữ trạng thái phòng thi giả lập
DB_FILE = "upload_db.json"
registered_students = {}
evaluation_results = {}

# --- SCHEMAS ---
class RegisterPayload(BaseModel):
    server_url: str

class AskRequest(BaseModel):
    question: str

# Giả lập API của OpenAI Proxy
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.0

# --- CÁC ENDPOINT MÔ PHỎNG TEACHER SERVER ---

@app.post("/api/v1/competition/register")
async def register(payload: RegisterPayload, x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if not x_student_id:
        raise HTTPException(status_code=400, detail="Missing X-Student-ID Header")
    
    registered_students[x_student_id] = payload.server_url
    print(f"🔹 [REGISTER] Sinh viên {x_student_id} đăng ký thành công với URL: {payload.server_url}")
    return {
        "message": "Đăng ký thành công!",
        "student_id": x_student_id,
        "server_url": payload.server_url
    }

# =========================================================================
# BỘ ĐỀ THI 10 CÂU HỎI THỰC TẾ (Đã cập nhật theo log và đáp án chuẩn của hệ thống)
# =========================================================================
MOCK_QUESTIONS = [
    {
        "q": "Câu 1: Mã ngành của chương trình đào tạo Trí tuệ nhân tạo là gì?\nA. 7480101\nB. 7480107\nC. 7480109\nD. 7480201", 
        "a": "B"
    },
    {
        "q": "Câu 2: Thời gian đào tạo chuẩn của ngành Trí tuệ nhân tạo kéo dài bao lâu?\nA. 3.5 năm\nB. 4 năm\nC. 4.5 năm\nD. 5 năm", 
        "a": "B"  # Khớp với dữ liệu gốc "Thời gian 4" trong chunk_0
    },
    {
        "q": "Câu 3: Tổ hợp môn xét tuyển khối A00 và A01 của ngành gồm những môn nào?\nA. Toán, Lý, Hóa hoặc Toán, Văn, Anh\nB. Toán, Lý, Sinh hoặc Toán, Hóa, Sinh\nC. Toán, Lý, Hóa hoặc Toán, Lý, Anh văn\nD. Toán, Khoa học, Ngoại ngữ", 
        "a": "C"
    },
    {
        "q": "Câu 4: Môn học 'Lập trình Python cơ bản' được giảng dạy ở học kỳ mấy?\nA. Học kỳ 1\nB. Học kỳ 2\nC. Học kỳ 3\nD. Học kỳ 4", 
        "a": "B"  # Khớp với cấu trình phân bổ môn cơ sở ngành chuẩn
    },
    {
        "q": "Câu 5: Chuẩn đầu ra LO2 nhấn mạnh vào năng lực cốt lõi nào của sinh viên?\nA. Có khả năng lập trình ứng dụng AI\nB. Giao tiếp hiệu quả trong môi trường chuyên nghiệp\nC. Có đạo đức và tính minh bạch trong nghiên cứu\nD. Có khả năng làm việc nhóm tốt", 
        "a": "A"  # Kỹ năng cá nhân và chuyên môn (Kỹ năng lập trình/thiết kế hệ thống)
    },
    {
        "q": "Câu 6: Kỹ sư Thị giác máy tính (CV Engineer) đòi hỏi xử lý loại dữ liệu nào?\nA. Văn bản và tài liệu chữ\nB. Âm thanh và giọng nói\nC. Hình ảnh và video\nD. Cả 3 loại trên", 
        "a": "C"
    },
    {
        "q": "Câu 7: Môn 'Nhập môn Học sâu' (Deep Learning) thuộc học kỳ mấy?\nA. Học kỳ 4\nB. Học kỳ 5\nC. Học kỳ 6\nD. Học kỳ 7", 
        "a": "D"
    },
    {
        "q": "Câu 8: Ở học kỳ 9, sinh viên làm gì theo cấu trúc chương trình đào tạo?\nA. Học các môn bổ trợ chuyên ngành\nB. Đi học Giáo dục Quốc phòng và An ninh\nC. Làm độ án liên ngành\nD. Thực tập và tốt nghiệp", 
        "a": "D"
    },
    {
        "q": "Câu 9: Vị trí Data Analyst có vai trò ứng dụng AI để làm gì?\nA. Viết API kết nối\nB. Phân tích dữ liệu lớn để đưa ra thống kê, hiển thị trực quan thông tin\nC. Tạo ra các model nhận diện và xử lý ngôn ngữ tự nhiên\nD. Đào tạo robot công nghiệp tự động", 
        "a": "B"
    },
    {
        "q": "Câu 10: Chuẩn đầu ra LO3 liên quan mạnh mẽ nhất tới khía cạnh nào sau đây?\nA. Trách nhiệm, nguyên tắc pháp lý và đạo đức nghề nghiệp\nB. Giải quyết vấn đề bằng toán học\nC. Khả năng ngoại ngữ chuyên ngành\nD. Quản lý và dẫn dắt đội ngũ kỹ sư", 
        "a": "A"
    }
]

def run_evaluation_workflow(student_id: str, student_url: str):
    """Luồng chạy ngầm gửi dữ liệu và chấm bài giống hệt Teacher Server thật"""
    print(f"🚀 [EVALUATE] Bắt đầu chấm điểm cho sinh viên {student_id}...")
    
    # Đọc dữ liệu thô từ file vector_db.json để làm tài liệu RAG gốc truyền xuống
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            raw_db = json.load(f)
        # Gộp toàn bộ text lại thành một văn bản lớn gửi đi
        combined_text = " . ".join([item['text'] for item in raw_db])
    except Exception:
        combined_text = "Nhóm các ngành, chương trình đào tạo lĩnh vực Kỹ thuật, Công nghệ. Ngành Trí tuệ nhân tạo. Mã ngành 7480107. Thời gian 4."

    # 1. Gửi văn bản gốc qua endpoint /upload của sinh viên
    print("⏳ Bước 1: Đang nạp tài liệu xuống máy sinh viên (/upload)...")
    try:
        upload_res = requests.post(
            f"{student_url}/upload", 
            json={"doc_id": "23297279-7375-4e52-a1e6-7954d8647014", "text": combined_text},
            timeout=120
        )
        print(f"✅ Sinh viên phản hồi /upload: {upload_res.json()}")
    except Exception as e:
        print(f"❌ Không thể kết nối tới /upload của sinh viên: {e}")
        evaluation_results[student_id] = {"student_id": student_id, "score": 0.0, "status": "failed", "detail": ["Upload failed"]}
        return

    # 2. Bắn lần lượt 10 câu hỏi qua endpoint /ask
    print("⏳ Bước 2: Bắt đầu gửi chuỗi 10 câu hỏi trắc nghiệm (/ask)...")
    correct_answers = 0
    details = []
    
    for i, exam in enumerate(MOCK_QUESTIONS):
        print(f"❓ Gửi câu hỏi {i+1}/10...")
        start_time = time.time()
        try:
            ask_res = requests.post(
                f"{student_url}/ask",
                json={"question": exam["q"]},
                timeout=60
            )
            elapsed = time.time() - start_time
            student_ans = ask_res.json().get("answer", "").strip().upper()
            sources = ask_res.json().get("sources", [])
            
            is_correct = (student_ans == exam["a"])
            if is_correct:
                correct_answers += 1
                
            status_str = "ĐÚNG" if is_correct else "SAI"
            print(f"   -> Sinh viên đáp: {student_ans} | Đáp án đúng: {exam['a']} [{status_str}] - Thời gian: {elapsed:.2f}s")
            
            details.append({
                "question_num": i + 1,
                "student_answer": student_ans,
                "expected_answer": exam["a"],
                "correct": is_correct,
                "latency": elapsed
            })
        except Exception as e:
            print(f"   -> 🚨 Câu hỏi {i+1} lỗi hoặc quá thời gian (Timeout): {e}")
            details.append({"question_num": i + 1, "student_answer": "TIMEOUT/ERROR", "expected_answer": exam["a"], "correct": False, "latency": 60.0})

    final_score = (correct_answers / len(MOCK_QUESTIONS)) * 10.0
    evaluation_results[student_id] = {
        "student_id": student_id,
        "score": final_score,
        "status": "FINISHED",
        "current_question": len(MOCK_QUESTIONS) + 1,
        "detail": details
    }
    print(f"🏁 [KẾT QUẢ THI GIẢ LẬP] Sinh viên {student_id} Đạt điểm số: {final_score}/10.0")

@app.post("/api/v1/competition/evaluate")
async def evaluate(x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if not x_student_id or x_student_id not in registered_students:
        raise HTTPException(status_code=400, detail="Student not registered or missing Header")
    
    student_url = registered_students[x_student_id]
    evaluation_results[x_student_id] = {"student_id": x_student_id, "score": 0.0, "status": "evaluating", "current_question": 1}
    
    # Chạy luồng đánh giá ngầm (Background thread) để không bị block API
    threading.Thread(target=run_evaluation_workflow, args=(x_student_id, student_url)).start()
    
    return {"message": "Đã hoàn tất đánh giá", "final_score": 0.0} # Trả về format đồng bộ để kích hoạt trigger

@app.get("/api/v1/competition/result")
async def get_result(x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if not x_student_id or x_student_id not in evaluation_results:
        raise HTTPException(status_code=404, detail="No result found")
    return evaluation_results[x_student_id]

# --- MOCK PROXY LLM ENDPOINT ---
@app.post("/api/v1/proxy/chat/completions")
async def mock_llm_proxy(request: ChatCompletionRequest, authorization: Optional[str] = Header(None)):
    user_message = request.messages[-1].content if request.messages else ""
    user_message_lower = user_message.lower()
    
    # Chuẩn hóa loại bỏ tiền tố "Câu X:" khi đối chiếu từ khóa cốt lõi để nhận diện đề bài chính xác hơn
    cleaned_user_msg = re.sub(r"câu\s+\d+:\s*", "", user_message_lower)
    
    detected_answer = "B" # Đặt mặc định Fallback là B
    for exam in MOCK_QUESTIONS:
        cleaned_exam_q = re.sub(r"câu\s+\d+:\s*", "", exam["q"].lower())
        # Lấy 35 ký tự đầu tiên của câu hỏi đã làm sạch để so sánh trùng khớp
        if cleaned_exam_q[:35] in cleaned_user_msg:
            detected_answer = exam["a"]
            break
            
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": detected_answer
                }
            }
        ]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)