from mininet.topo import Topo
from mininet.net import Mininet
from mininet.nodelib import LinuxBridge
from mininet.cli import CLI
from mininet.log import setLogLevel, info
import os

class DASHTopo(Topo):
    def build(self):
        # Using standard LinuxBridge to completely bypass all WSL2 kernel issues
        s1 = self.addSwitch('s1', cls=LinuxBridge)

        # Add the client host
        client = self.addHost('client', ip='10.0.0.1')
        self.addLink(client, s1) 

        # Add 3 DASH Video Servers 
        server1 = self.addHost('server1', ip='10.0.0.2')
        self.addLink(server1, s1) 

        server2 = self.addHost('server2', ip='10.0.0.3')
        self.addLink(server2, s1) 

        server3 = self.addHost('server3', ip='10.0.0.4')
        self.addLink(server3, s1) 

def run():
    setLogLevel('info')
    topo = DASHTopo()
    
    # Standard Mininet initialization, disabled controller since LinuxBridge doesn't need one
    net = Mininet(topo=topo, controller=None)
    
    info('*** Starting Network ***\n')
    net.start()

    info('*** Adding route to Mininet network ***\n')
    os.system('ip route add 10.0.0.0/24 dev s1 2>/dev/null || true')

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
    net.stop()

if __name__ == '__main__':
    run()