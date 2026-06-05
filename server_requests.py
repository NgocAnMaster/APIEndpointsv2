import requests

def send_json_requests():
    # --- Configuration ---
    # Replace this with your actual student ID (it will automatically capitalize)
    student_id = "B22DCDT003" 
    
    # Define your custom headers
    headers = {
        "X-Student-ID": student_id.upper(),
        "Content-Type": "application/json"  # explicitly stating we are sending JSON
    }

    # Define URLs and JSON payloads
    url_1 = "http://10.170.45.200:8000/api/v1/competition/register"
    payload_1 = {"server_url": "http://10.170.45.67:8000"}

    url_2 = "http://10.170.45.200:8000/api/v1/competition/evaluate"
    payload_2 = {}

    url_3 = "http://10.170.45.200:8000/api/v1/competition/result"
    payload_3 = {}

    try:
        # --- Request 1 ---
        print(f"Sending first request with header X-Student-ID: {headers['X-Student-ID']}...")
        response_1 = requests.post(url_1, json=payload_1, headers=headers)
        
        print("Response 1:", response_1.json())

        # Throws exception if server returns an error status code
        response_1.raise_for_status() 
        
        print("First Request Success!")
        print("-" * 50)

        # --- Request 2 ---
        print("Sending second request...")
        response_2 = requests.post(url_2, json=payload_2, headers=headers)
        
        print("Response 2:", response_2.json())

        # Throws exception if server returns an error status code
        response_2.raise_for_status() 
        
        print("Second Request Success!")
        print("-" * 50)

        # --- Request 3 ---
        print("Sending third request...")
        response_3 = requests.get(url_3, json=payload_3, headers=headers)
        
        print("Response 3:", response_3.json())

        # Throws exception if server returns an error status code
        response_3.raise_for_status() 
        
        print("Third Request Success!")

    except requests.exceptions.HTTPError as http_err:
        print(f"\n[HTTP Error]: {http_err}")
        if 'response_1' in locals() and response_1.text:
            print(f"Server Response Content: {response_1.text}")
        raise
    except requests.exceptions.RequestException as req_err:
        print(f"\n[Network/General Error]: {req_err}")
        raise

if __name__ == "__main__":
    send_json_requests()