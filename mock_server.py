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

app = FastAPI(title="Mock Teacher Server V4 - Phòng Thi Đẳng Cấp 100 Câu Tuyệt Đối")

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
# BỘ MẪU 10 CÂU GỐC - ĐƯỢC CHUẨN HÓA KHỚP LOGIC VỚI TÀI LIỆU
# =========================================================================
BASE_QUESTIONS = [
    {"q": "Mã ngành của chương trình đào tạo Trí tuệ nhân tạo là gì?\nA. 7480101\nB. 7480109\nC. 7480201\nD. 7480107", "a": "D"},
    {"q": "Thời gian đào tạo chuẩn của ngành Trí tuệ nhân tạo kéo dài bao lâu?\nA. 4 năm\nB. 3.5 năm\nC. 4.5 năm\nD. 5 năm", "a": "C"}, # SỬA LẠI THÀNH C (4.5 năm) ĐỂ PHÙ HỢP TÀI LIỆU thực tế tránh vênh logic
    {"q": "Tổ hợp môn xét tuyển khối A00 và A01 của ngành gồm những môn nào?\nA. Toán, Lý, Hóa hoặc Toán, Văn, Anh\nB. Toán, Lý, Hóa hoặc Toán, Lý, Anh văn\nC. Toán, Lý, Sinh hoặc Toán, Hóa, Sinh\nD. Toán, Khoa học, Ngoại ngữ", "a": "B"},
    {"q": "Môn học 'Lập trình Python cơ bản' được giảng dạy ở học kỳ mấy?\nA. Học kỳ 1\nB. Học kỳ 4\nC. Học kỳ 2\nD. Học kỳ 3", "a": "C"},
    {"q": "Chuẩn đầu ra LO2 nhấn mạnh vào năng lực cốt lõi nào của sinh viên?\nA. Giao tiếp hiệu quả trong môi trường chuyên nghiệp\nB. Có khả năng làm việc nhóm tốt\nC. Có khả năng lập trình ứng dụng AI\nD. Có đạo đức và tính minh bạch trong nghiên cứu", "a": "C"},
    {"q": "Kỹ sư Thị giác máy tính (CV Engineer) đòi hỏi xử lý loại dữ liệu nào?\nA. Hình ảnh và video\nB. Âm thanh và giọng nói\nC. Văn bản và tài liệu chữ\nD. Cả 3 loại trên", "a": "A"},
    {"q": "Môn 'Nhập môn Học sâu' (Deep Learning) thuộc học kỳ mấy?\nA. Học kỳ 4\nB. Học kỳ 5\nC. Học kỳ 6\nD. Học kỳ 7", "a": "D"},
    {"q": "Ở học kỳ 9, sinh viên làm gì theo cấu trúc chương trình đào tạo?\nA. Thực tập và tốt nghiệp\nB. Học các môn bổ trợ chuyên ngành\nC. Đi học Giáo dục Quốc phòng và An ninh\nD. Làm độ án liên ngành", "a": "A"},
    {"q": "Vị trí Data Analyst có vai trò ứng dụng AI để làm gì?\nA. Viết API kết nối\nB. Tạo ra các model nhận diện và xử lý ngôn ngữ tự nhiên\nC. Phân tích dữ liệu lớn để đưa ra thống kê, hiển thị trực quan thông tin\nD. Đào tạo robot công nghiệp tự động", "a": "C"},
    {"q": "Chuẩn đầu ra LO3 liên quan mạnh mẽ nhất tới khía cạnh nào sau đây?\nA. Giải quyết vấn đề bằng toán học\nB. Trách nhiệm, nguyên tắc pháp lý và đạo đức nghề nghiệp\nC. Khả năng ngoại ngữ chuyên ngành\nD. Quản lý và dẫn dắt đội ngũ kỹ sư", "a": "B"}
]

MOCK_QUESTIONS_100 = []
for i in range(100):
    base = BASE_QUESTIONS[i % len(BASE_QUESTIONS)]
    MOCK_QUESTIONS_100.append({
        "q": f"Câu {i+1}: {base['q']}",
        "a": base["a"]
    })

def run_evaluation_workflow(student_id: str, student_url: str, document_received: bool):
    print(f"🚀 [EVALUATE] Chạy luồng đánh giá 100 câu cho {student_id}...")
    
    if not document_received:
        print("⏳ [UPLOAD CHƯA NHẬN] Thầy gửi file thực tế 'raw_document.txt' xuống...")
        input_file = "raw_document.txt"
        
        if not os.path.exists(input_file):
            print(f"❌ Lỗi: Thiếu file '{input_file}'")
            evaluation_results[student_id] = {
                "student_id": student_id, "score": 0.0, "status": "FAILED", "detail": ["Missing raw_document.txt"], "current_question": 0
            }
            return
            
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                extracted_text = f.read()
            
            doc_id = "exam-document-2026-v4"
            upload_res = requests.post(
                f"{student_url}/upload", 
                json={"doc_id": doc_id, "text": extracted_text}, 
                timeout=120
            )
            print(f"✅ Sinh viên báo nạp xong tài liệu: {upload_res.json()}")
        except Exception as e:
            print(f"⚠️ Cảnh báo luồng upload: {e}")

    print("⏳ Bước 2: Bắt đầu gửi chuỗi câu hỏi marathon (100 câu) qua /ask...")
    correct_answers = 0
    
    for i, exam in enumerate(MOCK_QUESTIONS_100):
        # Đảm bảo cập nhật trạng thái an toàn
        if student_id in evaluation_results:
            evaluation_results[student_id]["current_question"] = i + 1
            
        start_time = time.time()
        try:
            ask_res = requests.post(f"{student_url}/ask", json={"question": exam["q"]}, timeout=10)
            elapsed = time.time() - start_time
            
            student_ans = ask_res.json().get("answer", "").strip().upper()
            
            is_correct = (student_ans == exam["a"])
            if is_correct:
                correct_answers += 1

            status_str = "ĐÚNG" if is_correct else "SAI"
            print(f"   -> Câu {i+1} - Sinh viên đáp: {student_ans} | Đúng: {exam['a']} [{status_str}] - Tốn {elapsed:.2f}s")
            
        except Exception as e:
            print(f"❌ Lỗi khi hỏi câu {i+1}: {e}")

    final_score = (correct_answers / len(MOCK_QUESTIONS_100)) * 10.0
    evaluation_results[student_id] = {
        "student_id": student_id,
        "score": final_score,
        "status": "FINISHED",
        "current_question": len(MOCK_QUESTIONS_100),
        "detail": f"Đúng {correct_answers}/100 câu."
    }
    print(f"🏁 [KẾT QUẢ CUỐI CÙNG] Sinh viên {student_id} đạt: {final_score}/10.0")

@app.post("/api/v1/competition/evaluate")
async def evaluate(request: EvaluateRequest, x_student_id: Optional[str] = Header(None, alias="X-Student-ID")):
    if not x_student_id or x_student_id not in registered_students:
        raise HTTPException(status_code=400, detail="Student not registered")
    
    student_url = registered_students[x_student_id]
    # Khởi tạo phần tử đầy đủ cấu trúc từ trước khi luồng Thread chạy để tránh lỗi KeyError ở client
    evaluation_results[x_student_id] = {
        "student_id": x_student_id, "score": 0.0, "status": "EVALUATING", "current_question": 0, "detail": ""
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

# @app.post("/api/v1/proxy/chat/completions")
# async def mock_llm_proxy(request: ChatCompletionRequest, authorization: Optional[str] = Header(None)):
#     user_message = request.messages[-1].content if request.messages else ""
#     user_message_lower = user_message.lower().strip()
    
#     detected_answer = "A"
#     for exam in BASE_QUESTIONS:
#         cleaned_exam_q = exam["q"].split("\n")[0].lower()
#         # Nới rộng điều kiện tìm kiếm, trích xuất từ khóa thô loại bỏ ký tự câu hỏi để đối chiếu chuẩn xác nhất
#         raw_q_keyword = re.sub(r'câu \d+:\s*', '', cleaned_exam_q).strip()
        
#         if raw_q_keyword[:25] in user_message_lower:
#             # Thuật toán quét ngữ cảnh thông minh mềm dẻo tránh bẫy viết hoa viết thường dấu câu
#             if any(kw in user_message_lower for kw in ["7480107", "4.5 năm", "4 năm", "anh văn", "học kỳ 2", "ứng dụng ai", "hình ảnh", "học kỳ 7", "thực tập", "phân tích dữ liệu", "đạo đức"]):
#                 detected_answer = exam["a"]
#                 break
                
#     return {"choices": [{"message": {"role": "assistant", "content": detected_answer}}]}
@app.post("/api/v1/proxy/chat/completions")
async def mock_llm_proxy(request: ChatCompletionRequest, authorization: Optional[str] = Header(None)):
    user_message = request.messages[-1].content if request.messages else ""
    user_message_lower = user_message.lower().strip()
    
    # CHIẾN THUẬT: Cô lập phần câu hỏi thi để tránh bị nhiễu bởi các từ khóa nằm trong chunk RAG
    question_part = ""
    if "--- câu hỏi thi ---" in user_message_lower:
        question_part = user_message_lower.split("--- câu hỏi thi ---")[-1].strip()
    else:
        question_part = user_message_lower

    print(f"🔬 [PROXY INSPECT] Đang bẫy câu hỏi bóc tách: '{question_part[:100]}...'")

    # Kiểm tra bằng từ khóa độc bản nằm duy nhất trong câu hỏi thi thực tế
    if "mã ngành" in question_part:
        return {"choices": [{"message": {"role": "assistant", "content": "D"}}]}
    elif "thời gian đào tạo chuẩn" in question_part:
        return {"choices": [{"message": {"role": "assistant", "content": "C"}}]}
    elif "tổ hợp môn xét tuyển" in question_part or "khối a00" in question_part:
        return {"choices": [{"message": {"role": "assistant", "content": "B"}}]}
    elif "python cơ bản" in question_part:
        return {"choices": [{"message": {"role": "assistant", "content": "C"}}]}
    elif "lo2" in question_part or "lập trình ứng dụng ai" in question_part:
        return {"choices": [{"message": {"role": "assistant", "content": "C"}}]}
    elif "thị giác máy tính" in question_part or "cv engineer" in question_part:
        return {"choices": [{"message": {"role": "assistant", "content": "A"}}]}
    elif "học sâu" in question_part or "deep learning" in question_part:
        return {"choices": [{"message": {"role": "assistant", "content": "D"}}]}
    elif "học kỳ 9" in question_part or "thực tập và tốt nghiệp" in question_part:
        return {"choices": [{"message": {"role": "assistant", "content": "A"}}]}
    elif "data analyst" in question_part or "phân tích dữ liệu lớn" in question_part:
        return {"choices": [{"message": {"role": "assistant", "content": "C"}}]}
    elif "lo3" in question_part or "nguyên tắc pháp lý" in question_part or "đạo đức nghề nghiệp" in question_part:
        print("🎯 [PROXY MATCH] Khớp chính xác câu hỏi LO3 -> Ép đáp án xuất xưởng: B")
        return {"choices": [{"message": {"role": "assistant", "content": "B"}}]}

    # Fallback dự phòng quét theo vòng lặp nếu định dạng câu hỏi bị thay đổi cấu trúc ngoại lệ
    for exam in BASE_QUESTIONS:
        cleaned_exam_q = exam["q"].split("\n")[0].lower()
        raw_q_keyword = re.sub(r'câu \d+:\s*', '', cleaned_exam_q).strip()
        if raw_q_keyword[:25] in question_part:
            return {"choices": [{"message": {"role": "assistant", "content": exam["a"]}}]}
            
    return {"choices": [{"message": {"role": "assistant", "content": "A"}}]}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=5000)