import matplotlib.pyplot as plt
import re
import glob
import os
from datetime import datetime

print("Looking for the most recent proxy log...")

# Find the newest log file in the logs/ directory
log_files = glob.glob('logs/*.log')
if not log_files:
    print("No log files found! Run your proxy first.")
    exit()

latest_log = max(log_files, key=os.path.getctime)
print(f"Plotting data from: {latest_log}")

times = []
tp_s1, tp_s2, tp_s3 = [], [], []

# Regex to catch the Avg Throughput from the MONITOR logs
log_pattern = re.compile(r'(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \| MONITOR: Server: (?P<ip>10\.0\.0\.\d) \|.*?Avg Throughput: (?P<tp>[\d\.]+)kb/s')

current_time = None
temp_tp = {'10.0.0.2': 0, '10.0.0.3': 0, '10.0.0.4': 0}

# Parse the log file line by line
with open(latest_log, 'r') as f:
    for line in f:
        match = log_pattern.search(line)
        if match:
            t_str = match.group('time')
            ip = match.group('ip')
            tp = float(match.group('tp'))
            
            dt = datetime.strptime(t_str, '%Y-%m-%d %H:%M:%S')
            
            # Group the 3 server pings that happen at the same second
            if current_time != dt:
                if current_time is not None:
                    times.append(current_time)
                    tp_s1.append(temp_tp['10.0.0.2'])
                    tp_s2.append(temp_tp['10.0.0.3'])
                    tp_s3.append(temp_tp['10.0.0.4'])
                current_time = dt
            
            temp_tp[ip] = tp

# Append the final batch
if current_time is not None:
    times.append(current_time)
    tp_s1.append(temp_tp['10.0.0.2'])
    tp_s2.append(temp_tp['10.0.0.3'])
    tp_s3.append(temp_tp['10.0.0.4'])

# Build the Graph 
plt.figure(figsize=(10, 5))
plt.plot(times, tp_s1, label='Server 1 (Local Edge)', color='blue', linewidth=2)
plt.plot(times, tp_s2, label='Server 2 (Local Edge)', color='green', linewidth=2)
plt.plot(times, tp_s3, label='Server 3 (Remote Core)', color='red', linewidth=2)

plt.title('DASH Video Proxy: Server Throughput Over Time')
plt.xlabel('Time')
plt.ylabel('Average Throughput (kb/s)')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.7)
plt.xticks(rotation=45)
plt.tight_layout()

# Save the image automatically
image_name = 'throughput_graph.png'
plt.savefig(image_name)
print(f"Success! Graph saved as {image_name}")