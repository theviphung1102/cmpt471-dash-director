from mininet.topo import Topo
from mininet.net import Mininet
from mininet.nodelib import LinuxBridge
from mininet.cli import CLI
from mininet.log import setLogLevel, info
import os
import sys

class DASHTopo(Topo):
    def build(self, num_clients=1):
        # Using standard LinuxBridge to completely bypass all WSL2 kernel issues
        s1 = self.addSwitch('s1', cls=LinuxBridge) # Local Edge Switch
        # s2 = self.addSwitch('s2', cls=LinuxBridge) # Remote Core Switch

        # Add the client host
        if num_clients == 1:
            client = self.addHost('client', ip='10.0.0.1')
            self.addLink(client, s1)
        else:
            for i in range(1, num_clients + 1):
                # Giving them IPs starting from 10.0.0.10
                name = f'client{i}'
                ip_addr = f'10.0.0.{9 + i}' 
                c = self.addHost(name, ip=ip_addr)
                self.addLink(c, s1)
                print(f"Added {name} at {ip_addr}")

        # Add Local DASH Video Servers (Edge)
        server1 = self.addHost('server1', ip='10.0.0.2')
        self.addLink(server1, s1) 

        server2 = self.addHost('server2', ip='10.0.0.3')
        self.addLink(server2, s1) 

        # Add Remote DASH Video Server (Core)
        server3 = self.addHost('server3', ip='10.0.0.4')
        self.addLink(server3, s1) 
        
        # # Connect the Edge and Core switches
        # self.addLink(s1, s2)

        proxy = self.addHost('proxy', ip='10.0.0.5')
        self.addLink(proxy, s1)

def run():
    setLogLevel('info')
    os.system("sudo mn -c")
    num_clients = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    topo = DASHTopo(num_clients)
    
    # Standard Mininet initialization, disabled controller since LinuxBridge doesn't need one
    net = Mininet(topo=topo, controller=None)
    
    info('*** Starting Network ***\n')
    net.start()

    info('*** Adding route to Mininet network ***\n')
    os.system('ip route add 10.0.0.0/24 dev s1 2>/dev/null || true')

    info('*** Starting Proxy on Proxy Host ***\n')
    proxy_host = net.get('proxy')
    proxy_host.cmd('python3 selectProxy.py &')
    info(f'Proxy started at IP: {proxy_host.IP()}\n')

    info('*** Starting HTTP Servers on all Video Servers ***\n')
    # Automatically start a simple web server pointing to your video folder
    for server_name in ['server1', 'server2', 'server3']:
        host = net.get(server_name)
        host.cmd('python3 -m http.server 80 --directory video_sources &')
        info(f'{server_name} HTTP server started at IP: {host.IP()}\n')

    info('*** Running Mininet CLI ***\n')
    info('Type "client wget http://10.0.0.2/output.mpd" to test!\n')
    CLI(net)

    info('*** Stopping Network ***\n')
    proxy_host.cmd('pkill -f selectProxy.py')
    net.stop()

if __name__ == '__main__':
    run()