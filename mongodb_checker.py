"""
DIGIL Diagnostic Checker - MongoDB Checker Module
==================================================
Verifica se i dispositivi hanno inviato dati nelle ultime 24 ore
tramite query MongoDB attraverso SSH tunnel.

IMPORTANTE: Non installa nulla sulla macchina ponte!
La connessione MongoDB avviene dal PC locale attraverso un tunnel SSH.
"""

import os
import threading
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class MongoCheckResult:
    """Risultato del check MongoDB per un dispositivo"""
    device_id: str
    has_data_24h: bool = False
    last_timestamp: Optional[datetime] = None
    last_timestamp_ms: Optional[int] = None
    error: str = ""
    checked: bool = False


class SSHTunnelManager:
    """
    Gestisce un tunnel SSH verso MongoDB attraverso la macchina ponte.
    
    Architettura:
    PC Locale:27017 → SSH Tunnel → Macchina Ponte → MongoDB:27017
    
    In questo modo pymongo gira LOCALMENTE e si connette a localhost,
    il traffico viene inoltrato attraverso la macchina ponte verso MongoDB.
    """
    
    def __init__(self):
        self.tunnel = None
        self.local_port = None
        self._lock = threading.Lock()
        
        # Configurazione dal .env
        self.bridge_host = os.getenv("BRIDGE_HOST")
        self.bridge_user = os.getenv("BRIDGE_USER")
        self.bridge_password = os.getenv("BRIDGE_PASSWORD")
        
        # Parse MongoDB hosts dalla URI
        self.mongo_uri = os.getenv("MONGO_URI", "")
        self.mongo_hosts = self._parse_mongo_hosts()
        
    def _parse_mongo_hosts(self) -> list:
        """Estrae gli host MongoDB dalla URI."""
        # URI format: mongodb://user:pass@host1:port,host2:port,host3:port/?options
        import re
        
        if not self.mongo_uri:
            return []
        
        # Trova la parte tra @ e /?
        match = re.search(r'@([^/\?]+)', self.mongo_uri)
        if not match:
            return []
        
        hosts_str = match.group(1)
        hosts = []
        
        for host_port in hosts_str.split(','):
            if ':' in host_port:
                host, port = host_port.split(':')
                hosts.append((host.strip(), int(port)))
            else:
                hosts.append((host_port.strip(), 27017))
        
        return hosts
    
    def start_tunnel(self) -> tuple[bool, str, int]:
        """
        Avvia il tunnel SSH verso MongoDB.
        
        Returns:
            (success, message, local_port)
        """
        with self._lock:
            if self.tunnel and self.tunnel.is_active:
                return True, "Tunnel già attivo", self.local_port
            
            if not self.mongo_hosts:
                return False, "Nessun host MongoDB configurato nella MONGO_URI", 0
            
            # Verifica che sshtunnel sia installato
            try:
                from sshtunnel import SSHTunnelForwarder
            except ImportError as e:
                return False, f"Libreria sshtunnel non trovata. Installa con: pip install sshtunnel. Errore: {str(e)}", 0
            except Exception as e:
                return False, f"Errore import sshtunnel: {type(e).__name__}: {str(e)}", 0
            
            
            try:
                # Usa il primo host MongoDB disponibile
                mongo_host, mongo_port = self.mongo_hosts[0]
                
                # Trova una porta locale libera
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', 0))
                    self.local_port = s.getsockname()[1]
                
                self.tunnel = SSHTunnelForwarder(
                    (self.bridge_host, 22),
                    ssh_username=self.bridge_user,
                    ssh_password=self.bridge_password,
                    remote_bind_address=(mongo_host, mongo_port),
                    local_bind_address=('127.0.0.1', self.local_port),
                    set_keepalive=30
                )
                
                self.tunnel.start()
                
                # Attendi che il tunnel sia pronto
                time.sleep(1)
                
                if self.tunnel.is_active:
                    return True, f"Tunnel attivo: localhost:{self.local_port} → {mongo_host}:{mongo_port}", self.local_port
                else:
                    return False, "Tunnel non si è avviato correttamente", 0
                    
            except ImportError:
                return False, "Libreria sshtunnel non installata. Installa con: pip install sshtunnel", 0
            except Exception as e:
                return False, f"Errore creazione tunnel: {str(e)}", 0
    
    def stop_tunnel(self):
        """Ferma il tunnel SSH."""
        with self._lock:
            if self.tunnel:
                try:
                    self.tunnel.stop()
                except:
                    pass
                self.tunnel = None
                self.local_port = None
    
    def is_active(self) -> bool:
        """Verifica se il tunnel è attivo."""
        return self.tunnel is not None and self.tunnel.is_active


class MongoDBChecker:
    """
    Verifica la presenza di dati MongoDB per i dispositivi DIGIL.
    
    Usa un tunnel SSH attraverso la macchina ponte per connettersi
    a MongoDB senza installare nulla sulla macchina ponte.
    """
    
    def __init__(self, tunnel_manager: Optional[SSHTunnelManager] = None):
        """
        Args:
            tunnel_manager: Gestore del tunnel SSH. Se None, ne crea uno nuovo.
        """
        self.tunnel_manager = tunnel_manager or SSHTunnelManager()
        self.mongo_uri = os.getenv("MONGO_URI", "")
        self.database = os.getenv("MONGO_DATABASE", "ibm_iot")
        self.collection_name = os.getenv("MONGO_COLLECTION", "event")
        self.collection_diags_name = os.getenv("MONGO_COLLECTION_DIAGS", "diagnostics")
        self._client = None
        self._collection = None
        self._collection_diags = None
        
    def connect(self) -> tuple[bool, str]:
        """
        Stabilisce la connessione a MongoDB attraverso il tunnel SSH.
        
        Returns:
            (success, message)
        """
        # Avvia il tunnel se non attivo
        if not self.tunnel_manager.is_active():
            success, msg, port = self.tunnel_manager.start_tunnel()
            if not success:
                return False, msg
        
        try:
            from pymongo import MongoClient
            
            # Costruisci URI per connessione locale attraverso il tunnel
            # Estrai credenziali dalla URI originale
            import re
            
            # Pattern per estrarre user:password
            creds_match = re.search(r'mongodb://([^:]+):([^@]+)@', self.mongo_uri)
            if creds_match:
                user = creds_match.group(1)
                password = creds_match.group(2)
            else:
                return False, "Impossibile estrarre credenziali dalla MONGO_URI"
            
            # Estrai authSource e altre opzioni
            options_match = re.search(r'\?(.+)$', self.mongo_uri)
            options = options_match.group(1) if options_match else "authSource=ibm_iot"
            
            # URI locale attraverso tunnel
            local_uri = f"mongodb://{user}:{password}@127.0.0.1:{self.tunnel_manager.local_port}/?{options}"
            
            self._client = MongoClient(local_uri, serverSelectionTimeoutMS=10000)
            
            # Test connessione
            self._client.admin.command('ping')
            
            db = self._client[self.database]
            self._collection = db[self.collection_name]
            self._collection_diags = db[self.collection_diags_name]
            
            return True, "Connesso a MongoDB via tunnel SSH"
            
        except ImportError:
            return False, "pymongo non installato. Installa con: pip install pymongo"
        except Exception as e:
            return False, f"Errore connessione MongoDB: {str(e)}"
    
    def disconnect(self):
        """Chiude la connessione MongoDB."""
        if self._client:
            try:
                self._client.close()
            except:
                pass
            self._client = None
            self._collection = None
    
    def check_device(self, device_id: str) -> MongoCheckResult:
        """
        Verifica se il dispositivo ha inviato dati nelle ultime 24 ore.
        
        Args:
            device_id: Il clientId del dispositivo (es: "1:1:2:15:22:DIGIL_MRN_0051")
            
        Returns:
            MongoCheckResult con i risultati del check
        """
        result = MongoCheckResult(device_id=device_id)
        
        # Verifica connessione
        if self._collection is None:
            success, msg = self.connect()
            if not success:
                result.error = msg
                return result
        
        try:
            # Calcola timestamp 24h fa in millisecondi
            now = datetime.now()
            yesterday = now - timedelta(hours=24)
            start_ms = int(yesterday.timestamp() * 1000)
            end_ms = int(now.timestamp() * 1000)
            
            # Query aggregation
            pipeline = [
                {
                    "$match": {
                        "clientId": device_id,
                        "payload.metrics.TIMESTAMP.value": {
                            "$gte": start_ms,
                            "$lte": end_ms
                        }
                    }
                },
                {"$sort": {"receivedOn": -1}},
                {"$limit": 1},
                {
                    "$project": {
                        "_id": 0,
                        "clientId": 1,
                        "timestamp": "$payload.metrics.TIMESTAMP.value"
                    }
                }
            ]
            
            results = list(self._collection.aggregate(pipeline))
            
            if results:
                result.has_data_24h = True
                result.checked = True
                ts = results[0].get("timestamp")
                if ts:
                    result.last_timestamp_ms = int(ts)
                    result.last_timestamp = datetime.fromtimestamp(ts / 1000.0)
            else:
                result.has_data_24h = False
                result.checked = True
            
        except Exception as e:
            result.error = str(e)[:150]
        
        return result
    
    def get_soc_history(self, device_id: str, days: int = 15) -> dict:
        """
        Recupera lo storico SOC (State of Charge) per un dispositivo.
        Prende un valore per giorno (l'ultimo disponibile).
        
        Args:
            device_id: Il clientId del dispositivo
            days: Numero di giorni da analizzare (default 15)
            
        Returns:
            Dict con:
                - device_id: str
                - daily_soc: dict {date_str: soc_value} es: {"2026-01-19": 99, "2026-01-18": 98}
                - avg: float (media)
                - min: int (minimo)
                - max: int (massimo)
                - trend: str ("↑", "↓", "→")
                - error: str (eventuale errore)
        """
        result = {
            "device_id": device_id,
            "daily_soc": {},
            "avg": None,
            "min": None,
            "max": None,
            "trend": "",
            "error": ""
        }
        
        # Verifica connessione - usa collection diagnostics
        if self._collection_diags is None:
            success, msg = self.connect()
            if not success:
                result["error"] = msg
                return result
        
        try:
            now = datetime.now()
            start_date = now - timedelta(days=days)
            start_ms = int(start_date.timestamp() * 1000)
            end_ms = int(now.timestamp() * 1000)
            
            # Query per ottenere tutti i documenti nel periodo
            # Raggruppa per giorno e prendi l'ultimo valore
            pipeline = [
                {
                    "$match": {
                        "clientId": device_id,
                        "payload.metrics.TIMESTAMP.value": {
                            "$gte": start_ms,
                            "$lte": end_ms
                        },
                        "payload.metrics.EGM_OUT_SENS_23_VAR_3_value.value": {"$exists": True}
                    }
                },
                {
                    "$addFields": {
                        "timestamp_date": {
                            "$toDate": "$payload.metrics.TIMESTAMP.value"
                        },
                        "soc_value": "$payload.metrics.EGM_OUT_SENS_23_VAR_3_value.value"
                    }
                },
                {
                    "$addFields": {
                        "day_str": {
                            "$dateToString": {
                                "format": "%Y-%m-%d",
                                "date": "$timestamp_date"
                            }
                        }
                    }
                },
                {
                    "$sort": {"payload.metrics.TIMESTAMP.value": -1}
                },
                {
                    "$group": {
                        "_id": "$day_str",
                        "soc": {"$first": "$soc_value"},
                        "timestamp": {"$first": "$payload.metrics.TIMESTAMP.value"}
                    }
                },
                {
                    "$sort": {"_id": -1}  # Ordina per data decrescente
                }
            ]
            
            docs = list(self._collection_diags.aggregate(pipeline))
            
            if docs:
                # Popola daily_soc
                soc_values = []
                for doc in docs:
                    date_str = doc["_id"]
                    soc = doc["soc"]
                    
                    # Gestisci il caso in cui soc sia un dict con $numberLong
                    if isinstance(soc, dict) and "$numberLong" in soc:
                        soc = int(soc["$numberLong"])
                    elif isinstance(soc, (int, float)):
                        soc = int(soc)
                    else:
                        continue
                    
                    result["daily_soc"][date_str] = soc
                    soc_values.append(soc)
                
                if soc_values:
                    result["avg"] = round(sum(soc_values) / len(soc_values), 1)
                    result["min"] = min(soc_values)
                    result["max"] = max(soc_values)
                    
                    # Calcola trend (confronta primo e ultimo valore disponibile)
                    # soc_values[0] è il più recente, soc_values[-1] è il più vecchio
                    if len(soc_values) >= 2:
                        diff = soc_values[0] - soc_values[-1]
                        if diff > 2:
                            result["trend"] = "↑"
                        elif diff < -2:
                            result["trend"] = "↓"
                        else:
                            result["trend"] = "→"
                    else:
                        result["trend"] = "→"
            
        except Exception as e:
            result["error"] = str(e)[:150]
        
        return result
    
    def get_channel_history(self, device_id: str, hours: int = 24) -> dict:
        """
        Recupera lo storico del canale di trasmissione per un dispositivo.
        Prende un valore per ora (l'ultimo disponibile).
        
        Args:
            device_id: Il clientId del dispositivo
            hours: Numero di ore da analizzare (default 24)
            
        Returns:
            Dict con:
                - device_id: str
                - hourly_channel: dict {hour_str: channel_value} es: {"2026-01-20 14:00": "LTE", "2026-01-20 13:00": "NBIoT"}
                - channels_used: list dei canali unici utilizzati
                - lte_count: int (conteggio ore su LTE)
                - nbiot_count: int (conteggio ore su NBIoT)
                - lora_count: int (conteggio ore su LORA)
                - error: str (eventuale errore)
        """
        result = {
            "device_id": device_id,
            "hourly_channel": {},
            "channels_used": [],
            "lte_count": 0,
            "nbiot_count": 0,
            "lora_count": 0,
            "error": ""
        }
        
        # Verifica connessione - usa collection diagnostics
        if self._collection_diags is None:
            success, msg = self.connect()
            if not success:
                result["error"] = msg
                return result
        
        try:
            now = datetime.now()
            start_time = now - timedelta(hours=hours)
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(now.timestamp() * 1000)
            
            # Prima verifica: conta quanti documenti esistono per questo device nel periodo
            # senza il filtro sulla metrica canale (usa collection diagnostics)
            count_pipeline = [
                {
                    "$match": {
                        "clientId": device_id,
                        "payload.metrics.TIMESTAMP.value": {
                            "$gte": start_ms,
                            "$lte": end_ms
                        }
                    }
                },
                {"$count": "total"}
            ]
            
            count_result = list(self._collection_diags.aggregate(count_pipeline))
            total_docs = count_result[0]["total"] if count_result else 0
            
            if total_docs == 0:
                result["error"] = f"Nessun documento in diagnostics nelle ultime {hours}h"
                return result
            
            # Conta quanti documenti hanno la metrica canale
            count_channel_pipeline = [
                {
                    "$match": {
                        "clientId": device_id,
                        "payload.metrics.TIMESTAMP.value": {
                            "$gte": start_ms,
                            "$lte": end_ms
                        },
                        "payload.metrics.EGM_OUT_SENS_23_VAR_7_value.value": {"$exists": True}
                    }
                },
                {"$count": "total"}
            ]
            
            count_channel_result = list(self._collection_diags.aggregate(count_channel_pipeline))
            docs_with_channel = count_channel_result[0]["total"] if count_channel_result else 0
            
            # Query per ottenere tutti i documenti nel periodo
            # Raggruppa per ora e prendi l'ultimo valore
            pipeline = [
                {
                    "$match": {
                        "clientId": device_id,
                        "payload.metrics.TIMESTAMP.value": {
                            "$gte": start_ms,
                            "$lte": end_ms
                        },
                        "payload.metrics.EGM_OUT_SENS_23_VAR_7_value.value": {"$exists": True}
                    }
                },
                {
                    "$addFields": {
                        "timestamp_date": {
                            "$toDate": "$payload.metrics.TIMESTAMP.value"
                        },
                        "channel_value": "$payload.metrics.EGM_OUT_SENS_23_VAR_7_value.value"
                    }
                },
                {
                    "$addFields": {
                        "hour_str": {
                            "$dateToString": {
                                "format": "%Y-%m-%d %H:00",
                                "date": "$timestamp_date"
                            }
                        }
                    }
                },
                {
                    "$sort": {"payload.metrics.TIMESTAMP.value": -1}
                },
                {
                    "$group": {
                        "_id": "$hour_str",
                        "channel": {"$first": "$channel_value"},
                        "timestamp": {"$first": "$payload.metrics.TIMESTAMP.value"}
                    }
                },
                {
                    "$sort": {"_id": -1}  # Ordina per ora decrescente
                }
            ]
            
            docs = list(self._collection_diags.aggregate(pipeline))
            
            if docs:
                channels_set = set()
                lte_count = 0
                nbiot_count = 0
                lora_count = 0
                
                for doc in docs:
                    hour_str = doc["_id"]
                    channel = doc["channel"]
                    
                    # Il valore dovrebbe essere una stringa
                    if isinstance(channel, str):
                        channel = channel.strip().upper()
                    else:
                        channel = str(channel).strip().upper()
                    
                    result["hourly_channel"][hour_str] = channel
                    channels_set.add(channel)
                    
                    # Conteggio per tipo
                    if "LTE" in channel:
                        lte_count += 1
                    elif "NBIOT" in channel or "NB-IOT" in channel or "NB_IOT" in channel:
                        nbiot_count += 1
                    elif "LORA" in channel:
                        lora_count += 1
                
                result["channels_used"] = sorted(list(channels_set))
                result["lte_count"] = lte_count
                result["nbiot_count"] = nbiot_count
                result["lora_count"] = lora_count
            else:
                # Documenti esistono ma la metrica canale no
                result["error"] = f"{total_docs} doc, {docs_with_channel} con canale"
            
        except Exception as e:
            result["error"] = str(e)[:150]
        
        return result
    
    def get_signal_history(self, device_id: str, hours: int = 24) -> dict:
        """
        Recupera lo storico del segnale LTE per un dispositivo.
        Prende un valore per ora (l'ultimo disponibile).
        
        Cerca in due metriche possibili:
        - payload.metrics.SENS_Digil2_LtePowerSignal.value (primaria)
        - payload.metrics.EGM_OUT_SENS_23_VAR_14_value.value (alternativa)
        
        Args:
            device_id: Il clientId del dispositivo
            hours: Numero di ore da analizzare (default 24)
            
        Returns:
            Dict con:
                - device_id: str
                - hourly_signal: dict {hour_str: signal_dbm} es: {"2026-01-20 14:00": -85, "2026-01-20 13:00": -90}
                - avg: float (media)
                - min: int (minimo - segnale peggiore)
                - max: int (massimo - segnale migliore)
                - error: str (eventuale errore)
        """
        result = {
            "device_id": device_id,
            "hourly_signal": {},
            "avg": None,
            "min": None,
            "max": None,
            "error": ""
        }
        
        # Verifica connessione - usa collection diagnostics
        if self._collection_diags is None:
            success, msg = self.connect()
            if not success:
                result["error"] = msg
                return result
        
        try:
            now = datetime.now()
            start_time = now - timedelta(hours=hours)
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(now.timestamp() * 1000)
            
            # Query che cerca in entrambe le metriche possibili
            # Usa $or per trovare documenti con una delle due metriche
            pipeline = [
                {
                    "$match": {
                        "clientId": device_id,
                        "payload.metrics.TIMESTAMP.value": {
                            "$gte": start_ms,
                            "$lte": end_ms
                        },
                        "$or": [
                            {"payload.metrics.SENS_Digil2_LtePowerSignal.value": {"$exists": True}},
                            {"payload.metrics.EGM_OUT_SENS_23_VAR_14_value.value": {"$exists": True}}
                        ]
                    }
                },
                {
                    "$addFields": {
                        "timestamp_date": {
                            "$toDate": "$payload.metrics.TIMESTAMP.value"
                        },
                        # Prende il valore dalla prima metrica se esiste, altrimenti dalla seconda
                        "signal_value": {
                            "$ifNull": [
                                "$payload.metrics.SENS_Digil2_LtePowerSignal.value",
                                "$payload.metrics.EGM_OUT_SENS_23_VAR_14_value.value"
                            ]
                        }
                    }
                },
                {
                    "$addFields": {
                        "hour_str": {
                            "$dateToString": {
                                "format": "%Y-%m-%d %H:00",
                                "date": "$timestamp_date"
                            }
                        }
                    }
                },
                {
                    "$sort": {"payload.metrics.TIMESTAMP.value": -1}
                },
                {
                    "$group": {
                        "_id": "$hour_str",
                        "signal": {"$first": "$signal_value"},
                        "timestamp": {"$first": "$payload.metrics.TIMESTAMP.value"}
                    }
                },
                {
                    "$sort": {"_id": -1}  # Ordina per ora decrescente
                }
            ]
            
            docs = list(self._collection_diags.aggregate(pipeline))
            
            if docs:
                signal_values = []
                
                for doc in docs:
                    hour_str = doc["_id"]
                    signal = doc["signal"]
                    
                    # Gestisci il caso in cui signal sia un dict con $numberLong o $numberDouble
                    if isinstance(signal, dict):
                        if "$numberLong" in signal:
                            signal = int(signal["$numberLong"])
                        elif "$numberDouble" in signal:
                            signal = float(signal["$numberDouble"])
                        elif "$numberInt" in signal:
                            signal = int(signal["$numberInt"])
                    elif isinstance(signal, (int, float)):
                        signal = int(signal)
                    else:
                        try:
                            signal = int(float(str(signal)))
                        except:
                            continue
                    
                    result["hourly_signal"][hour_str] = signal
                    signal_values.append(signal)
                
                if signal_values:
                    result["avg"] = round(sum(signal_values) / len(signal_values), 1)
                    result["min"] = min(signal_values)  # Più negativo = peggiore
                    result["max"] = max(signal_values)  # Meno negativo = migliore
            else:
                result["error"] = f"Nessun dato segnale nelle ultime {hours}h"
            
        except Exception as e:
            result["error"] = str(e)[:150]
        
        return result
    
    def check_devices_batch(self, device_ids: list, 
                            progress_callback=None) -> list[MongoCheckResult]:
        """
        Verifica più dispositivi in batch.
        
        Args:
            device_ids: Lista di device_id da verificare
            progress_callback: Callback opzionale (current, total, device_id)
            
        Returns:
            Lista di MongoCheckResult
        """
        results = []
        total = len(device_ids)
        
        for i, device_id in enumerate(device_ids):
            if progress_callback:
                progress_callback(i, total, device_id)
            
            result = self.check_device(device_id)
            results.append(result)
        
        return results


# Singleton per il tunnel manager (evita di creare multipli tunnel)
_tunnel_manager_instance = None

def get_tunnel_manager() -> SSHTunnelManager:
    """Restituisce l'istanza singleton del tunnel manager."""
    global _tunnel_manager_instance
    if _tunnel_manager_instance is None:
        _tunnel_manager_instance = SSHTunnelManager()
    return _tunnel_manager_instance


def cleanup_tunnel():
    """Chiude il tunnel SSH globale."""
    global _tunnel_manager_instance
    if _tunnel_manager_instance:
        _tunnel_manager_instance.stop_tunnel()
        _tunnel_manager_instance = None


if __name__ == "__main__":
    print("Test MongoDB Checker con SSH Tunnel")
    print("=" * 50)
    
    # Test tunnel
    tunnel = SSHTunnelManager()
    print(f"MongoDB hosts configurati: {tunnel.mongo_hosts}")
    
    success, msg, port = tunnel.start_tunnel()
    print(f"Tunnel: {msg}")
    
    if success:
        # Test query
        checker = MongoDBChecker(tunnel)
        success, msg = checker.connect()
        print(f"Connessione: {msg}")
        
        if success:
            test_device = "1:1:2:15:22:DIGIL_MRN_0051"
            result = checker.check_device(test_device)
            print(f"\nDevice: {result.device_id}")
            print(f"Has data 24h: {result.has_data_24h}")
            print(f"Last timestamp: {result.last_timestamp}")
            print(f"Error: {result.error}")
            
            # Test SOC history
            print(f"\n--- Test SOC History ---")
            soc_history = checker.get_soc_history(test_device, days=15)
            print(f"Daily SOC: {soc_history['daily_soc']}")
            print(f"Avg: {soc_history['avg']}, Min: {soc_history['min']}, Max: {soc_history['max']}")
            print(f"Trend: {soc_history['trend']}")
            print(f"Error: {soc_history['error']}")
            
            checker.disconnect()
        
        tunnel.stop_tunnel()