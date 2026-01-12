"""
DIGIL SSH Checker - Data Handler Module
=======================================
Gestisce il caricamento dei dati da Excel e l'esportazione dei risultati.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional
import os
import shutil

from connectivity_checker import (
    DeviceInfo, DeviceType, Vendor, ConnectionStatus,
    detect_device_type, detect_vendor, normalize_ip
)


class DataLoader:
    """Carica i dati dei dispositivi dal file Excel di monitoraggio e dalla lista test"""
    
    # Percorso di default per il file di monitoraggio (anagrafica)
    DEFAULT_FILE_NAME = "Monitoraggio_APPARATI_DIGIL_INSTALLATI.xlsx"
    
    def __init__(self, data_dir: Optional[str] = None):
        """
        Args:
            data_dir: Directory contenente il file di monitoraggio.
                     Se None, usa la directory corrente.
        """
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            # Cerca prima nella directory dell'app, poi in quella corrente
            self.data_dir = Path(__file__).parent / "data"
            if not self.data_dir.exists():
                self.data_dir = Path.cwd()
        
        self.monitoring_file: Optional[Path] = None  # Anagrafica completa
        self.test_list_file: Optional[Path] = None   # Lista DeviceID da testare
        self._df: Optional[pd.DataFrame] = None       # DataFrame anagrafica
        self._test_list_df: Optional[pd.DataFrame] = None  # DataFrame lista test
        self._test_device_ids: list[str] = []         # Lista DeviceID da testare
        
    def find_monitoring_file(self) -> Optional[Path]:
        """Cerca il file di monitoraggio nella directory dati"""
        # Cerca il file con il nome esatto
        exact_path = self.data_dir / self.DEFAULT_FILE_NAME
        if exact_path.exists():
            self.monitoring_file = exact_path
            return exact_path
        
        # Cerca file simili
        for f in self.data_dir.glob("*DIGIL*.xlsx"):
            if "monitoraggio" in f.name.lower() or "apparati" in f.name.lower():
                self.monitoring_file = f
                return f
        
        return None
    
    def load_file(self, file_path: Optional[str] = None) -> tuple[bool, str, int]:
        """
        Carica il file Excel di monitoraggio.
        
        Args:
            file_path: Percorso del file. Se None, usa il file di default.
            
        Returns:
            (success, message, device_count)
        """
        if file_path:
            path = Path(file_path)
        else:
            path = self.find_monitoring_file()
            if not path:
                return False, f"File di monitoraggio non trovato in {self.data_dir}", 0
        
        if not path.exists():
            return False, f"File non trovato: {path}", 0
        
        try:
            # Carica lo sheet "Stato" saltando la prima riga (header reale è riga 2)
            self._df = pd.read_excel(
                path, 
                sheet_name="Stato",
                header=1,  # La riga 1 (0-indexed) contiene gli header
                engine='openpyxl'
            )
            
            # Verifica che le colonne necessarie esistano
            required_cols = ['DeviceID', 'IP address SIM', 'Linea', 'ST Sostegno']
            missing = [c for c in required_cols if c not in self._df.columns]
            
            if missing:
                return False, f"Colonne mancanti nel file: {missing}", 0
            
            # Filtra righe con dati validi
            self._df = self._df.dropna(subset=['DeviceID', 'IP address SIM'])
            
            self.monitoring_file = path
            return True, f"Anagrafica caricata: {len(self._df)} dispositivi", len(self._df)
            
        except Exception as e:
            return False, f"Errore caricamento file: {str(e)}", 0
    
    def load_test_list(self, file_path: str, 
                       device_id_column: Optional[str] = None,
                       sheet_name: Optional[str] = None,
                       has_header: bool = True) -> tuple[bool, str, int]:
        """
        Carica la lista dei DeviceID da testare da un file Excel.
        
        Args:
            file_path: Percorso del file Excel con la lista
            device_id_column: Nome/indice della colonna contenente i DeviceID.
                            Se None, usa la prima colonna.
            sheet_name: Nome dello sheet da leggere. Se None, usa il primo.
            has_header: Se True, la prima riga è l'intestazione. Se False, i dati partono dalla riga 1.
            
        Returns:
            (success, message, device_count)
        """
        path = Path(file_path)
        
        if not path.exists():
            return False, f"File non trovato: {path}", 0
        
        try:
            # Carica il file - se non ha header, header=None
            read_params = {
                'engine': 'openpyxl',
                'header': 0 if has_header else None  # None = no header row
            }
            if sheet_name:
                read_params['sheet_name'] = sheet_name
                
            self._test_list_df = pd.read_excel(path, **read_params)
            
            # Se non ha header, le colonne saranno 0, 1, 2, ...
            # Determina quale colonna usare
            if has_header:
                # Con header: cerca per nome
                if device_id_column and device_id_column in self._test_list_df.columns:
                    id_col = device_id_column
                else:
                    # Cerca automaticamente colonne con nomi comuni
                    possible_names = ['DeviceID', 'deviceid', 'DEVICEID', 'Device_ID', 
                                     'device_id', 'ID', 'id', 'DeviceId']
                    id_col = None
                    for name in possible_names:
                        if name in self._test_list_df.columns:
                            id_col = name
                            break
                    
                    # Se non trova, prova la prima colonna
                    if id_col is None:
                        id_col = self._test_list_df.columns[0]
            else:
                # Senza header: usa indice colonna (default: prima colonna = 0)
                if device_id_column is not None:
                    # Se è un numero, usalo come indice
                    try:
                        id_col = int(device_id_column)
                    except (ValueError, TypeError):
                        id_col = 0
                else:
                    id_col = 0
            
            # Estrai i DeviceID
            self._test_device_ids = self._test_list_df[id_col].dropna().astype(str).tolist()
            
            # Pulisci valori vuoti o invalidi
            self._test_device_ids = [did.strip() for did in self._test_device_ids 
                                     if did.strip() and did.strip().lower() != 'nan']
            
            self.test_list_file = path
            col_name = f"colonna {id_col}" if not has_header else f"colonna '{id_col}'"
            return True, f"Lista test caricata: {len(self._test_device_ids)} dispositivi ({col_name})", len(self._test_device_ids)
            
        except Exception as e:
            return False, f"Errore caricamento lista test: {str(e)}", 0
    
    def clear_test_list(self):
        """Rimuove la lista test caricata (torna a testare tutti i dispositivi)"""
        self._test_list_df = None
        self._test_device_ids = []
        self.test_list_file = None
    
    def get_test_list_columns(self, file_path: str) -> tuple[bool, list[str], str]:
        """
        Legge le colonne disponibili in un file Excel per permettere la selezione.
        
        Returns:
            (success, columns_list, error_message)
        """
        try:
            df = pd.read_excel(file_path, nrows=0, engine='openpyxl')
            return True, list(df.columns), ""
        except Exception as e:
            return False, [], str(e)
    
    def get_devices(self, filter_vendor: Optional[str] = None,
                   filter_type: Optional[str] = None,
                   use_test_list: bool = True) -> list[DeviceInfo]:
        """
        Restituisce la lista dei dispositivi come oggetti DeviceInfo.
        
        Args:
            filter_vendor: Filtra per vendor (INDRA, SIRTI, MII)
            filter_type: Filtra per tipo (master, slave)
            use_test_list: Se True e c'è una lista test caricata, filtra solo quei DeviceID
        """
        if self._df is None:
            return []
        
        devices = []
        
        # Se c'è una lista test, crea un set per lookup veloce
        test_ids_set = set(self._test_device_ids) if (use_test_list and self._test_device_ids) else None
        
        for _, row in self._df.iterrows():
            device_id = str(row.get('DeviceID', ''))
            ip_raw = row.get('IP address SIM', '')
            
            # Salta righe senza dati essenziali
            if not device_id or device_id == 'nan' or pd.isna(ip_raw):
                continue
            
            # Se c'è una lista test, filtra solo i DeviceID presenti
            if test_ids_set is not None:
                if device_id not in test_ids_set:
                    continue
            
            # Normalizza IP
            ip = normalize_ip(ip_raw)
            
            # Determina tipo e vendor
            device_type = detect_device_type(device_id)
            fornitore = str(row.get('Fornitore', ''))
            vendor = detect_vendor(device_id, fornitore)
            
            # Applica filtri
            if filter_vendor:
                if vendor.value.upper() != filter_vendor.upper():
                    continue
            
            if filter_type:
                if device_type.value.lower() != filter_type.lower():
                    continue
            
            device = DeviceInfo(
                device_id=device_id,
                ip_address=ip,
                linea=str(row.get('Linea', '')),
                sostegno=str(row.get('ST Sostegno', '')),
                fornitore=fornitore,
                device_type=device_type,
                vendor=vendor
            )
            
            devices.append(device)
        
        return devices
    
    def get_summary(self) -> dict:
        """Restituisce un sommario dei dati caricati"""
        if self._df is None:
            return {"loaded": False}
        
        # Dispositivi totali in anagrafica
        all_devices = self.get_devices(use_test_list=False)
        
        # Dispositivi da testare (filtrati per lista test se presente)
        test_devices = self.get_devices(use_test_list=True)
        
        vendor_counts = {}
        type_counts = {"master": 0, "slave": 0, "unknown": 0}
        
        for d in test_devices:
            v = d.vendor.value
            vendor_counts[v] = vendor_counts.get(v, 0) + 1
            type_counts[d.device_type.value] += 1
        
        # Conta DeviceID non trovati in anagrafica
        not_found = []
        if self._test_device_ids:
            anagrafica_ids = set(str(row.get('DeviceID', '')) for _, row in self._df.iterrows())
            not_found = [did for did in self._test_device_ids if did not in anagrafica_ids]
        
        return {
            "loaded": True,
            "file": str(self.monitoring_file) if self.monitoring_file else "",
            "total_in_anagrafica": len(all_devices),
            "total_devices": len(test_devices),  # Dispositivi che saranno testati
            "by_vendor": vendor_counts,
            "by_type": type_counts,
            "test_list_loaded": bool(self._test_device_ids),
            "test_list_file": str(self.test_list_file) if self.test_list_file else "",
            "test_list_count": len(self._test_device_ids),
            "not_found_in_anagrafica": not_found,
            "not_found_count": len(not_found)
        }


class ResultExporter:
    """Esporta i risultati dei test in formato Excel"""
    
    def __init__(self):
        self.output_dir = Path.home() / "Downloads"
        if not self.output_dir.exists():
            self.output_dir = Path.cwd()
    
    def export_results(self, results: list[DeviceInfo], 
                       output_path: Optional[str] = None) -> tuple[bool, str]:
        """
        Esporta i risultati in un file Excel.
        
        Args:
            results: Lista di DeviceInfo con i risultati dei test
            output_path: Percorso di output. Se None, genera automaticamente.
            
        Returns:
            (success, file_path_or_error)
        """
        if not results:
            return False, "Nessun risultato da esportare"
        
        # Genera nome file se non specificato
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"DIGIL_SSH_Check_{timestamp}.xlsx"
        
        try:
            # Prepara dati per DataFrame
            data = []
            for r in results:
                # Determina esito finale
                if r.ssh_status == ConnectionStatus.SSH_PORT_OPEN:
                    check_lte = "OK"
                elif r.ping_status == ConnectionStatus.PING_OK:
                    check_lte = "PING_OK_SSH_KO"
                elif r.ping_status == ConnectionStatus.VPN_ERROR:
                    check_lte = "VPN_ERROR"
                else:
                    check_lte = "KO"
                
                data.append({
                    "Linea": r.linea,
                    "ST Sostegno": r.sostegno,
                    "DeviceID": r.device_id,
                    "IP Address": r.ip_address,
                    "Vendor": r.vendor.value,
                    "Tipo": r.device_type.value,
                    "Fornitore": r.fornitore,
                    "Ping Status": r.ping_status.value,
                    "Ping Time (ms)": r.ping_time_ms if r.ping_time_ms else "",
                    "SSH Status": r.ssh_status.value,
                    "Check LTE": check_lte,
                    "Note": r.error_message,
                    "Timestamp Test": r.test_timestamp
                })
            
            df = pd.DataFrame(data)
            
            # Crea Excel con formattazione
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Risultati Test')
                
                workbook = writer.book
                worksheet = writer.sheets['Risultati Test']
                
                # Formati
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#0066CC',  # Blu Terna
                    'font_color': 'white',
                    'border': 1,
                    'align': 'center',
                    'valign': 'vcenter'
                })
                
                ok_format = workbook.add_format({
                    'bg_color': '#C6EFCE',
                    'font_color': '#006100',
                    'border': 1
                })
                
                ko_format = workbook.add_format({
                    'bg_color': '#FFC7CE',
                    'font_color': '#9C0006',
                    'border': 1
                })
                
                warning_format = workbook.add_format({
                    'bg_color': '#FFEB9C',
                    'font_color': '#9C5700',
                    'border': 1
                })
                
                cell_format = workbook.add_format({
                    'border': 1,
                    'align': 'left',
                    'valign': 'vcenter'
                })
                
                # Applica formato header
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                # Larghezza colonne
                column_widths = {
                    'Linea': 12,
                    'ST Sostegno': 22,
                    'DeviceID': 30,
                    'IP Address': 15,
                    'Vendor': 10,
                    'Tipo': 8,
                    'Fornitore': 20,
                    'Ping Status': 15,
                    'Ping Time (ms)': 12,
                    'SSH Status': 15,
                    'Check LTE': 15,
                    'Note': 40,
                    'Timestamp Test': 20
                }
                
                for col_num, col_name in enumerate(df.columns):
                    width = column_widths.get(col_name, 15)
                    worksheet.set_column(col_num, col_num, width)
                
                # Applica formattazione condizionale per Check LTE (colonna K, index 10)
                check_col = df.columns.get_loc('Check LTE')
                worksheet.conditional_format(1, check_col, len(df), check_col, {
                    'type': 'cell',
                    'criteria': '==',
                    'value': '"OK"',
                    'format': ok_format
                })
                worksheet.conditional_format(1, check_col, len(df), check_col, {
                    'type': 'cell',
                    'criteria': '==',
                    'value': '"KO"',
                    'format': ko_format
                })
                worksheet.conditional_format(1, check_col, len(df), check_col, {
                    'type': 'text',
                    'criteria': 'containing',
                    'value': 'ERROR',
                    'format': ko_format
                })
                worksheet.conditional_format(1, check_col, len(df), check_col, {
                    'type': 'text',
                    'criteria': 'containing',
                    'value': 'PING_OK',
                    'format': warning_format
                })
                
                # Aggiungi filtri
                worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
                
                # Freeze prima riga
                worksheet.freeze_panes(1, 0)
                
                # Aggiungi foglio riepilogo
                summary_data = {
                    "Metrica": ["Totale Dispositivi", "OK", "KO", "Ping OK / SSH KO", 
                              "Errori VPN", "Data Test"],
                    "Valore": [
                        len(results),
                        sum(1 for r in results if r.ssh_status == ConnectionStatus.SSH_PORT_OPEN),
                        sum(1 for r in results if r.ping_status == ConnectionStatus.PING_FAILED or 
                            (r.ping_status == ConnectionStatus.PING_OK and 
                             r.ssh_status != ConnectionStatus.SSH_PORT_OPEN)),
                        sum(1 for r in results if r.ping_status == ConnectionStatus.PING_OK and 
                            r.ssh_status != ConnectionStatus.SSH_PORT_OPEN),
                        sum(1 for r in results if r.ping_status == ConnectionStatus.VPN_ERROR),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ]
                }
                
                df_summary = pd.DataFrame(summary_data)
                df_summary.to_excel(writer, index=False, sheet_name='Riepilogo')
                
                ws_summary = writer.sheets['Riepilogo']
                for col_num, value in enumerate(df_summary.columns.values):
                    ws_summary.write(0, col_num, value, header_format)
                ws_summary.set_column(0, 0, 25)
                ws_summary.set_column(1, 1, 20)
            
            return True, str(output_path)
            
        except Exception as e:
            return False, f"Errore esportazione: {str(e)}"


def update_monitoring_file(source_path: str, dest_dir: Optional[str] = None) -> tuple[bool, str]:
    """
    Aggiorna il file di monitoraggio copiandolo nella directory dati dell'app.
    
    Args:
        source_path: Percorso del nuovo file
        dest_dir: Directory di destinazione. Se None, usa data/
        
    Returns:
        (success, message)
    """
    source = Path(source_path)
    
    if not source.exists():
        return False, f"File sorgente non trovato: {source}"
    
    if dest_dir:
        dest = Path(dest_dir) / DataLoader.DEFAULT_FILE_NAME
    else:
        dest = Path(__file__).parent / "data" / DataLoader.DEFAULT_FILE_NAME
    
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup del file esistente
        if dest.exists():
            backup = dest.with_suffix('.xlsx.bak')
            shutil.copy2(dest, backup)
        
        # Copia nuovo file
        shutil.copy2(source, dest)
        
        return True, f"File aggiornato: {dest}"
        
    except Exception as e:
        return False, f"Errore aggiornamento: {str(e)}"


if __name__ == "__main__":
    # Test
    loader = DataLoader("/mnt/project")
    success, msg, count = loader.load_file()
    print(f"Load: {success}, {msg}")
    
    if success:
        print(f"\nSummary: {loader.get_summary()}")
        
        devices = loader.get_devices()
        print(f"\nPrimi 5 dispositivi:")
        for d in devices[:5]:
            print(f"  {d.device_id} -> {d.ip_address} ({d.vendor.value}, {d.device_type.value})")