import uvicorn
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import requests
import json
import time
import threading
import os
import re

app = FastAPI(title="Mock Teacher Server V3 - Đọc Dữ Liệu File Thực Tế")

registered_students = {}
evaluation_results = {}

class RegisterPayload(BaseModel):
    server_url: str

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.0

@app.post("/api/v1/competition/register")
async def register(payload: RegisterPayload, x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if not x_student_id:
        raise HTTPException(status_code=400, detail="Missing X-Student-ID Header")
    registered_students[x_student_id] = payload.server_url
    print(f"🔹 [REGISTER] Sinh viên {x_student_id} đăng ký thành công.")
    return {"message": "Đăng ký thành công!", "student_id": x_student_id}

# =========================================================================
# BỘ ĐỀ THI ĐÃ ĐẢO ĐÁP ÁN (Dùng để kiểm tra tư duy RAG thực chất)
# =========================================================================
MOCK_QUESTIONS = [
    {"q": "Câu 1: Mã ngành của chương trình đào tạo Trí tuệ nhân tạo là gì?\nA. 7480101\nB. 7480109\nC. 7480201\nD. 7480107", "a": "D"},
    {"q": "Câu 2: Thời gian đào tạo chuẩn của ngành Trí tuệ nhân tạo kéo dài bao lâu?\nA. 4 năm\nB. 3.5 năm\nC. 4.5 năm\nD. 5 năm", "a": "A"},
    {"q": "Câu 3: Tổ hợp môn xét tuyển khối A00 và A01 của ngành gồm những môn nào?\nA. Toán, Lý, Hóa hoặc Toán, Văn, Anh\nB. Toán, Lý, Hóa hoặc Toán, Lý, Anh văn\nC. Toán, Lý, Sinh hoặc Toán, Hóa, Sinh\nD. Toán, Khoa học, Ngoại ngữ", "a": "B"},
    {"q": "Câu 4: Môn học 'Lập trình Python cơ bản' được giảng dạy ở học kỳ mấy?\nA. Học kỳ 1\nB. Học kỳ 4\nC. Học kỳ 2\nD. Học kỳ 3", "a": "C"},
    {"q": "Câu 5: Chuẩn đầu ra LO2 nhấn mạnh vào năng lực cốt lõi nào của sinh viên?\nA. Giao tiếp hiệu quả trong môi trường chuyên nghiệp\nB. Có khả năng làm việc nhóm tốt\nC. Có khả năng lập trình ứng dụng AI\nD. Có đạo đức và tính minh bạch trong nghiên cứu", "a": "C"},
    {"q": "Câu 6: Kỹ sư Thị giác máy tính (CV Engineer) đòi hỏi xử lý loại dữ liệu nào?\nA. Hình ảnh và video\nB. Âm thanh và giọng nói\nC. Văn bản và tài liệu chữ\nD. Cả 3 loại trên", "a": "A"},
    {"q": "Câu 7: Môn 'Nhập môn Học sâu' (Deep Learning) thuộc học kỳ mấy?\nA. Học kỳ 4\nB. Học kỳ 5\nC. Học kỳ 6\nD. Học kỳ 7", "a": "D"},
    {"q": "Câu 8: Ở học kỳ 9, sinh viên làm gì theo cấu trúc chương trình đào tạo?\nA. Thực tập và tốt nghiệp\nB. Học các môn bổ trợ chuyên ngành\nC. Đi học Giáo dục Quốc phòng và An ninh\nD. Làm độ án liên ngành", "a": "A"},
    {"q": "Câu 9: Vị trí Data Analyst có vai trò ứng dụng AI để làm gì?\nA. Viết API kết nối\nB. Tạo ra các model nhận diện và xử lý ngôn ngữ tự nhiên\nC. Phân tích dữ liệu lớn để đưa ra thống kê, hiển thị trực quan thông tin\nD. Đào tạo robot công nghiệp tự động", "a": "C"},
    {"q": "Câu 10: Chuẩn đầu ra LO3 liên quan mạnh mẽ nhất tới khía cạnh nào sau đây?\nA. Giải quyết vấn đề bằng toán học\nB. Trách nhiệm, nguyên tắc pháp lý và đạo đức nghề nghiệp\nC. Khả năng ngoại ngữ chuyên ngành\nD. Quản lý và dẫn dắt đội ngũ kỹ sư", "a": "B"}
]

def run_evaluation_workflow(student_id: str, student_url: str):
    print(f"🚀 [EVALUATE] Bắt đầu quy trình chấm điểm cho sinh viên {student_id}...")
    
    # 🔴 ĐỌC DỮ LIỆU THỰC TẾ TỪ FILE UPLOAD_DB.JSON DO THẦY CUNG CẤP
    input_file = "upload_db.json"
    if not os.path.exists(input_file):
        print(f"❌ Không tìm thấy file dữ liệu đầu vào '{input_file}'!")
        evaluation_results[student_id] = {"student_id": student_id, "score": 0.0, "status": "FAILED", "detail": [f"Missing {input_file}"]}
        return

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        # Gộp tất cả các text từ file json đầu vào thành chuỗi dữ liệu duy nhất để bắn qua /upload
        # (Giữ nguyên cấu trúc phân tách dữ liệu thô ban đầu)
        extracted_text = " ".join([item.get("text", "") for item in raw_data if "text" in item])
        doc_id = raw_data[0].get("doc_id", "23297279-7375-4e52-a1e6-7954d8647014").split("_chunk_")[0]
        
        print(f"📂 Đã đọc thành công {len(raw_data)} chunks dữ liệu từ {input_file}.")
    except Exception as e:
        print(f"❌ Lỗi khi phân tích cú pháp tệp '{input_file}': {e}")
        evaluation_results[student_id] = {"student_id": student_id, "score": 0.0, "status": "FAILED", "detail": ["Parse file error"]}
        return

    # 1. Gửi văn bản trích xuất từ file qua endpoint /upload của Student
    print("⏳ Bước 1: Đang nạp tài liệu kiểm thử thực tế xuống máy sinh viên (/upload)...")
    try:
        upload_res = requests.post(
            f"{student_url}/upload", 
            json={"doc_id": doc_id, "text": extracted_text}, 
            timeout=120
        )
        print(f"✅ Sinh viên phản hồi /upload: {upload_res.json()}")
    except Exception as e:
        print(f"❌ Lỗi kết nối /upload: {e}")
        evaluation_results[student_id] = {"student_id": student_id, "score": 0.0, "status": "FAILED"}
        return

    # 2. Bắn lần lượt 10 câu hỏi qua endpoint /ask
    print("⏳ Bước 2: Bắt đầu gửi chuỗi 10 câu hỏi trắc nghiệm (/ask)...")
    correct_answers = 0
    details = []
    
    for i, exam in enumerate(MOCK_QUESTIONS):
        evaluation_results[student_id]["current_question"] = i + 1
        try:
            ask_res = requests.post(f"{student_url}/ask", json={"question": exam["q"]}, timeout=60)
            student_ans = ask_res.json().get("answer", "").strip().upper()
            
            is_correct = (student_ans == exam["a"])
            if is_correct:
                correct_answers += 1
                
            print(f"   -> Câu {i+1}: Sinh viên chọn [{student_ans}] | Đáp án chuẩn [{exam['a']}] -> {'ĐÚNG' if is_correct else 'SAI'}")
            details.append({"question_num": i + 1, "student_answer": student_ans, "expected_answer": exam["a"], "correct": is_correct})
        except Exception as e:
            print(f"   -> 🚨 Câu hỏi {i+1} Timeout/Lỗi mạng LAN: {e}")
            details.append({"question_num": i + 1, "student_answer": "TIMEOUT", "expected_answer": exam["a"], "correct": False})

    final_score = (correct_answers / len(MOCK_QUESTIONS)) * 10.0
    evaluation_results[student_id] = {
        "student_id": student_id, "score": final_score, "status": "FINISHED", "detail": details
    }
    print(f"🏁 [KẾT QUẢ BIỂU ĐỒ] Sinh viên {student_id} đạt điểm số thực chất: {final_score}/10.0")

@app.post("/api/v1/competition/evaluate")
async def evaluate(x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if not x_student_id or x_student_id not in registered_students:
        raise HTTPException(status_code=400, detail="Student not registered")
    
    student_url = registered_students[x_student_id]
    evaluation_results[x_student_id] = {"student_id": x_student_id, "score": 0.0, "status": "EVALUATING", "current_question": 0, "detail": []}
    
    # Kích hoạt luồng chạy ngầm bất đồng bộ tránh gây nghẽn deadlock máy trạm cục bộ
    threading.Thread(target=run_evaluation_workflow, args=(x_student_id, student_url)).start()
    return {"message": "Hệ thống đã nhận file upload_db.json và đang tiến hành chấm bài kiểm tra.", "status": "EVALUATING"}

@app.get("/api/v1/competition/result")
async def get_result(x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if not x_student_id or x_student_id not in evaluation_results:
        raise HTTPException(status_code=404, detail="No result found")
    return evaluation_results[x_student_id]

# =========================================================================
# MOCK PROXY LLM THÔNG MINH
# =========================================================================
@app.post("/api/v1/proxy/chat/completions")
async def mock_llm_proxy(request: ChatCompletionRequest, authorization: Optional[str] = Header(None)):
    user_message = request.messages[-1].content if request.messages else ""
    user_message_lower = user_message.lower()
    
    current_exam = None
    for exam in MOCK_QUESTIONS:
        cleaned_exam_q = re.sub(r"câu\s+\d+:\s*", "", exam["q"].lower())
        if cleaned_exam_q[:35] in user_message_lower:
            current_exam = exam
            break
            
    if not current_exam:
        return {"choices": [{"message": {"role": "assistant", "content": "A"}}]}

    # Thực hiện bẫy quét tính hợp lệ của RAG dựa vào Prompt ngữ cảnh
    context_valid = False
    q_text = current_exam["q"].lower()
    
    if "7480107" in q_text and "7480107" in user_message_lower:
        context_valid = True
    elif "đào tạo chuẩn" in q_text and "thời gian" in user_message_lower and "4" in user_message_lower:
        context_valid = True
    elif "a00" in q_text and "toán, lý, anh văn" in user_message_lower:
        context_valid = True
    elif "python" in q_text and "học kỳ 2" in user_message_lower:
        context_valid = True
    elif "lo2" in q_text and "lập trình ứng dụng ai" in user_message_lower:
        context_valid = True
    elif "thị giác máy tính" in q_text and "hình ảnh" in user_message_lower:
        context_valid = True
    elif "học sâu" in q_text and "học kỳ 7" in user_message_lower:
        context_valid = True
    elif "học kỳ 9" in q_text and "thực tập" in user_message_lower:
        context_valid = True
    elif "data analyst" in q_text and "phân tích dữ liệu lớn" in user_message_lower:
        context_valid = True
    elif "lo3" in q_text and "đạo đức nghề nghiệp" in user_message_lower:
        context_valid = True

    if context_valid:
        detected_answer = current_exam["a"]
    else:
        detected_answer = "C" if current_exam["a"] != "C" else "B"
        print(f"⚠️  [RAG WARNING] Không tìm thấy ngữ cảnh hợp lệ trong prompt!")

    return {"choices": [{"message": {"role": "assistant", "content": detected_answer}}]}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)