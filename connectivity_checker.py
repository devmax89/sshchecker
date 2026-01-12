"""
DIGIL SSH Connectivity Checker - Core Module
=============================================
Modulo per verificare la raggiungibilità dei dispositivi DIGIL
senza MAI accedere effettivamente ai dispositivi.

Test eseguiti:
1. Verifica raggiungibilità macchina ponte (bridge)
2. Ping verso il dispositivo DIGIL (dalla macchina ponte)
3. Test porta SSH (dalla macchina ponte) - solo verifica che risponda, no login
"""

import socket
import paramiko
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable
import os
from dotenv import load_dotenv

# Carica variabili d'ambiente
load_dotenv()


class ConnectionStatus(Enum):
    """Stati possibili per una connessione"""
    PENDING = "In attesa"
    TESTING = "In corso..."
    BRIDGE_UNREACHABLE = "Ponte non raggiungibile"
    PING_OK = "Ping OK"
    PING_FAILED = "Ping fallito"
    SSH_PORT_OPEN = "SSH OK"
    SSH_PORT_CLOSED = "SSH porta chiusa"
    SSH_TIMEOUT = "SSH timeout"
    ERROR = "Errore"
    VPN_ERROR = "VPN non connessa"


class DeviceType(Enum):
    """Tipo di dispositivo DIGIL"""
    MASTER = "master"
    SLAVE = "slave"
    UNKNOWN = "unknown"


class Vendor(Enum):
    """Vendor del dispositivo"""
    INDRA = "INDRA"
    SIRTI = "SIRTI"
    MII = "MII"  # Marini
    UNKNOWN = "UNKNOWN"


@dataclass
class DeviceInfo:
    """Informazioni di un dispositivo DIGIL"""
    device_id: str
    ip_address: str
    linea: str
    sostegno: str
    fornitore: str
    device_type: DeviceType = DeviceType.UNKNOWN
    vendor: Vendor = Vendor.UNKNOWN
    
    # Risultati test
    ping_status: ConnectionStatus = ConnectionStatus.PENDING
    ssh_status: ConnectionStatus = ConnectionStatus.PENDING
    ping_time_ms: Optional[float] = None
    error_message: str = ""
    test_timestamp: Optional[str] = None


def detect_device_type(device_id: str) -> DeviceType:
    """
    Rileva automaticamente il tipo di device dal deviceid.
    
    Pattern:
    - 1121525_xxxx → Master (contiene "15" nella parte centrale)
    - 1121621_xxxx → Slave (contiene "16" nella parte centrale)
    
    Esempi:
    - 1:1:2:16:21:DIGIL_MRN_0562 → slave
    - 1:1:2:15:25:DIGIL_SR2_0103 → master
    """
    device_id_str = str(device_id)
    
    # Cerca nel formato 1:1:2:XX:YY:DIGIL_...
    parts = device_id_str.split(":")
    if len(parts) >= 4:
        # La quarta parte (index 3) contiene 15 o 16
        type_indicator = parts[3]
        if type_indicator == "15":
            return DeviceType.MASTER
        elif type_indicator == "16":
            return DeviceType.SLAVE
    
    # Fallback: cerca ovunque nel deviceid
    if "15" in device_id_str and "16" not in device_id_str:
        return DeviceType.MASTER
    elif "16" in device_id_str:
        return DeviceType.SLAVE
    
    return DeviceType.UNKNOWN


def detect_vendor(device_id: str, fornitore: str = "") -> Vendor:
    """
    Rileva il vendor dal deviceid o dalla colonna fornitore.
    
    Pattern nel deviceid:
    - DIGIL_SR2_xxxx → SIRTI
    - DIGIL_MRN_xxxx → MII (Marini)
    - DIGIL_IND_xxxx → INDRA
    
    Pattern nel fornitore:
    - Lotto1-IndraOlivetti → INDRA
    - Lotto2-TelebitMarini → MII
    - Lotto3-Sirti → SIRTI
    """
    device_id_upper = str(device_id).upper()
    fornitore_upper = str(fornitore).upper()
    
    # Prima verifica dal deviceid (più affidabile)
    if "SR2" in device_id_upper or "_SR_" in device_id_upper:
        return Vendor.SIRTI
    elif "MRN" in device_id_upper or "_MR_" in device_id_upper:
        return Vendor.MII
    elif "IND" in device_id_upper:
        return Vendor.INDRA
    
    # Poi verifica dalla colonna fornitore
    if "SIRTI" in fornitore_upper:
        return Vendor.SIRTI
    elif "MARINI" in fornitore_upper or "TELEBIT" in fornitore_upper:
        return Vendor.MII
    elif "INDRA" in fornitore_upper or "OLIVETTI" in fornitore_upper:
        return Vendor.INDRA
    
    return Vendor.UNKNOWN


def normalize_ip(ip_raw) -> str:
    """
    Normalizza l'indirizzo IP.
    Alcuni IP nel file sono senza punti (es: 10183224247 invece di 10.183.224.247)
    """
    ip_str = str(ip_raw).strip()
    
    # Se contiene già i punti, è già formattato
    if "." in ip_str:
        return ip_str
    
    # Se è un numero lungo, prova a convertirlo
    # Formato atteso: 10.183.224.xxx
    if ip_str.isdigit() and len(ip_str) >= 9:
        # Pattern tipico: 10183224XXX -> 10.183.224.XXX
        try:
            # Prova a ricostruire l'IP
            if ip_str.startswith("10183224"):
                remaining = ip_str[8:]
                return f"10.183.224.{remaining}"
            elif ip_str.startswith("1018322"):
                remaining = ip_str[7:]
                return f"10.183.22.{remaining}"
        except:
            pass
    
    return ip_str


class BridgeConnection:
    """Gestisce la connessione alla macchina ponte"""
    
    def __init__(self):
        self.host = os.getenv("BRIDGE_HOST")
        self.user = os.getenv("BRIDGE_USER")
        self.password = os.getenv("BRIDGE_PASSWORD")
        self.timeout = int(os.getenv("BRIDGE_TIMEOUT", "10"))
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self._lock = threading.Lock()
        
        # Verifica che le credenziali siano configurate
        if not self.host or not self.user or not self.password:
            raise ValueError("Configurazione mancante nel file .env: BRIDGE_HOST, BRIDGE_USER, BRIDGE_PASSWORD")
        
    def connect(self) -> tuple[bool, str]:
        """
        Stabilisce la connessione alla macchina ponte.
        Ritorna (success, message)
        """
        with self._lock:
            if self.ssh_client and self.ssh_client.get_transport() and self.ssh_client.get_transport().is_active():
                return True, "Già connesso"
            
            try:
                self.ssh_client = paramiko.SSHClient()
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                self.ssh_client.connect(
                    hostname=self.host,
                    username=self.user,
                    password=self.password,
                    timeout=self.timeout,
                    allow_agent=False,
                    look_for_keys=False
                )
                return True, f"Connesso a {self.host}"
                
            except socket.timeout:
                return False, f"Timeout connessione a {self.host} - Verifica VPN"
            except socket.gaierror:
                return False, f"Impossibile risolvere {self.host} - Verifica VPN"
            except paramiko.AuthenticationException:
                return False, f"Autenticazione fallita per {self.user}@{self.host}"
            except Exception as e:
                return False, f"Errore connessione ponte: {str(e)}"
    
    def disconnect(self):
        """Chiude la connessione alla macchina ponte"""
        with self._lock:
            if self.ssh_client:
                try:
                    self.ssh_client.close()
                except:
                    pass
                self.ssh_client = None
    
    def is_connected(self) -> bool:
        """Verifica se la connessione è attiva"""
        with self._lock:
            return (self.ssh_client and 
                    self.ssh_client.get_transport() and 
                    self.ssh_client.get_transport().is_active())
    
    def execute_command(self, command: str, timeout: int = 10) -> tuple[bool, str, str]:
        """
        Esegue un comando sulla macchina ponte.
        Ritorna (success, stdout, stderr)
        """
        if not self.is_connected():
            success, msg = self.connect()
            if not success:
                return False, "", msg
        
        try:
            with self._lock:
                stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=timeout)
                out = stdout.read().decode('utf-8', errors='ignore')
                err = stderr.read().decode('utf-8', errors='ignore')
                return True, out, err
        except Exception as e:
            return False, "", str(e)


class DeviceChecker:
    """Classe per verificare la connettività di un singolo dispositivo"""
    
    # Timeout retry PING (aspettiamo il risveglio del device)
    MASTER_PING_RETRY_TIMEOUT = 300   # 5 minuti per master
    SLAVE_PING_RETRY_TIMEOUT = 1200   # 20 minuti per slave
    PING_RETRY_INTERVAL = 10          # Riprova ogni 10 secondi
    
    # Retry SSH (device già sveglio, pochi tentativi bastano)
    SSH_RETRY_ATTEMPTS = 5            # 5 tentativi per SSH
    SSH_RETRY_INTERVAL = 2            # Riprova ogni 2 secondi
    
    def __init__(self, bridge: BridgeConnection):
        self.bridge = bridge
        self.device_timeout = int(os.getenv("DEVICE_TIMEOUT", "5"))
        self.ssh_port = int(os.getenv("SSH_PORT", "22"))
        
    def check_ping_single(self, device: DeviceInfo) -> tuple[ConnectionStatus, Optional[float], str]:
        """
        Esegue UN SINGOLO ping verso il dispositivo dalla macchina ponte.
        Ritorna (status, ping_time_ms, error_message)
        """
        ip = normalize_ip(device.ip_address)
        
        # Comando ping con timeout breve (2 pacchetti, timeout 2 secondi ciascuno)
        cmd = f"ping -c 2 -W 2 {ip}"
        
        success, stdout, stderr = self.bridge.execute_command(cmd, timeout=10)
        
        if not success:
            return ConnectionStatus.ERROR, None, stderr
        
        # Analizza output ping
        if "0 received" in stdout or "100% packet loss" in stdout:
            return ConnectionStatus.PING_FAILED, None, "Nessuna risposta al ping"
        
        # Cerca il tempo medio di risposta
        ping_time = None
        for line in stdout.split('\n'):
            if 'avg' in line.lower() and '/' in line:
                try:
                    parts = line.split('=')[1].split('/')
                    ping_time = float(parts[1])
                except:
                    pass
        
        if "bytes from" in stdout or "0% packet loss" in stdout:
            return ConnectionStatus.PING_OK, ping_time, ""
        
        # Anche 50% packet loss consideriamo OK
        if "1 received" in stdout or "50% packet loss" in stdout:
            return ConnectionStatus.PING_OK, ping_time, ""
        
        return ConnectionStatus.PING_FAILED, None, "Risposta ping inconclusiva"
    
    def check_ping(self, device: DeviceInfo,
                   progress_callback: Optional[Callable[[DeviceInfo, str], None]] = None) -> tuple[ConnectionStatus, Optional[float], str]:
        """
        Esegue ping verso il dispositivo con retry basato sul tipo:
        - Master: 5 minuti (300s)
        - Slave: 20 minuti (1200s) - aspetta il risveglio
        
        Ritorna (status, ping_time_ms, error_message)
        
        NOTA: Non accede MAI al dispositivo, solo verifica raggiungibilità.
        """
        import time
        
        # Determina timeout in base al tipo di device
        if device.device_type == DeviceType.MASTER:
            max_retry_seconds = self.MASTER_PING_RETRY_TIMEOUT
            device_type_str = "Master"
        else:
            max_retry_seconds = self.SLAVE_PING_RETRY_TIMEOUT
            device_type_str = "Slave"
        
        start_time = time.time()
        attempt = 0
        last_error = ""
        
        while True:
            attempt += 1
            elapsed = time.time() - start_time
            remaining = int(max_retry_seconds - elapsed)
            
            if progress_callback:
                minutes = remaining // 60
                seconds = remaining % 60
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                progress_callback(device, f"Ping tentativo {attempt} ({device_type_str}, {time_str} rimanenti)...")
            
            # Prova ping
            status, ping_time, error = self.check_ping_single(device)
            
            if status == ConnectionStatus.PING_OK:
                return status, ping_time, ""
            
            last_error = error
            
            # Controlla se abbiamo superato il timeout
            if elapsed >= max_retry_seconds:
                minutes = max_retry_seconds // 60
                return ConnectionStatus.PING_FAILED, None, f"Ping fallito dopo {attempt} tentativi ({minutes} min). {last_error}"
            
            # Aspetta prima di riprovare
            time.sleep(self.PING_RETRY_INTERVAL)
    
    def check_ssh_port(self, device: DeviceInfo) -> tuple[ConnectionStatus, str]:
        """
        Verifica se la porta SSH è aperta sul dispositivo.
        
        IMPORTANTE: NON esegue login, solo verifica che la porta risponda.
        Usa nc (netcat) o un tentativo di connessione socket dalla macchina ponte.
        """
        ip = normalize_ip(device.ip_address)
        
        # Usa timeout di netcat per verificare la porta
        # -z = zero-I/O mode (solo scan), -w = timeout
        cmd = f"timeout 5 bash -c 'echo > /dev/tcp/{ip}/{self.ssh_port}' 2>&1 && echo 'PORT_OPEN' || echo 'PORT_CLOSED'"
        
        success, stdout, stderr = self.bridge.execute_command(cmd, timeout=10)
        
        if not success:
            # Prova metodo alternativo con nc
            cmd_alt = f"nc -z -w 5 {ip} {self.ssh_port} && echo 'PORT_OPEN' || echo 'PORT_CLOSED'"
            success, stdout, stderr = self.bridge.execute_command(cmd_alt, timeout=10)
            
            if not success:
                return ConnectionStatus.ERROR, f"Errore verifica SSH: {stderr}"
        
        if "PORT_OPEN" in stdout:
            return ConnectionStatus.SSH_PORT_OPEN, ""
        elif "PORT_CLOSED" in stdout or "Connection refused" in stdout:
            return ConnectionStatus.SSH_PORT_CLOSED, "Porta SSH chiusa o rifiutata"
        elif "timed out" in stdout.lower() or "timeout" in stdout.lower():
            return ConnectionStatus.SSH_TIMEOUT, "Timeout connessione SSH"
        else:
            return ConnectionStatus.SSH_PORT_CLOSED, stdout.strip()
    
    def check_ssh_port_with_retry(self, device: DeviceInfo,
                                   progress_callback: Optional[Callable[[DeviceInfo, str], None]] = None) -> tuple[ConnectionStatus, str]:
        """
        Verifica porta SSH con 5 tentativi rapidi.
        (Il device è già sveglio dopo il ping OK, quindi pochi retry bastano)
        """
        import time
        
        last_error = ""
        
        for attempt in range(1, self.SSH_RETRY_ATTEMPTS + 1):
            if progress_callback:
                progress_callback(device, f"SSH check tentativo {attempt}/{self.SSH_RETRY_ATTEMPTS}...")
            
            # Prova SSH
            status, error = self.check_ssh_port(device)
            
            if status == ConnectionStatus.SSH_PORT_OPEN:
                return status, ""
            
            last_error = error
            
            # Se non è l'ultimo tentativo, aspetta prima di riprovare
            if attempt < self.SSH_RETRY_ATTEMPTS:
                time.sleep(self.SSH_RETRY_INTERVAL)
        
        return ConnectionStatus.SSH_PORT_CLOSED, f"SSH fallito dopo {self.SSH_RETRY_ATTEMPTS} tentativi. {last_error}"
    
    def full_check(self, device: DeviceInfo, 
                   progress_callback: Optional[Callable[[DeviceInfo, str], None]] = None) -> DeviceInfo:
        """
        Esegue il check completo di un dispositivo:
        1. Ping con retry lunghi (aspetta risveglio: 5min master, 20min slave)
        2. SSH con 5 retry rapidi (device già sveglio)
        
        NOTA: Non accede MAI al dispositivo.
        """
        from datetime import datetime
        
        device.test_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Determina tipo e vendor se non già fatto
        if device.device_type == DeviceType.UNKNOWN:
            device.device_type = detect_device_type(device.device_id)
        if device.vendor == Vendor.UNKNOWN:
            device.vendor = detect_vendor(device.device_id, device.fornitore)
        
        # Notifica inizio test
        retry_minutes = self.MASTER_PING_RETRY_TIMEOUT // 60 if device.device_type == DeviceType.MASTER else self.SLAVE_PING_RETRY_TIMEOUT // 60
        if progress_callback:
            progress_callback(device, f"Ping in corso (max {retry_minutes} min per {device.device_type.value})...")
        
        # Step 1: Ping CON RETRY LUNGHI (aspetta risveglio)
        device.ping_status, device.ping_time_ms, error = self.check_ping(device, progress_callback)
        
        if device.ping_status != ConnectionStatus.PING_OK:
            device.ssh_status = ConnectionStatus.PENDING
            device.error_message = error
            if progress_callback:
                progress_callback(device, f"Ping fallito: {error}")
            return device
        
        # Step 2: SSH CON 5 RETRY RAPIDI (device già sveglio)
        if progress_callback:
            ping_ms = f"{device.ping_time_ms:.1f}ms" if device.ping_time_ms else "OK"
            progress_callback(device, f"Ping {ping_ms}! SSH check ({self.SSH_RETRY_ATTEMPTS} tentativi)...")
        
        device.ssh_status, error = self.check_ssh_port_with_retry(device, progress_callback)
        
        if error:
            device.error_message = error
        
        if progress_callback:
            status_msg = "SSH OK ✓" if device.ssh_status == ConnectionStatus.SSH_PORT_OPEN else f"SSH fallito: {error}"
            progress_callback(device, f"Completato: {status_msg}")
        
        return device


class MultiThreadChecker:
    """Gestisce l'esecuzione multi-thread dei test"""
    
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.bridge = BridgeConnection()
        self._stop_flag = threading.Event()
        self._results: list[DeviceInfo] = []
        self._results_lock = threading.Lock()
        self._active_threads: list[threading.Thread] = []
        
    def stop(self):
        """Ferma l'esecuzione dei test"""
        self._stop_flag.set()
        
    def reset(self):
        """Reset per nuovo batch di test"""
        self._stop_flag.clear()
        self._results = []
        self._active_threads = []
        
    def check_devices(self, devices: list[DeviceInfo],
                      progress_callback: Optional[Callable[[DeviceInfo, str, int, int], None]] = None,
                      completion_callback: Optional[Callable[[list[DeviceInfo]], None]] = None,
                      bridge_callback: Optional[Callable[[bool, str], None]] = None) -> list[DeviceInfo]:
        """
        Esegue i test su tutti i dispositivi in parallelo.
        
        Args:
            devices: Lista di dispositivi da testare
            progress_callback: Callback chiamata per ogni aggiornamento (device, message, current, total)
            completion_callback: Callback chiamata al completamento
            bridge_callback: Callback per stato connessione ponte (connected, message)
        """
        self.reset()
        
        # Prima verifica connessione ponte
        if bridge_callback:
            bridge_callback(None, f"Connessione a {self.bridge.host}...")
        
        success, msg = self.bridge.connect()
        
        if bridge_callback:
            bridge_callback(success, msg)
        
        if not success:
            # Tutti i dispositivi segnati come errore VPN/ponte
            for dev in devices:
                dev.ping_status = ConnectionStatus.VPN_ERROR
                dev.ssh_status = ConnectionStatus.VPN_ERROR
                dev.error_message = msg
                self._results.append(dev)
            if completion_callback:
                completion_callback(self._results)
            return self._results
        
        total = len(devices)
        completed = [0]  # Usa lista per permettere modifica in closure
        
        def worker(device: DeviceInfo):
            if self._stop_flag.is_set():
                return
            
            checker = DeviceChecker(self.bridge)
            
            def local_progress(dev, msg):
                if progress_callback:
                    progress_callback(dev, msg, completed[0], total)
            
            result = checker.full_check(device, local_progress)
            
            with self._results_lock:
                self._results.append(result)
                completed[0] += 1
                
            if progress_callback:
                progress_callback(result, "Completato", completed[0], total)
        
        # Crea thread pool
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(worker, dev): dev for dev in devices}
            
            for future in as_completed(futures):
                if self._stop_flag.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    future.result()
                except Exception as e:
                    dev = futures[future]
                    dev.error_message = str(e)
                    dev.ping_status = ConnectionStatus.ERROR
        
        # Cleanup
        self.bridge.disconnect()
        
        if completion_callback:
            completion_callback(self._results)
        
        return self._results


if __name__ == "__main__":
    # Test di base
    print("Test modulo connectivity_checker")
    
    # Test detect_device_type
    test_ids = [
        "1:1:2:16:21:DIGIL_MRN_0562",
        "1:1:2:15:25:DIGIL_SR2_0103",
        "1:1:2:16:25:DIGIL_SR2_0163",
        "1:1:2:15:22:DIGIL_MRN_0053",
    ]
    
    for did in test_ids:
        dtype = detect_device_type(did)
        vendor = detect_vendor(did)
        print(f"{did} -> Type: {dtype.value}, Vendor: {vendor.value}")
    
    # Test normalize_ip
    test_ips = ["10.183.224.97", "10183224247", "10183224250"]
    for ip in test_ips:
        print(f"IP: {ip} -> {normalize_ip(ip)}")