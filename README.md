# CMPT 471 DASH Director

## Quick Start
1. **Pull the latest code:** `git pull origin main`
2. **Start the Network:** Run `sudo python3 mininet_topo.py` in the Ubuntu terminal.
3. **Play the Video:** Open `videoPlayer.html` and click play.

## Project Structure
* `mininet_topo.py`: The network topology. Uses `LinuxBridge` for WSL2 compatibility.
* `selectProxy.py`: Proxy server source selection mechanism implementation.
* `video_sources/`: Contains the DASH manifest and video chunks.
* `sample.mp4`: The original source video.
* `test#-commands.txt`: Command files for test scenarios (to run in Mininet CLI, see report to run).
* `simulate_users.py`: Simulates multiple concurrent users (see report to run).

## Network Map
* **Client:** 10.0.0.1
* **Server 1:** 10.0.0.2 (Primary)
* **Server 2:** 10.0.0.3 (Secondary)
* **Server 3:** 10.0.0.4 (Backup)
* **Proxy Server**: 10.0.0.5

