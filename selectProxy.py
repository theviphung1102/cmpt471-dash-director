from flask import Flask, request, Response
from flask_cors import CORS
import requests
import time
import threading
import logging
from datetime import datetime
import os

SERVERS = ['10.0.0.2', '10.0.0.3', '10.0.0.4']
ALPHA = 0.7
RTT_WEIGHT = 0.6
LOAD_WEIGHT = 0.4

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
        server_throughput[server] = measure_rtt(server)   # in kb/s
        logging.info(f'STARTUP: Server: {server} | Initial RTT: {server_rtt[server]}ms | Initial Throughput: {server_throughput[server]:.2f} KB/s')


def measure_rtt(server, num_pings = 3):
    total_time = 0
    for _ in range(num_pings):
        start_time = time.time()
        requests.head(f'http://{server}/output.mpd')
        end_time = time.time()
        
        total_time += end_time - start_time

    return int((total_time / num_pings ) * 1000)


def measure_throughput(server):
        start_time = time.time()
        response = requests.head(f'http://{server}/output.mpd')
        end_time = time.time()

        size_kb = len(response.content) / 1024
        rtt = end_time - start_time

        return size_kb / rtt


def calculate_weighted_avg_rtt(server, new_rtt):
    return int(ALPHA * server_rtt[server] + (1 - ALPHA) * new_rtt)


def calculate_weighted_avg_throughput(server, new_throughput):
    return int(ALPHA * server_throughput[server] + (1 - ALPHA) * new_throughput)


def monitor_servers():
    while True:
        for server in SERVERS:
            if user_count[server] == 0:
                try:
                    new_rtt = measure_rtt(server, num_pings=1)  # single ping
                    server_rtt[server] = calculate_weighted_avg_rtt(server, new_rtt)
                    logging.info(f'MONITOR: Server: {server} | New RTT: {new_rtt}ms | Smoothed RTT: {server_rtt[server]}ms')
                except requests.exceptions.RequestException:
                    logging.error(f'UNREACHABLE | Server: {server} | Setting RTT to 9999ms')
                    server_rtt[server] = 9999
        time.sleep(5)


def calculate_score(server):
    # normalize values on a scale of 0 to 1. Best server gets 1, worse gets 0.
    min_rtt = min(server_rtt.values())
    max_rtt = max(server_rtt.values())
    
    min_load = min(user_count.values())
    max_load = max(user_count.values())

    min_tp = min(server_throughput.values())
    max_tp = max(server_throughput.values())

    if max_rtt == min_rtt:
        rtt_score = 1.0
    else:
        rtt_score = 1 - ((server_rtt[server] - min_rtt) / (max_rtt - min_rtt))
    
    if max_load == min_load:
        load_score = 1.0
    else:
        load_score = 1 - ((user_count[server] - min_load) / (max_load - min_load))

    if max_tp == min_tp:
        tp_score = 1.0
    else:
        tp_score = (server_throughput[server] - min_tp) / (max_tp - min_tp)

    score = (rtt_score + load_score + tp_score) / 3

    server_score[server] = score

    return score


def select_server(client_ip):
    current_server = client_server_assignment.get(client_ip, None)

    for server in SERVERS:
        calculate_score(server)

    best_server = max(SERVERS, key=lambda s: server_score[s])

    # new client, first request, return best server
    if not current_server:
        client_server_assignment[client_ip] = best_server
        logging.info(f'NEW CLIENT: Client: {client_ip} | Assigned to: {best_server} | Score: {server_score[best_server]:.6f}')
        return best_server
        
    # switch servers only if 20% performance gain
    if server_score[best_server] > server_score[current_server] * 1.2:
        client_server_assignment[client_ip] = best_server
        logging.info(f'SWITCH SERVER: Client: {client_ip} | {current_server} -> {best_server} | Score gain: {(server_score[best_server]/server_score[current_server]):.2f}x')
        return best_server
    
    logging.info(f'KEEP SERVER: Client: {client_ip} | Keeping: {current_server} | Score: {server_score[current_server]:.6f}')
    return current_server

#endregion

# region ROUTING
@app.route('/output.mpd')
def get_mpd():
    # get MPD file of any server with video
    server = SERVERS[0]
    response = requests.get(f'http://{server}/output.mpd')

    # replace MPD file URLs to point to proxy instead
    content = response.text
    content = content.replace(f'http://{server}', f'http://{request.host}')

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

    # new throughput
    size_kb = len(response.content) / 1024
    new_throughput = size_kb / time_taken
    server_throughput[server] = calculate_weighted_avg_throughput(server, new_throughput)
    
    logging.info(f'GET SEGMENT: Client: {client_ip} | Server: {server} | RTT: {new_rtt}ms | Avg RTT: {server_rtt[server]}ms | Avg Throughput: {server_throughput[server]}kb/s | Load: {user_count[server]}')

    user_count[server] -= 1

    return Response(response.content, mimetype='video/mp4')

#endregion

if __name__ == '__main__':
    startup()
    
    # start monitor in background thread
    monitor_thread = threading.Thread(target=monitor_servers, daemon=True)
    monitor_thread.start()
    
    app.run(host='0.0.0.0', port=5000)
