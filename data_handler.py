"""
DIGIL Diagnostic Checker - Data Handler Module
===============================================
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
    """Carica i dati dei dispositivi dal file Excel di monitoraggio"""
    
    DEFAULT_FILE_NAME = "Monitoraggio_APPARATI_DIGIL_INSTALLATI.xlsx"
    
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(__file__).parent / "data"
            if not self.data_dir.exists():
                self.data_dir = Path.cwd()
        
        self.monitoring_file: Optional[Path] = None
        self.test_list_file: Optional[Path] = None
        self._df: Optional[pd.DataFrame] = None
        self._test_list_df: Optional[pd.DataFrame] = None
        self._test_device_ids: list[str] = []
        
    def find_monitoring_file(self) -> Optional[Path]:
        """Cerca il file di monitoraggio nella directory dati"""
        exact_path = self.data_dir / self.DEFAULT_FILE_NAME
        if exact_path.exists():
            self.monitoring_file = exact_path
            return exact_path
        
        for f in self.data_dir.glob("*DIGIL*.xlsx"):
            if "monitoraggio" in f.name.lower() or "apparati" in f.name.lower():
                self.monitoring_file = f
                return f
        
        return None
    
    def load_file(self, file_path: Optional[str] = None) -> tuple[bool, str, int]:
        """Carica il file Excel di monitoraggio."""
        if file_path:
            path = Path(file_path)
        else:
            path = self.find_monitoring_file()
            if not path:
                return False, f"File di monitoraggio non trovato in {self.data_dir}", 0
        
        if not path.exists():
            return False, f"File non trovato: {path}", 0
        
        try:
            self._df = pd.read_excel(
                path, 
                sheet_name="Stato",
                header=1,
                engine='openpyxl'
            )
            
            # Colonne richieste
            required_cols = ['DeviceID', 'IP address SIM', 'Linea', 'ST Sostegno']
            missing = [c for c in required_cols if c not in self._df.columns]
            
            if missing:
                return False, f"Colonne mancanti nel file: {missing}", 0
            
            # Verifica se esiste la colonna "Tipo Installazione AM" (colonna A)
            # Potrebbe avere nomi leggermente diversi
            tipo_inst_col = None
            possible_names = ['Tipo Installazione AM', 'Tipo installazione AM', 
                            'TIPO INSTALLAZIONE AM', 'Tipo_Installazione_AM']
            
            for col_name in possible_names:
                if col_name in self._df.columns:
                    tipo_inst_col = col_name
                    break
            
            # Se non trovata con il nome, prova a usare la prima colonna (colonna A)
            if tipo_inst_col is None:
                # La colonna A dopo header=1 dovrebbe essere la prima
                first_col = self._df.columns[0]
                if 'tipo' in str(first_col).lower() or 'installazione' in str(first_col).lower():
                    tipo_inst_col = first_col
            
            self._tipo_installazione_col = tipo_inst_col
            
            self._df = self._df.dropna(subset=['DeviceID', 'IP address SIM'])
            
            self.monitoring_file = path
            
            msg = f"Anagrafica caricata: {len(self._df)} dispositivi"
            if tipo_inst_col:
                msg += f" (colonna '{tipo_inst_col}' trovata)"
            else:
                msg += " (colonna 'Tipo Installazione AM' non trovata)"
            
            return True, msg, len(self._df)
            
        except Exception as e:
            return False, f"Errore caricamento file: {str(e)}", 0
    
    def load_test_list(self, file_path: str, 
                       device_id_column: Optional[str] = None,
                       sheet_name: Optional[str] = None,
                       has_header: bool = True) -> tuple[bool, str, int]:
        """Carica la lista dei DeviceID da testare."""
        path = Path(file_path)
        
        if not path.exists():
            return False, f"File non trovato: {path}", 0
        
        try:
            read_params = {
                'engine': 'openpyxl',
                'header': 0 if has_header else None
            }
            if sheet_name:
                read_params['sheet_name'] = sheet_name
                
            self._test_list_df = pd.read_excel(path, **read_params)
            
            if has_header:
                if device_id_column and device_id_column in self._test_list_df.columns:
                    id_col = device_id_column
                else:
                    possible_names = ['DeviceID', 'deviceid', 'DEVICEID', 'Device_ID', 
                                     'device_id', 'ID', 'id', 'DeviceId']
                    id_col = None
                    for name in possible_names:
                        if name in self._test_list_df.columns:
                            id_col = name
                            break
                    
                    if id_col is None:
                        id_col = self._test_list_df.columns[0]
            else:
                if device_id_column is not None:
                    try:
                        id_col = int(device_id_column)
                    except (ValueError, TypeError):
                        id_col = 0
                else:
                    id_col = 0
            
            self._test_device_ids = self._test_list_df[id_col].dropna().astype(str).tolist()
            
            self._test_device_ids = [did.strip() for did in self._test_device_ids 
                                     if did.strip() and did.strip().lower() != 'nan']
            
            self.test_list_file = path
            col_name = f"colonna {id_col}" if not has_header else f"colonna '{id_col}'"
            return True, f"Lista test caricata: {len(self._test_device_ids)} dispositivi ({col_name})", len(self._test_device_ids)
            
        except Exception as e:
            return False, f"Errore caricamento lista test: {str(e)}", 0
    
    def clear_test_list(self):
        """Rimuove la lista test caricata"""
        self._test_list_df = None
        self._test_device_ids = []
        self.test_list_file = None
    
    def get_devices(self, filter_vendor: Optional[str] = None,
                   filter_type: Optional[str] = None,
                   use_test_list: bool = True) -> list[DeviceInfo]:
        """Restituisce la lista dei dispositivi come oggetti DeviceInfo."""
        if self._df is None:
            return []
        
        devices = []
        
        test_ids_set = set(self._test_device_ids) if (use_test_list and self._test_device_ids) else None
        
        for _, row in self._df.iterrows():
            device_id = str(row.get('DeviceID', ''))
            ip_raw = row.get('IP address SIM', '')
            
            if not device_id or device_id == 'nan' or pd.isna(ip_raw):
                continue
            
            if test_ids_set is not None:
                if device_id not in test_ids_set:
                    continue
            
            ip = normalize_ip(ip_raw)
            
            device_type = detect_device_type(device_id)
            fornitore = str(row.get('Fornitore', ''))
            vendor = detect_vendor(device_id, fornitore)
            
            if filter_vendor:
                if vendor.value.upper() != filter_vendor.upper():
                    continue
            
            if filter_type:
                if device_type.value.lower() != filter_type.lower():
                    continue
            
            # Leggi "Tipo Installazione AM" se disponibile
            tipo_installazione_am = ""
            if hasattr(self, '_tipo_installazione_col') and self._tipo_installazione_col:
                tipo_inst_value = row.get(self._tipo_installazione_col, '')
                if pd.notna(tipo_inst_value):
                    tipo_installazione_am = str(tipo_inst_value).strip()
            
            device = DeviceInfo(
                device_id=device_id,
                ip_address=ip,
                linea=str(row.get('Linea', '')),
                sostegno=str(row.get('ST Sostegno', '')),
                fornitore=fornitore,
                device_type=device_type,
                vendor=vendor,
                tipo_installazione_am=tipo_installazione_am
            )
            
            devices.append(device)
        
        return devices
    
    def get_summary(self) -> dict:
        """Restituisce un sommario dei dati caricati"""
        if self._df is None:
            return {"loaded": False}
        
        all_devices = self.get_devices(use_test_list=False)
        test_devices = self.get_devices(use_test_list=True)
        
        vendor_counts = {}
        type_counts = {"master": 0, "slave": 0, "unknown": 0}
        
        for d in test_devices:
            v = d.vendor.value
            vendor_counts[v] = vendor_counts.get(v, 0) + 1
            type_counts[d.device_type.value] += 1
        
        not_found = []
        if self._test_device_ids:
            anagrafica_ids = set(str(row.get('DeviceID', '')) for _, row in self._df.iterrows())
            not_found = [did for did in self._test_device_ids if did not in anagrafica_ids]
        
        return {
            "loaded": True,
            "file": str(self.monitoring_file) if self.monitoring_file else "",
            "total_in_anagrafica": len(all_devices),
            "total_devices": len(test_devices),
            "by_vendor": vendor_counts,
            "by_type": type_counts,
            "test_list_loaded": bool(self._test_device_ids),
            "test_list_file": str(self.test_list_file) if self.test_list_file else "",
            "test_list_count": len(self._test_device_ids),
            "not_found_in_anagrafica": not_found,
            "not_found_count": len(not_found),
            "has_tipo_installazione": hasattr(self, '_tipo_installazione_col') and self._tipo_installazione_col is not None
        }


class ResultExporter:
    """Esporta i risultati dei test in formato Excel"""
    
    def __init__(self):
        self.output_dir = Path.home() / "Downloads"
        if not self.output_dir.exists():
            self.output_dir = Path.cwd()
    
    def _get_note_for_device(self, device) -> str:
        """
        Genera la nota per un dispositivo.
        
        Logica:
        - Se malfunction_type == "OK" E tipo_installazione_am == "Inst. Completa"
          -> "Verificare Tiro"
        - Altrimenti mostra eventuali errori
        """
        # Controlla la condizione speciale per "Verificare Tiro"
        malfunction = getattr(device, 'malfunction_type', '')
        tipo_inst = getattr(device, 'tipo_installazione_am', '')
        
        if malfunction == "OK" and tipo_inst == "Inst. Completa":
            return "Verificare Tiro"
        
        # Altrimenti, raccogli gli errori
        errors = []
        if hasattr(device, 'error_message') and device.error_message:
            errors.append(device.error_message)
        if hasattr(device, 'api_error') and device.api_error:
            errors.append(device.api_error)
        if hasattr(device, 'mongodb_error') and device.mongodb_error:
            errors.append(device.mongodb_error)
        
        return "; ".join(errors)[:50] if errors else ""
    
    def export_diagnostic_results(self, results: list, 
                                   output_path: Optional[str] = None) -> tuple[bool, str]:
        """Esporta i risultati diagnostici in un file Excel."""
        if not results:
            return False, "Nessun risultato da esportare"
        
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"DIGIL_Diagnostic_{timestamp}.xlsx"
        
        try:
            data = []
            for r in results:
                # Determina esiti
                ssh_ok = r.ssh_status == ConnectionStatus.SSH_PORT_OPEN if hasattr(r, 'ssh_status') else None
                ping_ok = r.ping_status == ConnectionStatus.PING_OK if hasattr(r, 'ping_status') else None
                mongodb_ok = getattr(r, 'mongodb_has_data', None)
                lte_ok = getattr(r, 'lte_ok', None)
                battery_ok = getattr(r, 'battery_ok', None)
                door_open = getattr(r, 'door_open', None)
                malfunction = getattr(r, 'malfunction_type', '')
                
                # MongoDB status
                if mongodb_ok is True:
                    ts = getattr(r, 'mongodb_last_timestamp', None)
                    mongo_status = ts.strftime("%d/%m/%Y") if ts else "Data"
                elif mongodb_ok is False:
                    mongo_status = "KO"
                else:
                    mongo_status = getattr(r, 'mongodb_error', '-')[:20] if getattr(r, 'mongodb_error', '') else "-"
                
                # Genera la nota (con logica "Verificare Tiro")
                note = self._get_note_for_device(r)
                
                data.append({
                    "Linea": r.linea,
                    "ST Sostegno": r.sostegno,
                    "DeviceID": r.device_id,
                    "IP Address": r.ip_address,
                    "Vendor": r.vendor.value,
                    "Tipo": r.device_type.value,
                    "Tipo Installazione AM": getattr(r, 'tipo_installazione_am', ''),
                    "Check MongoDB": mongo_status,
                    "Check LTE": "OK" if lte_ok else ("KO" if lte_ok is False else "0"),
                    "Check SSH": "OK" if ssh_ok else ("KO" if ssh_ok is False else "-"),
                    "Batteria": "OK" if battery_ok else ("KO" if battery_ok is False else "-"),
                    "Porta": "KO" if door_open else ("OK" if door_open is False else "-"),
                    "SOC %": getattr(r, 'soc_percent', None) or "",
                    "SOH %": getattr(r, 'soh_percent', None) or "",
                    "Segnale dBm": getattr(r, 'lte_signal_dbm', None) or "",
                    "Canale": getattr(r, 'channel', None) or "",
                    "API Timestamp": getattr(r, 'api_timestamp', None) or "",
                    "Tipo Malfunzionamento": malfunction,
                    "Note": note,
                    "Timestamp Test": r.test_timestamp if hasattr(r, 'test_timestamp') else ""
                })
            
            df = pd.DataFrame(data)
            
            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Risultati Diagnostici')
                
                workbook = writer.book
                worksheet = writer.sheets['Risultati Diagnostici']
                
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#0066CC',
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
                
                # Formato per "Verificare Tiro" (giallo/arancione)
                verificare_tiro_format = workbook.add_format({
                    'bg_color': '#FFEB9C',
                    'font_color': '#9C6500',
                    'border': 1,
                    'bold': True
                })
                
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                column_widths = {
                    'Linea': 10, 'ST Sostegno': 20, 'DeviceID': 28, 'IP Address': 14,
                    'Vendor': 8, 'Tipo': 8, 'Tipo Installazione AM': 18,
                    'Check MongoDB (24h)': 12, 'Check LTE': 10,
                    'Check SSH': 10, 'Batteria': 9, 'Porta': 7, 'SOC %': 7, 'SOH %': 7,
                    'Segnale dBm': 11, 'Canale': 8, 'API Timestamp': 18,
                    'Tipo Malfunzionamento': 18, 
                    'Note': 30, 'Timestamp Test': 18
                }
                
                for col_num, col_name in enumerate(df.columns):
                    width = column_widths.get(col_name, 12)
                    worksheet.set_column(col_num, col_num, width)
                
                # Formattazione condizionale colonna Malfunzionamento
                malf_col = df.columns.get_loc('Tipo Malfunzionamento')
                worksheet.conditional_format(1, malf_col, len(df), malf_col, {
                    'type': 'cell',
                    'criteria': '==',
                    'value': '"OK"',
                    'format': ok_format
                })
                worksheet.conditional_format(1, malf_col, len(df), malf_col, {
                    'type': 'cell',
                    'criteria': '!=',
                    'value': '"OK"',
                    'format': ko_format
                })
                
                # Formattazione condizionale colonna Note per "Verificare Tiro"
                note_col = df.columns.get_loc('Note')
                worksheet.conditional_format(1, note_col, len(df), note_col, {
                    'type': 'text',
                    'criteria': 'containing',
                    'value': 'Verificare Tiro',
                    'format': verificare_tiro_format
                })
                
                worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
                worksheet.freeze_panes(1, 0)
                
                # Riepilogo
                verificare_tiro_count = sum(1 for r in results 
                                           if getattr(r, 'malfunction_type', '') == "OK" 
                                           and getattr(r, 'tipo_installazione_am', '') == "Inst. Completa")
                
                summary_data = {
                    "Metrica": ["Totale Dispositivi", "OK", "Disconnesso", "Metriche assenti",
                              "Allarme batteria", "Porta aperta", "Non classificato", 
                              "Da verificare Tiro", "Data Test"],
                    "Valore": [
                        len(results),
                        sum(1 for r in results if getattr(r, 'malfunction_type', '') == "OK"),
                        sum(1 for r in results if getattr(r, 'malfunction_type', '') == "Disconnesso"),
                        sum(1 for r in results if getattr(r, 'malfunction_type', '') == "Metriche assenti"),
                        sum(1 for r in results if getattr(r, 'malfunction_type', '') == "Allarme batteria"),
                        sum(1 for r in results if getattr(r, 'malfunction_type', '') == "Porta aperta"),
                        sum(1 for r in results if getattr(r, 'malfunction_type', '') == "Non classificato"),
                        verificare_tiro_count,
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
    
    def export_results(self, results: list, output_path: Optional[str] = None) -> tuple[bool, str]:
        """Alias per compatibilità con vecchia versione"""
        return self.export_diagnostic_results(results, output_path)


def update_monitoring_file(source_path: str, dest_dir: Optional[str] = None) -> tuple[bool, str]:
    """Aggiorna il file di monitoraggio."""
    source = Path(source_path)
    
    if not source.exists():
        return False, f"File sorgente non trovato: {source}"
    
    if dest_dir:
        dest = Path(dest_dir) / DataLoader.DEFAULT_FILE_NAME
    else:
        dest = Path(__file__).parent / "data" / DataLoader.DEFAULT_FILE_NAME
    
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        if dest.exists():
            backup = dest.with_suffix('.xlsx.bak')
            shutil.copy2(dest, backup)
        
        shutil.copy2(source, dest)
        
        return True, f"File aggiornato: {dest}"
        
    except Exception as e:
        return False, f"Errore aggiornamento: {str(e)}"