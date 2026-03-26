from flask import Flask, request, Response
from flask_cors import CORS
import requests
import time
import threading
import logging
from datetime import datetime
import os

SERVERS = ['10.0.0.2', '10.0.0.3', '10.0.0.4']

TEST_MODE = True
TEST_SERVER = SERVERS[0]

ALPHA = 0.7

MAX_RTT = 200.0        # ms (anything above is "bad")
MAX_LOAD = 20.0        # users (capacity of server)
MAX_TP = 10000.0       # kb/s (target throughput)

RTT_WEIGHT = 0.7
LOAD_WEIGHT = 0.2
TP_WEIGHT = 0.1

server_rtt = {}
server_throughput = {}
user_count = {}
client_server_assignment = {}
server_score = {}

os.makedirs('logs', exist_ok=True)

log_filename = f'logs/proxy_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler() 
    ]
)

app = Flask(__name__)
CORS(app)

#region MAIN FUNCTIONS

def startup():
    for server in SERVERS:
        user_count[server] = 0
        server_rtt[server] = measure_rtt(server)   # in ms
        server_throughput[server] = measure_throughput(server)   # in kb/s
        logging.info(f'STARTUP: Server: {server} | Initial RTT: {server_rtt[server]}ms | Initial Throughput: {server_throughput[server]:.2f} KB/s')


def measure_rtt(server, num_pings = 3):
    total_time = 0
    for _ in range(num_pings):
        start_time = time.time()
        requests.get(f'http://{server}/output.mpd')
        end_time = time.time()
        
        total_time += end_time - start_time

    return int((total_time / num_pings ) * 1000)


def measure_throughput(server):
        start_time = time.time()
        response = requests.get(f'http://{server}/output.mpd')
        end_time = time.time()

        size_kb = len(response.content) / 1024
        rtt = end_time - start_time

        return size_kb / rtt


def calculate_weighted_avg_rtt(server, new_rtt):
    return ALPHA * server_rtt[server] + (1 - ALPHA) * new_rtt


def calculate_weighted_avg_throughput(server, new_throughput):
    return ALPHA * server_throughput[server] + (1 - ALPHA) * new_throughput


def monitor_servers():
    while True:
        for server in SERVERS:
            if user_count[server] == 0:
                try:
                    new_rtt = measure_rtt(server, num_pings=1)  # single ping
                    new_tp = measure_throughput(server)
                    
                    server_rtt[server] = calculate_weighted_avg_rtt(server, new_rtt)
                    server_throughput[server] = calculate_weighted_avg_throughput(server, new_tp)
                    
                    logging.info(f'MONITOR: Server: {server} | New RTT: {new_rtt}ms | Avg RTT: {server_rtt[server]:.2f}ms | Throughput {new_tp:.2f}kb/s | Avg Throughput: {server_throughput[server]:.2f}kb/s')
                except requests.exceptions.RequestException:
                    logging.error(f'UNREACHABLE | Server: {server} | Setting RTT to 9999ms')
                    server_rtt[server] = 9999
        time.sleep(5)


def calculate_score(server):
    # RTT, load, and throughput scores normalized 0 to 1
    rtt_val = min(server_rtt[server], MAX_RTT)
    rtt_score = 1.0 - (rtt_val / MAX_RTT)

    load_val = min(user_count[server], MAX_LOAD)
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
        init_server = TEST_SERVER if TEST_MODE else best_server
        client_server_assignment[client_ip] = init_server

        logging.info(f"NEW CLIENT (TestMode={TEST_MODE}): {client_ip} -> {init_server}")
        logging.info(f"INITIAL SCORES: S1: {server_score[SERVERS[0]]:.4f} | "
                     f"S2: {server_score[SERVERS[1]]:.4f} | S3: {server_score[SERVERS[2]]:.4f}")
        
        return init_server
        
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
    # reset client server assignment so they get new 'best server' selection
    if client_ip in client_server_assignment:
        del client_server_assignment[client_ip]
        logging.info(f"SESSION RESET: Client {client_ip} requested new manifest.")

    # get MPD file of any server with video
    content = None
    for server in SERVERS:
        try:
            response = requests.get(f'http://{server}/output.mpd', timeout=2)
            if response.status_code == 200:
                content = response.text
                origin_server = server
                break
        except requests.exceptions.RequestException:
            logging.warning(f"GET MPD FAIL: {server} unreachable, trying next server")
            continue

    if not content:
        return Response("No servers available for manifest", status=503)

    # replace MPD file URLs to point to proxy instead
    content = content.replace(f'http://{origin_server}', f'http://{request.host}')

    return Response(content, mimetype='application/dash+xml')

@app.route('/<path:segment>')
def get_segment(segment):
    client_ip = request.remote_addr
    server = select_server(client_ip)

    url = f'http://{server}/{segment}'

    # Send request to server, track RTT, throughput, and user count during request
    user_count[server] += 1

    start_time = time.time()
    response = requests.get(url)  
    end_time = time.time()
    time_taken = end_time - start_time

    # new RTT
    new_rtt = int((time_taken) * 1000)
    server_rtt[server] = calculate_weighted_avg_rtt(server, new_rtt)

    # new throughput for video segments
    if 'chunk' in segment:
        size_kb = len(response.content) / 1024
        new_throughput = size_kb / time_taken
        server_throughput[server] = calculate_weighted_avg_throughput(server, new_throughput)
    
    logging.info(f'GET SEGMENT: Client: {client_ip} | Server: {server} | Segment: {segment} | RTT: {new_rtt:.2f}ms | Avg RTT: {server_rtt[server]:.2f}ms | Avg Throughput: {server_throughput[server]:.2f}kb/s | Load: {user_count[server]}')

    user_count[server] -= 1

    return Response(response.content, mimetype='video/mp4')

#endregion

if __name__ == '__main__':
    startup()
    
    # start monitor in background thread
    monitor_thread = threading.Thread(target=monitor_servers, daemon=True)
    monitor_thread.start()
    
    app.run(host='0.0.0.0', port=5000)