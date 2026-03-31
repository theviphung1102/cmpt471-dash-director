import requests
import time
import threading
import sys

PROXY_URL = "http://10.0.0.5:5000"
NUM_SEGMENTS = 30

def simulate_user(user_id):
    print(f"[User {user_id}] Starting...")
    try:
        # 1. Manifest
        print("Requesting manifest...")
        r = requests.get(f"{PROXY_URL}/output.mpd")
        print(f"Manifest Status: {r.status_code}")
        
        # 2. Segments
        for i in range(1, NUM_SEGMENTS + 1):
            if i < 10:
                segment = f"chunk-stream1-0000{i}.m4s"
            else:
                segment = f"chunk-stream1-000{i}.m4s"

            start_time = time.time()

            print(f"Requesting {segment}...", end=" ")
            resp = requests.get(f"{PROXY_URL}/{segment}")

            duration = (time.time() - start_time) * 1000
            print(f"Done! Status: {resp.status_code} | Time: {duration:.2f}ms")
            time.sleep(0.5)
    except Exception as e:
        print(f"[User {user_id}] Error: {e}")

if __name__ == "__main__":
    # Get NUM_USERS from command line argument, default to 1
    num_users = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    
    print(f"--- Launching {num_users} Concurrent Users ---")
    threads = []
    for i in range(num_users):
        t = threading.Thread(target=simulate_user, args=(i,))
        threads.append(t)
        t.start()
        time.sleep(0.05) 

    for t in threads:
        t.join()