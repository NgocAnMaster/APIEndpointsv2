import requests
import time
import sys

def send_json_requests():
    # --- CẤU HÌNH PHÒNG THI ---
    STUDENT_ID = "B22DCDT003" 
    
    # URL phòng thi thực tế (Khi thi thật, hãy thay IP 127.0.0.1 bằng IP Teacher Server của thầy)
    BASE_TEACHER_URL = "http://127.0.0.1:5000/api/v1/competition"
    MY_SERVER_URL = "http://127.0.0.1:8000"  # URL máy local của bạn

    headers = {
        "X-Student-ID": STUDENT_ID.upper(),
        "Content-Type": "application/json"
    }

    print("=" * 60)
    print(f"🚀 CONSOLE ĐIỀU PHỐI PHÒNG THI RAG - SINH VIÊN: {STUDENT_ID.upper()}")
    print("=" * 60)
    print("1. Đăng ký tài khoản thi thực tế (/register)")
    print("2. Reset điểm số trên Server phòng thi (/reset)")
    print("3. Kích hoạt thi LẦN ĐẦU (document_received = False) -> (Bắn file + Chấm bài)")
    print("4. Kích hoạt thi LẠI (document_received = True)  -> (Chỉ bắn câu hỏi, cực nhanh)")
    print("5. Thoát chương trình")
    print("-" * 60)

    try:
        choice = input("👉 Nhập số lựa chọn hành động của bạn (1-5): ").strip()
        
        # -----------------------------------------------------------------
        # LỰA CHỌN 1: REGISTER
        # -----------------------------------------------------------------
        if choice == "1":
            url = f"{BASE_TEACHER_URL}/register"
            payload = {"server_url": MY_SERVER_URL}
            print(f"\n📡 Đang gửi request đăng ký tới: {url}...")
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            res.raise_for_status()
            print("🎉 [SUCCESS] Phản hồi từ Teacher Server:", res.json())

        # -----------------------------------------------------------------
        # LỰA CHỌN 2: RESET SCORE
        # -----------------------------------------------------------------
        elif choice == "2":
            url = f"{BASE_TEACHER_URL}/reset"
            print(f"\n📡 Đang gửi request reset kết quả thi tới: {url}...")
            res = requests.post(url, headers=headers, timeout=10)
            res.raise_for_status()
            print("♻️ [SUCCESS] Phản hồi từ Teacher Server:", res.json())

        # -----------------------------------------------------------------
        # LỰA CHỌN 3 & 4: EVALUATE (KÍCH HOẠT THI & QUÉT ĐIỂM REAL-TIME)
        # -----------------------------------------------------------------
        elif choice in ["3", "4"]:
            doc_received_status = True if choice == "4" else False
            
            url_eval = f"{BASE_TEACHER_URL}/evaluate"
            payload_eval = {"document_received": doc_received_status}
            
            print(f"\n📡 Đang kích hoạt cuộc thi thực tế (document_received={doc_received_status})...")
            # Đặt timeout cho evaluate là 130 giây vì lần đầu server thầy đợi nạp file mất tầm 2 phút
            res_eval = requests.post(url_eval, json=payload_eval, headers=headers, timeout=130)
            res_eval.raise_for_status()
            print("🚀 [START] Server thầy phản hồi kích hoạt thành công:", res_eval.json())
            print("\n" + "="*20 + " BẮT ĐẦU THEO DÕI TIẾN ĐỘ THỜI GIAN THỰC " + "="*20)

            # Khởi chạy vòng lặp Polling tự động quét trạng thái điểm số mỗi 3 giây
            url_result = f"{BASE_TEACHER_URL}/result"
            while True:
                try:
                    res_result = requests.get(url_result, headers=headers, timeout=5)
                    if res_result.status_code == 200:
                        data = res_result.json()
                        status = data.get("status", "UNKNOWN")
                        current_q = data.get("current_question", 0)
                        score = data.get("score", 0.0)
                        
                        # In đè dòng trạng thái để console trông sạch sẽ, chuyên nghiệp
                        sys.stdout.write(f"\r📈 Tiến độ câu hỏi: [{current_q}/100] | Trạng thái: {status} | Điểm số hiện tại: {score:.1f}/10.0")
                        sys.stdout.flush()
                        
                        if status in ["FINISHED", "FAILED"]:
                            print(f"\n\n🏁 Kỳ thi kết thúc! Trạng thái cuối: {status}")
                            print(f"🏆 Điểm số chính thức của bạn: {score}/10.0")
                            if "detail" in data:
                                print(f"📝 Ghi chú chi tiết: {data['detail']}")
                            break
                    else:
                        print(f"\n⚠️ Lỗi tạm thời khi lấy điểm (Mã lỗi: {res_result.status_code})")
                except Exception as e:
                    print(f"\n⚠️ Mất kết nối mạng LAN tạm thời trong lúc lấy điểm: {e}")
                
                time.sleep(3) # Cứ 3 giây quét kết quả một lần

        elif choice == "5":
            print("\n👋 Đã thoát chương trình.")
            exit(0)
        else:
            print("\n❌ Lựa chọn không hợp lệ, vui lòng chạy lại script!")

    except requests.exceptions.HTTPError as http_err:
        print(f"\n❌ [Lỗi HTTP từ Server Thầy]: {http_err}")
        try:
            print(f"Nội dung lỗi chi tiết: {http_err.response.text}")
        except:
            pass
    except requests.exceptions.RequestException as req_err:
        print(f"\n❌ [Lỗi Kết Nối Mạng LAN / Timeout]: {req_err}")

if __name__ == "__main__":
    while True:
        send_json_requests()
        while True:    
            print("\n" + "-"*60 + "\n")
            cont = input("🔄 Bạn có muốn tiếp tục thực hiện hành động khác không? (y/n): ").strip().lower()
            if cont == 'n':
                print("👋 Tạm biệt! Chúc bạn đạt điểm tuyệt đối!")
                exit(0)
            elif cont == 'y':
                break