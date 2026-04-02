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
    
    NUOVA LOGICA v2.1 - SSH/Ping non è più il check primario:
    
    1. MongoDB OK → TUTTO OK (SSH/Ping matematicamente OK, fine)
    2. MongoDB KO + Onesait OK → SSH/Ping OK, problema di inoltro dati → Metriche assenti
    3. MongoDB KO + Onesait KO → SSH/Ping KO → Disconnesso
    
    SSH/Ping viene eseguito direttamente solo se la checkbox è selezionata.
    In quel caso i valori reali sovrascrivono quelli derivati.
    
    NOTA: Se OK e "Tipo Installazione AM" == "Inst. Completa" 
          -> nelle Note viene scritto "Verificare Tiro" (gestito in data_handler.py)
    
    NOTA: Allarme porta aperta viene validato confrontando il timestamp dell'allarme
          con la data di installazione del dispositivo. Se l'allarme è precedente
          all'installazione, viene ignorato (falso positivo pre-installazione).
    """
    
    def classify(self, device) -> tuple[str, str]:
        """
        Classifica il tipo di malfunzionamento per un dispositivo.
        
        LOGICA:
        - MongoDB OK → SSH/Ping matematicamente OK → TUTTO OK
        - MongoDB KO + Onesait OK → SSH/Ping OK, dato bloccato → Metriche assenti
        - MongoDB KO + Onesait KO → SSH/Ping KO → Disconnesso
        - Se ssh_directly_checked=True, usa i valori reali SSH/Ping
        
        Args:
            device: DeviceInfo con tutti i risultati dei check
            
        Returns:
            Tuple (malfunction_type, connectivity_note)
        """
        mongodb_ok = getattr(device, 'mongodb_has_data', None)
        lte_ok = getattr(device, 'lte_ok', None)
        battery_ok = getattr(device, 'battery_ok', None)
        door_open_valid = getattr(device, 'door_open_valid', None)
        api_timestamp = getattr(device, 'api_timestamp', None)
        onesait_ok = bool(api_timestamp)
        
        # Determina SSH/Ping: reale (check diretto) o derivato
        ssh_directly_checked = getattr(device, 'ssh_directly_checked', False)
        
        if ssh_directly_checked:
            ssh_ok = self._check_ssh(device)
            ping_ok = self._check_ping(device)
            connectivity_note = self._build_connectivity_note(ping_ok, ssh_ok)
        else:
            # Deriva SSH/Ping dalla logica MongoDB + Onesait
            if mongodb_ok is True:
                ssh_ok = True
                ping_ok = True
                connectivity_note = ""
            elif onesait_ok:
                ssh_ok = True
                ping_ok = True
                connectivity_note = ""
            elif mongodb_ok is False:
                ssh_ok = False
                ping_ok = False
                connectivity_note = "SSH/Ping KO (derivato)"
            else:
                ssh_ok = None
                ping_ok = None
                connectivity_note = ""
        
        # === REGOLE DI CLASSIFICAZIONE ===
        
        # 1. Porta aperta (priorità alta - problema fisico)
        if door_open_valid is True:
            return "Porta aperta", connectivity_note
        
        # 2. Allarme batteria (priorità alta - rischio perdita device)
        if battery_ok is False:
            return "Allarme batteria", connectivity_note
        
        # 3. MongoDB OK → device attivo e sano
        if mongodb_ok is True:
            if ssh_directly_checked and (not ping_ok or not ssh_ok):
                # Check diretto fallisce ma MongoDB OK: attivo ma non raggiungibile via rete
                return "OK", f"Non raggiungibile ({connectivity_note})" if connectivity_note else "Non raggiungibile"
            return "OK", ""
        
        # 4. MongoDB KO ma Onesait OK → dato presente su piattaforma ma non su MongoDB
        if mongodb_ok is False and onesait_ok:
            return "Metriche assenti", "Dato presente su Onesait, assente su MongoDB"
        
        # 5. MongoDB KO + Onesait KO
        if mongodb_ok is False:
            if ssh_directly_checked and ssh_ok:
                # Check diretto SSH OK ma non invia dati
                return "Metriche assenti", connectivity_note
            # Tutto KO → Disconnesso
            return "Disconnesso", connectivity_note
        
        # 6. MongoDB non verificato - usa LTE e SSH come fallback
        if lte_ok is False:
            return "Disconnesso", connectivity_note
        
        if ssh_ok:
            return "OK", connectivity_note if connectivity_note else ""
        
        if lte_ok is True:
            return "OK", ""
        
        # Default
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
        """Verifica se SSH è OK (solo check diretto)."""
        if hasattr(device, 'ssh_status'):
            from connectivity_checker import ConnectionStatus
            return device.ssh_status == ConnectionStatus.SSH_PORT_OPEN
        return False
    
    def _check_ping(self, device) -> bool:
        """Verifica se Ping è OK (solo check diretto)."""
        if hasattr(device, 'ping_status'):
            from connectivity_checker import ConnectionStatus
            return device.ping_status == ConnectionStatus.PING_OK
        return False
    
    def _derive_ssh_ping(self, device) -> tuple:
        """
        Deriva lo stato SSH/Ping da MongoDB e Onesait quando il check diretto
        non è stato eseguito.
        
        Returns:
            Tuple (ssh_ok, ping_ok, connectivity_note)
        """
        mongodb_ok = getattr(device, 'mongodb_has_data', None)
        api_timestamp = getattr(device, 'api_timestamp', None)
        onesait_ok = bool(api_timestamp)
        
        if mongodb_ok is True:
            return True, True, ""
        elif onesait_ok:
            return True, True, ""
        elif mongodb_ok is False:
            return False, False, "SSH/Ping KO (derivato)"
        else:
            return None, None, ""
    
    def get_classification_rules(self) -> str:
        """Restituisce una descrizione delle regole di classificazione."""
        return """
REGOLE DI CLASSIFICAZIONE MALFUNZIONAMENTI (v2.1):

LOGICA PRIMARIA (MongoDB + Onesait):
  MongoDB OK                      → OK (SSH/Ping matematicamente OK)
  MongoDB KO + Onesait OK         → Metriche assenti (dato bloccato tra Onesait e MongoDB)
  MongoDB KO + Onesait KO         → Disconnesso (SSH/Ping KO derivato)

1. PORTA APERTA
   - Condizione: door_open_valid = True (da MongoDB collection unsolicited)
   - Validazione: Il timestamp dell'allarme deve essere >= data installazione dispositivo
   - Azione: Verificare fisicamente il dispositivo

2. ALLARME BATTERIA
   - Condizione: battery_ok = False (ALG_Digil2_Alm_Low_Batt)
   - Azione: Programmare sostituzione batteria

3. OK
   - Condizione: MongoDB OK
   - Se ssh_directly_checked e SSH/Ping KO: OK con nota "Non raggiungibile"
   - NOTA: Se "Tipo Installazione AM" = "Inst. Completa" -> Note: "Verificare Tiro"

4. METRICHE ASSENTI
   - Condizione: MongoDB KO + Onesait OK (dato su piattaforma ma non su MongoDB)
   - Condizione: MongoDB KO + SSH/Ping OK (check diretto)
   - Azione: Verificare configurazione invio dati, routing applicativo

5. DISCONNESSO
   - Condizione: MongoDB KO + Onesait KO
   - Azione: Verificare connettività di rete, SIM, antenna, alimentazione

6. NON CLASSIFICATO
   - Condizione: Combinazione di stati non coperta dalle regole
   - Azione: Analisi manuale richiesta

NOTA: Il check SSH/Ping diretto è opzionale. Se selezionato, i valori reali
      sovrascrivono quelli derivati. La colonna SSH nell'export mostra OK*/KO*
      quando il valore è derivato (asterisco = dedotto dalla logica).
"""


if __name__ == "__main__":
    print("Test Malfunction Classifier")
    print(MalfunctionClassifier().get_classification_rules())