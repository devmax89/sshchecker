"""
DIGIL Diagnostic Checker - API Client Module
=============================================
Client per le API REST di diagnostica DIGIL con OAuth2.
"""

import os
import re
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()


class DigilAPIClient:
    """Client per le API REST di diagnostica DIGIL"""
    
    # Endpoint OAuth2
    TOKEN_URL = "https://rh-sso.apps.clusterzac.opencs.servizi.prv/auth/realms/DigilV2/protocol/openid-connect/token"
    
    # Endpoint API
    API_BASE_URL = "https://digil-back-end-onesait.servizi.prv/api/v1"
    
    # Credenziali OAuth2 (client credentials flow)
    CLIENT_ID = "application"
    CLIENT_SECRET = "q3pH03oAvt9io1K1rJ9GHVVRcmAEf55x"
    
    # Metriche da estrarre
    METRICS_MAP = {
        "ALG_Digil2_Alm_Low_Batt": "battery_alarm",
        "SENS_Digil2_BatteryLevel_Percent": "soc_percent",
        "SENS_Digil2_BatteryState_Percent": "soh_percent",
        "SENS_Digil2_Channel": "channel",
        "SENS_Digil2_LtePowerSignal": "lte_signal_dbm",
        "ALG_Digil2_Alm_Open_Door": "door_alarm"
    }
    
    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        self._session = requests.Session()
        
        # Disabilita warning SSL per certificati interni
        self._session.verify = False
        requests.packages.urllib3.disable_warnings()
    
    def _get_token(self) -> Optional[str]:
        """Ottiene o rinnova il token OAuth2."""
        # Se il token è ancora valido, riusalo
        if self._access_token and self._token_expiry:
            if datetime.now() < self._token_expiry - timedelta(minutes=1):
                return self._access_token
        
        try:
            response = self._session.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.CLIENT_ID,
                    "client_secret": self.CLIENT_SECRET
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self._access_token = data.get("access_token")
                expires_in = data.get("expires_in", 300)
                self._token_expiry = datetime.now() + timedelta(seconds=expires_in)
                return self._access_token
            else:
                print(f"Errore token OAuth2: {response.status_code} - {response.text[:200]}")
                return None
                
        except Exception as e:
            print(f"Errore richiesta token: {str(e)}")
            return None
    
    def _convert_device_id(self, device_id: str) -> str:
        """
        Converte DeviceID dal formato MongoDB al formato API.
        
        Input: "1:1:2:15:22:DIGIL_MRN_0259"
        Output: "1121522_0259"
        """
        # Pattern: 1:1:2:XX:YY:DIGIL_XXX_NNNN
        match = re.match(r'^(\d+):(\d+):(\d+):(\d+):(\d+):DIGIL_\w+_(\d+)$', device_id)
        
        if match:
            # Ricostruisci come: 112XXYY_NNNN
            p1, p2, p3, p4, p5, suffix = match.groups()
            return f"{p1}{p2}{p3}{p4}{p5}_{suffix}"
        
        # Fallback: prova a estrarre comunque
        parts = device_id.split(":")
        if len(parts) >= 5:
            prefix = "".join(parts[:5])
            # Cerca il numero finale dopo DIGIL_XXX_
            num_match = re.search(r'_(\d+)$', device_id)
            if num_match:
                return f"{prefix}_{num_match.group(1)}"
        
        return device_id
    
    def get_device_diagnostics(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        Ottiene i dati diagnostici per un dispositivo.
        
        Args:
            device_id: DeviceID nel formato MongoDB (es: "1:1:2:15:22:DIGIL_MRN_0259")
            
        Returns:
            Dict con i dati diagnostici o None in caso di errore
        """
        token = self._get_token()
        if not token:
            return None
        
        # Converti device_id per l'API
        api_device_id = self._convert_device_id(device_id)
        
        url = f"{self.API_BASE_URL}/digils/{api_device_id}"
        
        try:
            response = self._session.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json"
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._parse_diagnostics(data)
            elif response.status_code == 404:
                return {"error": "Device non trovato"}
            else:
                return {"error": f"HTTP {response.status_code}"}
                
        except Exception as e:
            return {"error": str(e)[:100]}
    
    def _parse_diagnostics(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Estrae le metriche rilevanti dalla risposta API."""
        result = {
            "battery_ok": None,
            "door_open": None,
            "lte_ok": None,
            "soc_percent": None,
            "soh_percent": None,
            "lte_signal_dbm": None,
            "channel": None,
            "status": data.get("status"),
            "vendor": data.get("vendor"),
            "typology": data.get("typology"),
            "api_timestamp": None  # Timestamp decodificato dalla risposta API
        }
        
        # Status connessione
        status = data.get("status", "").upper()
        result["lte_ok"] = status == "CONNECTED"
        
        # I dati sono in "diags" (allarmi) e "measures" (misure)
        diags = data.get("diags", {})
        measures = data.get("measures", {})
        
        # === ESTRAI TIMESTAMP PIÙ RECENTE ===
        # Cerca il timestamp più recente tra tutte le metriche
        latest_timestamp = None
        
        # Controlla timestamp nelle measures
        for metric_name, metric_data in measures.items():
            if isinstance(metric_data, dict):
                ts = metric_data.get("timestamp") or metric_data.get("receivedOn")
                if ts and (latest_timestamp is None or ts > latest_timestamp):
                    latest_timestamp = ts
        
        # Controlla timestamp nei diags
        for diag_name, diag_data in diags.items():
            if isinstance(diag_data, dict):
                ts = diag_data.get("timestamp") or diag_data.get("receivedOn")
                if ts and (latest_timestamp is None or ts > latest_timestamp):
                    latest_timestamp = ts
        
        # Se non trovato nelle metriche, prova il campo principale
        if latest_timestamp is None:
            latest_timestamp = data.get("lastUpdate") or data.get("receivedOn") or data.get("timestamp")
        
        # Decodifica il timestamp
        if latest_timestamp:
            result["api_timestamp"] = self._decode_timestamp(latest_timestamp)
        
        # === DIAGS (Allarmi) ===
        
        # Allarme batteria bassa
        battery_alarm = diags.get("ALG_Digil2_Alm_Low_Batt", {}).get("value")
        if battery_alarm is not None:
            result["battery_ok"] = not battery_alarm
        
        # Warning batteria bassa (se non c'è l'allarme, controlla il warning)
        if result["battery_ok"] is None:
            battery_warn = diags.get("ALG_Digil2_Warn_Low_Batt", {}).get("value")
            if battery_warn is not None:
                result["battery_ok"] = not battery_warn
        
        # Porta aperta - NOTA: questo campo potrebbe non esistere in tutti i device
        door_alarm = diags.get("ALG_Digil2_Alm_Open_Door", {}).get("value")
        if door_alarm is not None:
            result["door_open"] = door_alarm
        
        # === MEASURES (Misure) ===
        
        # SOC (State of Charge) - Livello batteria %
        soc_data = measures.get("SENS_Digil2_BatteryLevel_Percent", {})
        soc = soc_data.get("value")
        if soc is not None:
            result["soc_percent"] = float(soc)
        
        # SOH (State of Health) - Stato salute batteria %
        soh_data = measures.get("SENS_Digil2_BatteryState_Percent", {})
        soh = soh_data.get("value")
        if soh is not None:
            result["soh_percent"] = float(soh)
        
        # Segnale LTE (dBm)
        signal_data = measures.get("SENS_Digil2_LtePowerSignal", {})
        signal = signal_data.get("value")
        if signal is not None:
            result["lte_signal_dbm"] = float(signal)
        
        # Canale (LTE/NBIoT)
        channel_data = measures.get("SENS_Digil2_Channel", {})
        channel = channel_data.get("value")
        if channel is not None:
            result["channel"] = str(channel)
        
        # Se non c'è il segnale LTE, prova NBIoT
        if result["lte_signal_dbm"] is None:
            nbiot_signal = measures.get("SENS_Digil2_NBIoTPowerSignal", {}).get("value")
            if nbiot_signal is not None:
                result["lte_signal_dbm"] = float(nbiot_signal)
        
        return result
    
    def _decode_timestamp(self, timestamp) -> Optional[str]:
        """
        Decodifica un timestamp in formato leggibile.
        
        Supporta:
        - Millisecondi Unix (es: 1737297942000)
        - Secondi Unix (es: 1737297942)
        - Stringa ISO già formattata
        
        Returns:
            Stringa nel formato "YYYY-MM-DD HH:MM:SS" o None
        """
        if timestamp is None:
            return None
        
        try:
            # Se è già una stringa formattata, prova a parsarla
            if isinstance(timestamp, str):
                # Prova formato ISO
                if 'T' in timestamp or '-' in timestamp:
                    # Rimuovi timezone se presente
                    ts_clean = timestamp.split('+')[0].split('Z')[0]
                    dt = datetime.fromisoformat(ts_clean)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                # Prova a convertirlo in numero
                timestamp = int(timestamp)
            
            # Se è un numero (int o float)
            if isinstance(timestamp, (int, float)):
                # Se il timestamp è in millisecondi (> anno 2100 in secondi)
                if timestamp > 4102444800:  # 2100-01-01 in secondi
                    timestamp = timestamp / 1000
                
                dt = datetime.fromtimestamp(timestamp)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            
        except Exception as e:
            print(f"Errore decodifica timestamp {timestamp}: {e}")
        
        return None


if __name__ == "__main__":
    print("Test API Client")
    
    client = DigilAPIClient()
    
    # Test token
    token = client._get_token()
    print(f"Token ottenuto: {'Sì' if token else 'No'}")
    
    # Test conversione device_id
    test_ids = [
        "1:1:2:15:22:DIGIL_MRN_0259",
        "1:1:2:16:21:DIGIL_SR2_0103"
    ]
    
    for did in test_ids:
        converted = client._convert_device_id(did)
        print(f"{did} -> {converted}")
    
    # Test decodifica timestamp
    test_timestamps = [
        1737297942000,  # millisecondi
        1737297942,     # secondi
        "2025-01-19T15:25:42.000Z",  # ISO
        "2025-01-19T15:25:42+01:00"  # ISO con timezone
    ]
    
    print("\nTest decodifica timestamp:")
    for ts in test_timestamps:
        decoded = client._decode_timestamp(ts)
        print(f"  {ts} -> {decoded}")