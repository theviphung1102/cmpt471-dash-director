#!/bin/bash

echo "Starting CMPT 471 Stress Test..."
echo "Baseline running for 10 seconds..."
sleep 10

echo "[0:10] Injecting 50% Packet Loss on Server 1!"
# mnexec runs the command inside the Mininet virtual host
sudo mnexec -a server1 tc qdisc add dev server1-eth0 root netem loss 50%
sleep 15

echo "[0:25] Restoring Server 1, crushing Server 2 bandwidth!"
sudo mnexec -a server1 tc qdisc del dev server1-eth0 root
sudo mnexec -a server2 tc qdisc add dev server2-eth0 root netem tbf rate 500kbit burst 32kbit lat 400ms
sleep 15

echo "[0:40] Test complete. Restoring all servers."
sudo mnexec -a server2 tc qdisc del dev server2-eth0 root
echo "Done! Check your proxy logs."