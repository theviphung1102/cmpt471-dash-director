# CMPT 471 DASH Director

## Quick Start (For Partner)
1. **Pull the latest code:** `git pull origin main`
2. **Start the Network:** Run `sudo python3 mininet_topo.py` in the Ubuntu terminal.
3. **Test the Server:** Inside the `mininet>` prompt, run:
   `client wget http://10.0.0.2/output.mpd`
4. **Start the Proxy:** Run `sudo python3 selectProxy.pyy` in a new seperate Ubuntu terminal.
5. **Play the Video:** Open `videoPlayer.html` and click play.

## Project Structure
* `mininet_topo.py`: The network topology. Uses `LinuxBridge` for WSL2 compatibility.
* `video_sources/`: Contains the DASH manifest and video chunks.
* `sample.mp4`: The original source video.

## Network Map
* **Client:** 10.0.0.1
* **Server 1:** 10.0.0.2 (Primary)
* **Server 2:** 10.0.0.3 (Secondary)
* **Server 3:** 10.0.0.4 (Backup)

## Current Status
Role A (Infrastructure) is complete. The servers are successfully hosting the DASH segments. 
**Next Step (Role B):** Implement the Selection Controller logic to monitor these servers and route the client.
