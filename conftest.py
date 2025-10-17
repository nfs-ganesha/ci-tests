from pathlib import Path

def pytest_addoption(parser):
    parser.addoption("--system-type", action="store", default="baremetal",
                     help="System type: baremetal|openstack|centos")
    parser.addoption("--admin-ip", action="store",
                     help="Admin node IP")
    parser.addoption("--server-ips", action="store", nargs="*",
                     help="List of server node IPs (optional)")
    parser.addoption("--client-ips", action="store", nargs="*",
                     help="List of client node IPs (optional)")
    parser.addoption("--ces-ips", action="store", nargs="*",
                     help="List of CES IPs (optional)")
    parser.addoption("--ssh-key", action="store", default=str(Path.home() / ".ssh/id_rsa"),
                     help="Path to SSH private key")
    parser.addoption("--username", action="store", default="root",
                     help="Username for SSH login")
    parser.addoption("--password", action="store",
                     help="Username for SSH login")
    parser.addoption("--scale-installer", action="store",
                     help="Path or URL to Spectrum Scale installer")
    parser.addoption("--cthon-instances", action="store", default="2", 
                     help="Number of parallel Cthon instances")
    parser.addoption("--cthon-repeat", action="store", default="1",
                     help="Number of repeats for Cthon serially")
    parser.addoption("--cthon-timeout", action="store", default="86400",
                     help="Timeout in seconds for Cthon. Default is set to 24 hours")