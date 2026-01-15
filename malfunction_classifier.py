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
    - Disconnesso = SSH KO o LTE KO o non raggiungibile
    - Metriche assenti = Connesso ma MongoDB KO (non invia dati)
    - OK = Tutto funziona
    """
    
    def classify(self, device) -> str:
        """
        Classifica il tipo di malfunzionamento per un dispositivo.
        
        Args:
            device: DeviceInfo con tutti i risultati dei check
            
        Returns:
            Stringa con il tipo di malfunzionamento
        """
        # Estrai tutti gli stati
        ssh_ok = self._check_ssh(device)
        ping_ok = self._check_ping(device)
        mongodb_ok = getattr(device, 'mongodb_has_data', None)
        lte_ok = getattr(device, 'lte_ok', None)
        battery_ok = getattr(device, 'battery_ok', None)
        door_open = getattr(device, 'door_open', None)
        
        # === REGOLE DI CLASSIFICAZIONE ===
        
        # 1. Porta aperta (priorità alta - problema fisico)
        if door_open is True:
            return "Porta aperta"
        
        # 2. Allarme batteria (priorità alta - rischio perdita device)
        if battery_ok is False:
            return "Allarme batteria"
        
        # 3. Disconnesso - device non raggiungibile
        # Se ping/SSH falliti e non è un problema specifico già classificato
        if not ping_ok and not ssh_ok:
            return "Disconnesso"
        
        # 4. Disconnesso - LTE KO (anche se SSH OK potrebbe essere solo temporaneo)
        if lte_ok is False and not mongodb_ok:
            return "Disconnesso"
        
        # 5. Metriche assenti - Device connesso ma non invia dati
        # SSH/LTE OK ma MongoDB KO
        if mongodb_ok is False:
            if ssh_ok or lte_ok:
                return "Metriche assenti"
            else:
                return "Disconnesso"
        
        # 6. Tutto OK
        if ssh_ok and (mongodb_ok is True or mongodb_ok is None):
            if lte_ok is True or lte_ok is None:
                if battery_ok is True or battery_ok is None:
                    return "OK"
        
        # 7. Casi particolari / non classificabili
        # SSH OK ma altri check mancanti o inconclusivi
        if ssh_ok:
            if mongodb_ok is None and lte_ok is None:
                # Solo SSH fatto, consideriamo OK parziale
                return "OK"
            elif mongodb_ok is True:
                return "OK"
        
        # 8. Default per casi non coperti
        return "Non classificato"
    
    def _check_ssh(self, device) -> bool:
        """Verifica se SSH è OK."""
        if hasattr(device, 'ssh_status'):
            return device.ssh_status == ConnectionStatus.SSH_PORT_OPEN
        return False
    
    def _check_ping(self, device) -> bool:
        """Verifica se Ping è OK."""
        if hasattr(device, 'ping_status'):
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

3. DISCONNESSO
   - Condizione: SSH KO + Ping KO (device non raggiungibile)
   - Condizione: LTE KO + MongoDB KO (problemi connettività)
   - Azione: Verificare connettività di rete, SIM, antenna

4. METRICHE ASSENTI
   - Condizione: SSH/LTE OK ma MongoDB KO (non invia dati)
   - Azione: Verificare configurazione invio dati, routing

5. OK
   - Condizione: Tutti i check passati (SSH, LTE, MongoDB, Batteria)
   - Azione: Nessuna

6. NON CLASSIFICATO
   - Condizione: Combinazione di stati non coperta dalle regole
   - Azione: Analisi manuale richiesta
"""


if __name__ == "__main__":
    print("Test Malfunction Classifier")
    print(MalfunctionClassifier().get_classification_rules())
