# test_tunnel.py
import os
from dotenv import load_dotenv

load_dotenv()

print("=== TEST CONFIGURAZIONE ===")
print(f"BRIDGE_HOST: {os.getenv('BRIDGE_HOST')}")
print(f"BRIDGE_USER: {os.getenv('BRIDGE_USER')}")
print(f"MONGO_URI: {os.getenv('MONGO_URI')[:50]}...")

print("\n=== TEST IMPORT SSHTUNNEL ===")
try:
    from sshtunnel import SSHTunnelForwarder
    print("✅ sshtunnel importato correttamente")
except Exception as e:
    print(f"❌ Errore: {type(e).__name__}: {e}")

print("\n=== TEST PARSE MONGO HOSTS ===")
import re
mongo_uri = os.getenv("MONGO_URI", "")
match = re.search(r'@([^/\?]+)', mongo_uri)
if match:
    hosts_str = match.group(1)
    print(f"Hosts trovati: {hosts_str}")
    for host_port in hosts_str.split(','):
        if ':' in host_port:
            host, port = host_port.split(':')
            print(f"  - {host}:{port}")
else:
    print("❌ Nessun host trovato nella MONGO_URI")

print("\n=== TEST CREAZIONE TUNNEL ===")
try:
    from sshtunnel import SSHTunnelForwarder
    import socket
    
    # Trova porta libera
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        local_port = s.getsockname()[1]
    
    print(f"Porta locale: {local_port}")
    print(f"Creazione tunnel verso: epmvlmngiotcfg3.servizi.prv:27017")
    
    tunnel = SSHTunnelForwarder(
        (os.getenv("BRIDGE_HOST"), 22),
        ssh_username=os.getenv("BRIDGE_USER"),
        ssh_password=os.getenv("BRIDGE_PASSWORD"),
        remote_bind_address=("epmvlmngiotcfg3.servizi.prv", 27017),
        local_bind_address=('127.0.0.1', local_port),
    )
    
    print("Avvio tunnel...")
    tunnel.start()
    
    if tunnel.is_active:
        print(f"✅ Tunnel attivo! localhost:{tunnel.local_bind_port}")
        tunnel.stop()
        print("Tunnel chiuso")
    else:
        print("❌ Tunnel non attivo")
        
except Exception as e:
    print(f"❌ Errore: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()