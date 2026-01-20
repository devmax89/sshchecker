"""
DIGIL Diagnostic Checker - Malfunction Classifier Module
=========================================================
Classifica i malfunzionamenti in base ai risultati dei check.
"""

from typing import Optional
from connectivity_checker import ConnectionStatus


class MalfunctionClassifier:
    """
    Classifica i malfunzionamenti dei dispositivi DIGIL.
    
    Logica basata sui pattern:
    - Porta aperta = door_open == True
    - Allarme batteria = battery_ok == False
    - Disconnesso = SSH KO E MongoDB KO (device veramente offline)
    - Metriche assenti = Connesso ma MongoDB KO (non invia dati)
    - OK = Tutto funziona OPPURE MongoDB OK (anche se SSH KO - device attivo)
    
    NOTA: Se OK e "Tipo Installazione AM" == "Inst. Completa" 
          -> nelle Note viene scritto "Verificare Tiro" (gestito in data_handler.py)
    
    NOTA: Se MongoDB OK ma SSH/Ping KO
          -> classificato come OK con nota "Dispositivo non raggiungibile"
    """
    
    def classify(self, device) -> tuple[str, str]:
        """
        Classifica il tipo di malfunzionamento per un dispositivo.
        
        Args:
            device: DeviceInfo con tutti i risultati dei check
            
        Returns:
            Tuple (malfunction_type, connectivity_note)
            - malfunction_type: Stringa con il tipo di malfunzionamento
            - connectivity_note: Nota sulla raggiungibilità (es: "Ping KO, SSH KO")
        """
        # Estrai tutti gli stati
        ssh_ok = self._check_ssh(device)
        ping_ok = self._check_ping(device)
        mongodb_ok = getattr(device, 'mongodb_has_data', None)
        lte_ok = getattr(device, 'lte_ok', None)
        battery_ok = getattr(device, 'battery_ok', None)
        door_open = getattr(device, 'door_open', None)
        
        # Costruisci nota di connettività
        connectivity_note = self._build_connectivity_note(ping_ok, ssh_ok)
        
        # === REGOLE DI CLASSIFICAZIONE ===
        
        # 1. Porta aperta (priorità alta - problema fisico)
        if door_open is True:
            return "Porta aperta", connectivity_note
        
        # 2. Allarme batteria (priorità alta - rischio perdita device)
        if battery_ok is False:
            return "Allarme batteria", connectivity_note
        
        # 3. NUOVA LOGICA: Se MongoDB OK, il device è ATTIVO anche se non raggiungibile
        # Non può essere "Disconnesso" se sta mandando dati!
        if mongodb_ok is True:
            # Device attivo, sta comunicando con la piattaforma
            if not ping_ok or not ssh_ok:
                # Non raggiungibile ma attivo -> OK con nota
                return "OK", f"Non raggiungibile ({connectivity_note})" if connectivity_note else ""
            else:
                # Tutto OK
                return "OK", ""
        
        # 4. Disconnesso - device non raggiungibile E non manda dati
        if not ping_ok and not ssh_ok:
            if mongodb_ok is False:
                return "Disconnesso", connectivity_note
            elif mongodb_ok is None:
                # MongoDB non verificato, ma SSH/Ping KO
                return "Disconnesso", connectivity_note
        
        # 5. Disconnesso - LTE KO e MongoDB KO
        if lte_ok is False and mongodb_ok is False:
            return "Disconnesso", connectivity_note
        
        # 6. Metriche assenti - Device raggiungibile ma non invia dati
        if mongodb_ok is False:
            if ssh_ok or ping_ok or lte_ok:
                return "Metriche assenti", connectivity_note
            else:
                return "Disconnesso", connectivity_note
        
        # 7. Tutto OK (SSH OK, MongoDB non verificato o OK)
        if ssh_ok:
            return "OK", ""
        
        # 8. LTE OK ma MongoDB non verificato
        if lte_ok is True:
            return "OK", connectivity_note if (not ping_ok or not ssh_ok) else ""
        
        # 9. Default per casi non coperti
        return "Non classificato", connectivity_note
    
    def _build_connectivity_note(self, ping_ok: bool, ssh_ok: bool) -> str:
        """Costruisce la nota sulla connettività."""
        issues = []
        if not ping_ok:
            issues.append("Ping KO")
        if not ssh_ok:
            issues.append("SSH KO")
        return ", ".join(issues)
    
    def _check_ssh(self, device) -> bool:
        """Verifica se SSH è OK."""
        if hasattr(device, 'ssh_status'):
            from connectivity_checker import ConnectionStatus
            return device.ssh_status == ConnectionStatus.SSH_PORT_OPEN
        return False
    
    def _check_ping(self, device) -> bool:
        """Verifica se Ping è OK."""
        if hasattr(device, 'ping_status'):
            from connectivity_checker import ConnectionStatus
            return device.ping_status == ConnectionStatus.PING_OK
        return False
    
    def get_classification_rules(self) -> str:
        """Restituisce una descrizione delle regole di classificazione."""
        return """
REGOLE DI CLASSIFICAZIONE MALFUNZIONAMENTI:

1. PORTA APERTA
   - Condizione: door_open = True (ALG_Digil2_Alm_Open_Door)
   - Azione: Verificare fisicamente il dispositivo

2. ALLARME BATTERIA
   - Condizione: battery_ok = False (ALG_Digil2_Alm_Low_Batt)
   - Azione: Programmare sostituzione batteria

3. OK (con nota "Non raggiungibile")
   - Condizione: MongoDB OK ma SSH/Ping KO
   - Significato: Device attivo, comunica con piattaforma, ma non raggiungibile via rete
   - Azione: Verificare routing, firewall, configurazione rete
   - NOTA: Se "Tipo Installazione AM" = "Inst. Completa" -> Note: "Verificare Tiro"

4. DISCONNESSO
   - Condizione: SSH/Ping KO E MongoDB KO (device veramente offline)
   - Condizione: LTE KO + MongoDB KO (problemi connettività totale)
   - Azione: Verificare connettività di rete, SIM, antenna, alimentazione

5. METRICHE ASSENTI
   - Condizione: SSH/Ping OK oppure LTE OK, ma MongoDB KO (non invia dati)
   - Azione: Verificare configurazione invio dati, routing applicativo

6. OK
   - Condizione: Tutti i check passati (SSH, LTE, MongoDB, Batteria)
   - Azione: Nessuna

7. NON CLASSIFICATO
   - Condizione: Combinazione di stati non coperta dalle regole
   - Azione: Analisi manuale richiesta
"""


if __name__ == "__main__":
    print("Test Malfunction Classifier")
    print(MalfunctionClassifier().get_classification_rules())