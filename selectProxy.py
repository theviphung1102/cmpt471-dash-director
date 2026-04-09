from flask import Flask, request, Response
from flask_cors import CORS
import requests
import time
import threading
import logging
from datetime import datetime
import os
from enum import Enum

class ProxyMode(Enum):
    NORMAL = 0      # Proxy works as normal, switches servers based on performance
    TEST = 1        # Force start client on Server 1, but allows server switching aftr
    CONTROL = 2     # For control testing, client is always on Server 1 and never switches

EXECUTION_MODE = ProxyMode.NORMAL

SERVERS = ['10.0.0.2', '10.0.0.3', '10.0.0.4']
TEST_SERVER = SERVERS[0]

ALPHA = 0.3

MAX_RTT = 100       # ms (anything above is "bad")
MAX_LOAD = 10.0        # users (capacity of server)
MAX_TP = 10000.0       # kb/s (target throughput)

RTT_WEIGHT = 0.5
LOAD_WEIGHT = 0.3
TP_WEIGHT = 0.2

server_rtt = {}
server_throughput = {}
active_request_count = {}
client_server_assignment = {}
server_score = {}

# For logging
os.makedirs('logs', exist_ok=True)
log_filename = f'logs/proxy_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    handlers=[
        logging.FileHandler(log_filename)
    ]
)

app = Flask(__name__)
CORS(app)

http_session = requests.Session()
stats_lock = threading.Lock()

#region MAIN FUNCTIONS

def startup():
    for server in SERVERS:
        active_request_count[server] = 0
        server_rtt[server] = measure_rtt(server)   # in ms
        server_throughput[server] = measure_throughput(server)   # in kb/s
        logging.info(f'STARTUP: Server: {server} | Initial RTT: {server_rtt[server]}ms | Initial Throughput: {server_throughput[server]:.2f} KB/s')


def measure_rtt(server, num_pings = 3):
    total_time = 0
    for _ in range(num_pings):
        start_time = time.time()
        http_session.get(f'http://{server}/output.mpd', timeout=2)
        end_time = time.time()
        
        total_time += end_time - start_time

    return int((total_time / num_pings ) * 1000)


def measure_throughput(server):
        start_time = time.time()
        response = http_session.get(f'http://{server}/output.mpd', timeout=2)
        end_time = time.time()

        size_kb = len(response.content) / 1024
        rtt = max(end_time - start_time, 0.001)

        return size_kb / rtt


def calculate_weighted_avg_rtt(server, new_rtt):
    return ALPHA * server_rtt[server] + (1 - ALPHA) * new_rtt


def calculate_weighted_avg_throughput(server, new_throughput):
    return ALPHA * server_throughput[server] + (1 - ALPHA) * new_throughput


def monitor_servers():
    while True:
        active_users = sum(active_request_count.values())

        # don't send pings if users actively requesting content
        if active_users > 0:
            time.sleep(2)
            continue

        for server in SERVERS:
            if active_request_count[server] == 0:
                try:
                    new_rtt = measure_rtt(server, num_pings=1)  # single ping
                    new_tp = measure_throughput(server)
                    
                    server_rtt[server] = calculate_weighted_avg_rtt(server, new_rtt)
                    server_throughput[server] = calculate_weighted_avg_throughput(server, new_tp)
                    
                    logging.info(f"MONITOR: Server: {server} | New RTT: {new_rtt}ms | Avg RTT: {server_rtt[server]:.2f}ms | "
                                 f"Throughput {new_tp:.2f}kb/s | Avg Throughput: {server_throughput[server]:.2f}kb/s")
                except requests.exceptions.RequestException:
                    logging.error(f'UNREACHABLE | Server: {server} | Setting RTT to 9999ms')
                    server_rtt[server] = 9999
        time.sleep(5)


def calculate_score(server):
    if server_rtt[server] >= 9999:
        server_score[server] = 0.0
        return 0.0
    
    # RTT, load, and throughput scores normalized against max expected values
    rtt_val = min(server_rtt[server], MAX_RTT)
    rtt_score = 1.0 - (rtt_val / MAX_RTT)

    session_load = list(client_server_assignment.values()).count(server)
    load_val = min(session_load, MAX_LOAD)
    load_score = 1.0 - (load_val / MAX_LOAD)

    tp_val = min(server_throughput[server], MAX_TP)
    tp_score = tp_val / MAX_TP

    # Weighted score
    score = (RTT_WEIGHT * rtt_score) + (LOAD_WEIGHT * load_score) + (TP_WEIGHT * tp_score)

    server_score[server] = score

    return score


def select_server(client_ip):
    current_server = client_server_assignment.get(client_ip, None)

    for server in SERVERS:
        calculate_score(server)

    best_server = max(SERVERS, key=lambda s: server_score[s])

    # new client - currently returning first server for testing congestion on specific server link
    if not current_server:
        if EXECUTION_MODE == ProxyMode.NORMAL:

            # count how many users assigned to each server
            current_load = {s: 0 for s in SERVERS}
            for assigned_server in client_server_assignment.values():
                current_load[assigned_server] += 1
            
            min_load = min(current_load.values())

            # find servers that have minimum load
            candidates = [s for s in SERVERS if current_load[s] == min_load]
            
            # among servers with min load, return server with best score
            init_server = max(candidates, key=lambda s: server_score[s])
        else:
            init_server = TEST_SERVER

        client_server_assignment[client_ip] = init_server

        logging.info(f"NEW CLIENT (TestMode={EXECUTION_MODE.name}): {client_ip} -> {init_server}")
        logging.info(f"INITIAL SCORES: S1: {server_score[SERVERS[0]]:.4f} | "
                     f"S2: {server_score[SERVERS[1]]:.4f} | S3: {server_score[SERVERS[2]]:.4f}")
        
        return init_server
    
    if EXECUTION_MODE == ProxyMode.CONTROL:
        logging.info(f"KEEPING CONTROL MODE: Staying on {current_server}")
        return current_server
        
    current_score = server_score[current_server]
    best_score = server_score[best_server]
    
    ratio_gain = best_score / current_score if current_score > 0 else 99.9
    abs_diff = best_score - current_score

    if ratio_gain > 1.2 and abs_diff > 0.05:
        client_server_assignment[client_ip] = best_server
        logging.info(f'SWITCH SERVER: Client: {client_ip} | {current_server} -> {best_server} | Score gain: {ratio_gain:.2f}x | Old score: {server_score[current_server]}, New score: {server_score[best_server]}, )')
        return best_server
    
    logging.info(f'KEEP SERVER: Client: {client_ip} | Keeping: {current_server} | Score: {server_score[current_server]:.6f}')
    return current_server

#endregion

# region ROUTING
@app.route('/output.mpd')
def get_mpd():
    client_ip = request.remote_addr

    server = select_server(client_ip)
    
    try:
        response = http_session.get(f'http://{server}/output.mpd')
        content = response.text
        
        # Rewrite URLs so the browser stays on the proxy (10.0.0.5)
        content = content.replace(f'http://{server}', f'http://{request.host}')
        
        return Response(content, mimetype='application/dash+xml')
    except Exception as e:
        logging.error(f"Manifest Error: {e}")
        return Response("Proxy Busy", status=503)

@app.route('/<path:segment>')
def get_segment(segment):
    client_ip = request.remote_addr
    max_retries = 2

    for attempt in range(max_retries):
        server = select_server(client_ip)
        url = f'http://{server}/{segment}'

        # Send request to server, track RTT, throughput, and user count during request
        with stats_lock:
            active_request_count[server] += 1

        try:
            start_time = time.time()
            response = http_session.get(url, timeout=3, stream=False)
            time_taken = max(time.time() - start_time, 0.0001)

            if response.status_code == 200:
                data = response.content

                # Lock when updating rtt and throughput stats
                with stats_lock:
                    new_rtt = int(time_taken * 1000)
                    server_rtt[server] = calculate_weighted_avg_rtt(server, new_rtt)
                    
                    # only include chunk downloads in throughput calculation
                    if 'chunk' in segment and len(data) > 0:
                        size_kb = len(data) / 1024
                        new_throughput = size_kb / time_taken
                        server_throughput[server] = calculate_weighted_avg_throughput(server, new_throughput)

                flask_res = Response(data, status=200)

                #response headers
                for key, value in response.headers.items():
                    if key.lower() not in ['content-encoding', 'transfer-encoding', 'connection', 'content-length']:
                        flask_res.headers[key] = value

                session_load = list(client_server_assignment.values()).count(server)
                logging.info(f'SUCCESS: {server} | {segment} | RTT: {new_rtt}ms | Active Requests: {active_request_count[server]} | Load: {session_load}')

                with stats_lock:
                    active_request_count[server] = max(0, active_request_count[server] - 1)

                return flask_res
            
            else:
                logging.warning(f'RETRY: {server} returned {response.status_code} on attempt {attempt+1}')

                with stats_lock:
                    active_request_count[server] = max(0, active_request_count[server] - 1)

                continue

        except (requests.exceptions.RequestException, Exception) as e:
            logging.error(f"RETRY: Attempt {attempt+1} failed for {server}: {e}")

            with stats_lock:
                server_rtt[server] = 9999
                active_request_count[server] = max(0, active_request_count[server] - 1)
            
            continue
        
    return Response("SERVER ERROR: All backend servers exhausted", status=503)

#endregion

if __name__ == '__main__':
    startup()

    adapter = requests.adapters.HTTPAdapter(pool_connections=50, pool_maxsize=100)
    http_session.mount('http://', adapter)
    
    # start monitor in background thread
    monitor_thread = threading.Thread(target=monitor_servers, daemon=True)
    monitor_thread.start()
    
    app.run(host='0.0.0.0', port=5000, threaded=True)