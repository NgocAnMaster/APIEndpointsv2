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

app = FastAPI(title="Mock Teacher Server V4 - Phòng Thi Đẳng Cấp 100 Câu")

registered_students = {}
evaluation_results = {}

class RegisterPayload(BaseModel):
    server_url: str

class EvaluateRequest(BaseModel):
    document_received: Optional[bool] = False

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

@app.post("/api/v1/competition/reset")
async def reset_score(x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if x_student_id in evaluation_results:
        del evaluation_results[x_student_id]
        print(f"♻️ [RESET] Đã xóa kết quả cũ, sẵn sàng đánh giá lại cho {x_student_id}")
    return {"message": "Đã reset điểm thành công"}

# =========================================================================
# BỘ MẪU 10 CÂU GỐC - ĐƯỢC HỆ THỐNG TỰ ĐỘNG CHÂN PHƯƠNG NHÂN BẢN THÀNH 100 CÂU
# =========================================================================
BASE_QUESTIONS = [
    {"q": "Mã ngành của chương trình đào tạo Trí tuệ nhân tạo là gì?\nA. 7480101\nB. 7480109\nC. 7480201\nD. 7480107", "a": "D"},
    {"q": "Thời gian đào tạo chuẩn của ngành Trí tuệ nhân tạo kéo dài bao lâu?\nA. 4 năm\nB. 3.5 năm\nC. 4.5 năm\nD. 5 năm", "a": "A"},
    {"q": "Tổ hợp môn xét tuyển khối A00 và A01 của ngành gồm những môn nào?\nA. Toán, Lý, Hóa hoặc Toán, Văn, Anh\nB. Toán, Lý, Hóa hoặc Toán, Lý, Anh văn\nC. Toán, Lý, Sinh hoặc Toán, Hóa, Sinh\nD. Toán, Khoa học, Ngoại ngữ", "a": "B"},
    {"q": "Môn học 'Lập trình Python cơ bản' được giảng dạy ở học kỳ mấy?\nA. Học kỳ 1\nB. Học kỳ 4\nC. Học kỳ 2\nD. Học kỳ 3", "a": "C"},
    {"q": "Chuẩn đầu ra LO2 nhấn mạnh vào năng lực cốt lõi nào của sinh viên?\nA. Giao tiếp hiệu quả trong môi trường chuyên nghiệp\nB. Có khả năng làm việc nhóm tốt\nC. Có khả năng lập trình ứng dụng AI\nD. Có đạo đức và tính minh bạch trong nghiên cứu", "a": "C"},
    {"q": "Kỹ sư Thị giác máy tính (CV Engineer) đòi hỏi xử lý loại dữ liệu nào?\nA. Hình ảnh và video\nB. Âm thanh và giọng nói\nC. Văn bản và tài liệu chữ\nD. Cả 3 loại trên", "a": "A"},
    {"q": "Môn 'Nhập môn Học sâu' (Deep Learning) thuộc học kỳ mấy?\nA. Học kỳ 4\nB. Học kỳ 5\nC. Học kỳ 6\nD. Học kỳ 7", "a": "D"},
    {"q": "Ở học kỳ 9, sinh viên làm gì theo cấu trúc chương trình đào tạo?\nA. Thực tập và tốt nghiệp\nB. Học các môn bổ trợ chuyên ngành\nC. Đi học Giáo dục Quốc phòng và An ninh\nD. Làm độ án liên ngành", "a": "A"},
    {"q": "Vị trí Data Analyst có vai trò ứng dụng AI để làm gì?\nA. Viết API kết nối\nB. Tạo ra các model nhận diện và xử lý ngôn ngữ tự nhiên\nC. Phân tích dữ liệu lớn để đưa ra thống kê, hiển thị trực quan thông tin\nD. Đào tạo robot công nghiệp tự động", "a": "C"},
    {"q": "Chuẩn đầu ra LO3 liên quan mạnh mẽ nhất tới khía cạnh nào sau đây?\nA. Giải quyết vấn đề bằng toán học\nB. Trách nhiệm, nguyên tắc pháp lý và đạo đức nghề nghiệp\nC. Khả năng ngoại ngữ chuyên ngành\nD. Quản lý và dẫn dắt đội ngũ kỹ sư", "a": "B"}
]

# Nhân bản tuần hoàn tạo ra chuẩn 100 câu trắc nghiệm cho kỳ thi thực tế
MOCK_QUESTIONS_100 = []
for i in range(100):
    base = BASE_QUESTIONS[i % len(BASE_QUESTIONS)]
    MOCK_QUESTIONS_100.append({
        "q": f"Câu {i+1}: {base['q']}",
        "a": base["a"]
    })

def run_evaluation_workflow(student_id: str, student_url: str, document_received: bool):
    print(f"🚀 [EVALUATE] Chạy luồng đánh giá 100 câu cho {student_id} (document_received={document_received})...")
    
    # BƯỚC 1: KIỂM TRA ĐIỀU KIỆN UPLOAD TÀI LIỆU
    if not document_received:
        print("⏳ [UPLOAD CHƯA NHẬN] Thầy bắt đầu đọc file thực tế 'upload_db.json' gửi xuống...")
        input_file = "upload_db.json"
        if not os.path.exists(input_file):
            print(f"❌ Lỗi: Thiếu file '{input_file}' ở thư mục mock_server!")
            evaluation_results[student_id] = {"student_id": student_id, "score": 0.0, "status": "FAILED", "detail": ["Missing upload_db.json"]}
            return
            
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            extracted_text = " ".join([item.get("text", "") for item in raw_data if "text" in item])
            doc_id = raw_data[0].get("doc_id", "23297279-7375-4e52-a1e6-7954d8647014").split("_chunk_")[0]
            
            print(f"📡 Đang đẩy văn bản thô qua /upload của sinh viên. Cấu hình Timeout: 120s...")
            upload_res = requests.post(f"{student_url}/upload", json={"doc_id": doc_id, "text": extracted_text}, timeout=120)
            print(f"✅ Sinh viên báo nạp xong tài liệu thành công: {upload_res.json()}")
        except requests.exceptions.Timeout:
            print("🚨 [/upload TIMEOUT 2 PHÚT] Sinh viên đang bận xử lý nhúng cục bộ. Tiếp tục nhảy qua bắn câu hỏi...")
        except Exception as e:
            print(f"❌ Lỗi /upload bất thường: {e}")
    else:
        print("⏩ [UPLOAD ĐÃ NHẬN] Bỏ qua bước đẩy file, tiến thẳng tới chuỗi câu hỏi trắc nghiệm!")

    # BƯỚC 2: TIẾN HÀNH BẮN 100 CÂU HỎI
    print("⏳ Bước 2: Bắt đầu gửi chuỗi câu hỏi marathon (100 câu) qua /ask...")
    correct_answers = 0
    
    for i, exam in enumerate(MOCK_QUESTIONS_100):
        evaluation_results[student_id]["current_question"] = i + 1
        try:
            # Gửi từng câu hỏi lên máy trạm sinh viên
            ask_res = requests.post(f"{student_url}/ask", json={"question": exam["q"]}, timeout=10) # 10s cho mỗi câu
            student_ans = ask_res.json().get("answer", "").strip().upper()
            
            is_correct = (student_ans == exam["a"])
            if is_correct:
                correct_answers += 1
            
            if (i + 1) % 10 == 0: # Chỉ in log mỗi 10 câu để tránh ngập log command line
                print(f"   📈 Tiến độ: Lượt {i+1}/100 | Điểm số tạm thời: {correct_answers}/{i+1}")
                
        except Exception as e:
            pass # Timeout câu đơn lẻ không làm sập luồng thi lớn

    final_score = (correct_answers / len(MOCK_QUESTIONS_100)) * 10.0
    evaluation_results[student_id] = {
        "student_id": student_id,
        "score": final_score,
        "status": "FINISHED",
        "current_question": len(MOCK_QUESTIONS_100),
        "detail": f"Đúng {correct_answers}/100 câu."
    }
    print(f"🏁 [KẾT QUẢ KỲ THI GIẢ LẬP] Sinh viên {student_id} đạt: {final_score}/10.0")

@app.post("/api/v1/competition/evaluate")
async def evaluate(request: EvaluateRequest, x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if not x_student_id or x_student_id not in registered_students:
        raise HTTPException(status_code=400, detail="Student not registered")
    
    student_url = registered_students[x_student_id]
    evaluation_results[x_student_id] = {
        "student_id": x_student_id, "score": 0.0, "status": "EVALUATING", "current_question": 0
    }
    
    threading.Thread(
        target=run_evaluation_workflow, 
        args=(x_student_id, student_url, request.document_received)
    ).start()
    
    return {"message": "Nhận lệnh thành công. Đang khảo thí 100 câu...", "status": "EVALUATING"}

@app.get("/api/v1/competition/result")
async def get_result(x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if not x_student_id or x_student_id not in evaluation_results:
        raise HTTPException(status_code=404, detail="No result found")
    return evaluation_results[x_student_id]

# (Giữ nguyên Mock LLM Proxy để bẫy quét RAG)
@app.post("/api/v1/proxy/chat/completions")
async def mock_llm_proxy(request: ChatCompletionRequest, authorization: Optional[str] = Header(None)):
    user_message = request.messages[-1].content if request.messages else ""
    user_message_lower = user_message.lower()
    
    detected_answer = "A"
    for exam in BASE_QUESTIONS:
        cleaned_exam_q = exam["q"].split("\n")[0].lower()
        if cleaned_exam_q[:30] in user_message_lower:
            # Trình tự check ngữ cảnh
            if "7480107" in user_message_lower or "4" in user_message_lower or "toán, lý, anh văn" in user_message_lower or "học kỳ 2" in user_message_lower or "lập trình ứng dụng ai" in user_message_lower or "hình ảnh" in user_message_lower or "học kỳ 7" in user_message_lower or "thực tập" in user_message_lower or "phân tích dữ liệu lớn" in user_message_lower or "đạo đức nghề nghiệp" in user_message_lower:
                detected_answer = exam["a"]
            break
    return {"choices": [{"message": {"role": "assistant", "content": detected_answer}}]}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)