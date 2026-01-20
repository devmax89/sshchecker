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
        
        Logica (in ordine di priorità):
        1. Se malfunction_type == "OK" E tipo_installazione_am == "Inst. Completa"
           -> "Verificare Tiro"
        2. Se c'è connectivity_note (es: "Non raggiungibile (Ping KO, SSH KO)")
           -> Mostra la connectivity_note
        3. Altrimenti mostra eventuali errori tecnici
        """
        malfunction = getattr(device, 'malfunction_type', '')
        tipo_inst = getattr(device, 'tipo_installazione_am', '')
        connectivity_note = getattr(device, 'connectivity_note', '')
        
        notes = []
        
        # 1. Verificare Tiro (priorità alta)
        if malfunction == "OK" and tipo_inst == "Inst. Completa":
            notes.append("Verificare Tiro")
        
        # 2. Connectivity note (se presente)
        if connectivity_note:
            notes.append(connectivity_note)
        
        # Se abbiamo già delle note, restituiscile
        if notes:
            return "; ".join(notes)
        
        # 3. Altrimenti, raccogli gli errori tecnici
        errors = []
        if hasattr(device, 'error_message') and device.error_message:
            errors.append(device.error_message)
        if hasattr(device, 'api_error') and device.api_error:
            errors.append(device.api_error)
        if hasattr(device, 'mongodb_error') and device.mongodb_error:
            errors.append(device.mongodb_error)
        
        return "; ".join(errors)[:50] if errors else ""
    
    def export_diagnostic_results(self, results: list, 
                                   output_path: Optional[str] = None,
                                   soc_data: Optional[dict] = None,
                                   channel_data: Optional[dict] = None,
                                   signal_data: Optional[dict] = None) -> tuple[bool, str]:
        """Esporta i risultati diagnostici in un file Excel.
        
        Args:
            results: Lista dei DeviceInfo con i risultati
            output_path: Percorso del file di output (opzionale)
            soc_data: Dict {device_id: soc_history} per lo sheet Storico SOC (opzionale)
            channel_data: Dict {device_id: channel_history} per lo sheet Storico Canale (opzionale)
            signal_data: Dict {device_id: signal_history} per lo sheet Storico Segnale (opzionale)
        """
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
                    mongo_status = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "Data"
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
                    "Check MongoDB (24h)": mongo_status,
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
                    'Check MongoDB (24h)': 18, 'Check LTE': 10,
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
                
                # Aggiungi sheet Storico SOC se ci sono dati
                if soc_data:
                    print(f"DEBUG: soc_data ha {len(soc_data)} dispositivi")
                    self.export_soc_history_sheet(writer, workbook, results, soc_data, days=15)
                else:
                    print("DEBUG: soc_data è vuoto o None")
                
                # Aggiungi sheet Storico Canale se ci sono dati
                if channel_data:
                    print(f"DEBUG: channel_data ha {len(channel_data)} dispositivi")
                    self.export_channel_history_sheet(writer, workbook, results, channel_data, hours=24)
                else:
                    print("DEBUG: channel_data è vuoto o None")
                
                # Aggiungi sheet Storico Segnale se ci sono dati
                if signal_data:
                    print(f"DEBUG: signal_data ha {len(signal_data)} dispositivi")
                    self.export_signal_history_sheet(writer, workbook, results, signal_data, hours=24)
                else:
                    print("DEBUG: signal_data è vuoto o None")
            
            return True, str(output_path)
            
        except Exception as e:
            return False, f"Errore esportazione: {str(e)}"
    
    def export_soc_history_sheet(self, writer, workbook, results: list, soc_data: dict, days: int = 15):
        """
        Aggiunge lo sheet "Storico SOC" al file Excel.
        
        Args:
            writer: ExcelWriter attivo
            workbook: Workbook xlsxwriter
            results: Lista dei DeviceInfo
            soc_data: Dict {device_id: soc_history_dict} con i dati SOC
            days: Numero di giorni analizzati
        """
        from datetime import datetime, timedelta
        
        # Genera le date degli ultimi N giorni
        today = datetime.now().date()
        date_columns = []
        for i in range(days):
            d = today - timedelta(days=i)
            date_columns.append(d.strftime("%Y-%m-%d"))
        
        # Costruisci i dati
        data = []
        for r in results:
            device_soc = soc_data.get(r.device_id, {})
            daily_soc = device_soc.get("daily_soc", {})
            
            row = {
                "DeviceID": r.device_id,
                "Linea": r.linea,
                "Sostegno": r.sostegno,
                "Vendor": r.vendor.value,
                "Tipo": r.device_type.value,
            }
            
            # Aggiungi colonne per ogni giorno
            for date_str in date_columns:
                row[date_str] = daily_soc.get(date_str, "")
            
            # Statistiche
            row["Media"] = device_soc.get("avg", "")
            row["Min"] = device_soc.get("min", "")
            row["Max"] = device_soc.get("max", "")
            row["Trend"] = device_soc.get("trend", "")
            
            if device_soc.get("error"):
                row["Errore"] = device_soc.get("error", "")[:30]
            else:
                row["Errore"] = ""
            
            data.append(row)
        
        import pandas as pd
        df_soc = pd.DataFrame(data)
        df_soc.to_excel(writer, index=False, sheet_name='Storico SOC')
        
        # Formattazione
        worksheet = writer.sheets['Storico SOC']
        
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#0066CC',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        # Formati condizionali per SOC
        low_soc_format = workbook.add_format({
            'bg_color': '#FFC7CE',
            'font_color': '#9C0006',
            'border': 1
        })
        
        medium_soc_format = workbook.add_format({
            'bg_color': '#FFEB9C',
            'font_color': '#9C6500',
            'border': 1
        })
        
        high_soc_format = workbook.add_format({
            'bg_color': '#C6EFCE',
            'font_color': '#006100',
            'border': 1
        })
        
        trend_up_format = workbook.add_format({
            'bg_color': '#C6EFCE',
            'font_color': '#006100',
            'bold': True,
            'align': 'center'
        })
        
        trend_down_format = workbook.add_format({
            'bg_color': '#FFC7CE',
            'font_color': '#9C0006',
            'bold': True,
            'align': 'center'
        })
        
        # Scrivi header
        for col_num, value in enumerate(df_soc.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Imposta larghezze colonne
        worksheet.set_column(0, 0, 28)  # DeviceID
        worksheet.set_column(1, 1, 10)  # Linea
        worksheet.set_column(2, 2, 18)  # Sostegno
        worksheet.set_column(3, 3, 8)   # Vendor
        worksheet.set_column(4, 4, 8)   # Tipo
        
        # Colonne date (più strette)
        date_start_col = 5
        date_end_col = date_start_col + days - 1
        for col in range(date_start_col, date_end_col + 1):
            worksheet.set_column(col, col, 11)
        
        # Colonne statistiche
        stats_start_col = date_end_col + 1
        worksheet.set_column(stats_start_col, stats_start_col, 7)      # Media
        worksheet.set_column(stats_start_col + 1, stats_start_col + 1, 5)  # Min
        worksheet.set_column(stats_start_col + 2, stats_start_col + 2, 5)  # Max
        worksheet.set_column(stats_start_col + 3, stats_start_col + 3, 6)  # Trend
        worksheet.set_column(stats_start_col + 4, stats_start_col + 4, 25) # Errore
        
        # Formattazione condizionale per le colonne SOC (valori numerici)
        # SOC < 30 = rosso, 30-60 = giallo, > 60 = verde
        for col in range(date_start_col, date_end_col + 1):
            worksheet.conditional_format(1, col, len(df_soc), col, {
                'type': 'cell',
                'criteria': '<',
                'value': 30,
                'format': low_soc_format
            })
            worksheet.conditional_format(1, col, len(df_soc), col, {
                'type': 'cell',
                'criteria': 'between',
                'minimum': 30,
                'maximum': 60,
                'format': medium_soc_format
            })
            worksheet.conditional_format(1, col, len(df_soc), col, {
                'type': 'cell',
                'criteria': '>',
                'value': 60,
                'format': high_soc_format
            })
        
        # Formattazione condizionale per Trend
        trend_col = stats_start_col + 3
        worksheet.conditional_format(1, trend_col, len(df_soc), trend_col, {
            'type': 'text',
            'criteria': 'containing',
            'value': '↑',
            'format': trend_up_format
        })
        worksheet.conditional_format(1, trend_col, len(df_soc), trend_col, {
            'type': 'text',
            'criteria': 'containing',
            'value': '↓',
            'format': trend_down_format
        })
        
        # Freeze panes e autofilter
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(df_soc), len(df_soc.columns) - 1)
    
    def export_channel_history_sheet(self, writer, workbook, results: list, channel_data: dict, hours: int = 24):
        """
        Aggiunge lo sheet "Storico Canale" al file Excel.
        
        Args:
            writer: ExcelWriter attivo
            workbook: Workbook xlsxwriter
            results: Lista dei DeviceInfo
            channel_data: Dict {device_id: channel_history_dict} con i dati canale
            hours: Numero di ore analizzate
        """
        from datetime import datetime, timedelta
        
        # Genera le ore delle ultime N ore
        now = datetime.now()
        hour_columns = []
        for i in range(hours):
            h = now - timedelta(hours=i)
            hour_columns.append(h.strftime("%Y-%m-%d %H:00"))
        
        # Costruisci i dati
        data = []
        for r in results:
            device_channel = channel_data.get(r.device_id, {})
            hourly_channel = device_channel.get("hourly_channel", {})
            
            row = {
                "DeviceID": r.device_id,
                "Linea": r.linea,
                "Sostegno": r.sostegno,
                "Vendor": r.vendor.value,
                "Tipo": r.device_type.value,
            }
            
            # Aggiungi colonne per ogni ora
            for hour_str in hour_columns:
                row[hour_str] = hourly_channel.get(hour_str, "")
            
            # Statistiche
            row["LTE"] = device_channel.get("lte_count", "")
            row["NBIoT"] = device_channel.get("nbiot_count", "")
            row["Altro"] = device_channel.get("other_count", "")
            row["Canali Usati"] = ", ".join(device_channel.get("channels_used", []))
            
            if device_channel.get("error"):
                row["Errore"] = device_channel.get("error", "")[:30]
            else:
                row["Errore"] = ""
            
            data.append(row)
        
        import pandas as pd
        df_channel = pd.DataFrame(data)
        df_channel.to_excel(writer, index=False, sheet_name='Storico Canale')
        
        # Formattazione
        worksheet = writer.sheets['Storico Canale']
        
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#0066CC',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        # Formati per canale
        lte_format = workbook.add_format({
            'bg_color': '#C6EFCE',
            'font_color': '#006100',
            'border': 1,
            'align': 'center'
        })
        
        # NBIoT = BLU
        nbiot_format = workbook.add_format({
            'bg_color': '#CCE5FF',  
            'font_color': '#004C99', 
            'border': 1,
            'align': 'center'
        })
        
        # Altro (LORA) = GIALLO
        other_format = workbook.add_format({
            'bg_color': '#FFEB9C',   
            'font_color': '#9C6500', 
            'border': 1,
            'align': 'center'
        })
        
        # Scrivi header
        for col_num, value in enumerate(df_channel.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Imposta larghezze colonne
        worksheet.set_column(0, 0, 28)  # DeviceID
        worksheet.set_column(1, 1, 10)  # Linea
        worksheet.set_column(2, 2, 18)  # Sostegno
        worksheet.set_column(3, 3, 8)   # Vendor
        worksheet.set_column(4, 4, 8)   # Tipo
        
        # Colonne ore (più strette)
        hour_start_col = 5
        hour_end_col = hour_start_col + hours - 1
        for col in range(hour_start_col, hour_end_col + 1):
            worksheet.set_column(col, col, 15)
        
        # Colonne statistiche
        stats_start_col = hour_end_col + 1
        worksheet.set_column(stats_start_col, stats_start_col, 5)      # LTE
        worksheet.set_column(stats_start_col + 1, stats_start_col + 1, 6)  # NBIoT
        worksheet.set_column(stats_start_col + 2, stats_start_col + 2, 5)  # Altro
        worksheet.set_column(stats_start_col + 3, stats_start_col + 3, 15) # Canali Usati
        worksheet.set_column(stats_start_col + 4, stats_start_col + 4, 25) # Errore
        
        # Formattazione condizionale per le colonne canale
        for col in range(hour_start_col, hour_end_col + 1):
            # LTE = verde
            worksheet.conditional_format(1, col, len(df_channel), col, {
                'type': 'text',
                'criteria': 'containing',
                'value': 'LTE',
                'format': lte_format
            })
            # NBIOT = giallo
            worksheet.conditional_format(1, col, len(df_channel), col, {
                'type': 'text',
                'criteria': 'containing',
                'value': 'NBIOT',
                'format': nbiot_format
            })
            worksheet.conditional_format(1, col, len(df_channel), col, {
                'type': 'text',
                'criteria': 'containing',
                'value': 'NB-IOT',
                'format': nbiot_format
            })
        
        # Freeze panes e autofilter
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(df_channel), len(df_channel.columns) - 1)
    
    def export_signal_history_sheet(self, writer, workbook, results: list, signal_data: dict, hours: int = 24):
        """
        Aggiunge lo sheet "Storico Segnale" al file Excel.
        
        Args:
            writer: ExcelWriter attivo
            workbook: Workbook xlsxwriter
            results: Lista dei DeviceInfo
            signal_data: Dict {device_id: signal_history_dict} con i dati segnale
            hours: Numero di ore analizzate
        """
        from datetime import datetime, timedelta
        
        # Genera le ore delle ultime N ore
        now = datetime.now()
        hour_columns = []
        for i in range(hours):
            h = now - timedelta(hours=i)
            hour_columns.append(h.strftime("%Y-%m-%d %H:00"))
        
        # Costruisci i dati
        data = []
        for r in results:
            device_signal = signal_data.get(r.device_id, {})
            hourly_signal = device_signal.get("hourly_signal", {})
            
            row = {
                "DeviceID": r.device_id,
                "Linea": r.linea,
                "Sostegno": r.sostegno,
                "Vendor": r.vendor.value,
                "Tipo": r.device_type.value,
            }
            
            # Aggiungi colonne per ogni ora
            for hour_str in hour_columns:
                row[hour_str] = hourly_signal.get(hour_str, "")
            
            # Statistiche
            row["Media"] = device_signal.get("avg", "")
            row["Min"] = device_signal.get("min", "")
            row["Max"] = device_signal.get("max", "")
            
            if device_signal.get("error"):
                row["Errore"] = device_signal.get("error", "")[:30]
            else:
                row["Errore"] = ""
            
            data.append(row)
        
        import pandas as pd
        df_signal = pd.DataFrame(data)
        df_signal.to_excel(writer, index=False, sheet_name='Storico Segnale')
        
        # Formattazione
        worksheet = writer.sheets['Storico Segnale']
        
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#0066CC',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        # Formati per livello segnale (dBm)
        # Segnale forte: > -70 dBm = verde
        strong_signal_format = workbook.add_format({
            'bg_color': '#C6EFCE',
            'font_color': '#006100',
            'border': 1,
            'align': 'center'
        })
        
        # Segnale medio: -70 a -85 dBm = giallo
        medium_signal_format = workbook.add_format({
            'bg_color': '#FFEB9C',
            'font_color': '#9C6500',
            'border': 1,
            'align': 'center'
        })
        
        # Segnale debole: < -85 dBm = rosso
        weak_signal_format = workbook.add_format({
            'bg_color': '#FFC7CE',
            'font_color': '#9C0006',
            'border': 1,
            'align': 'center'
        })
        
        # Scrivi header
        for col_num, value in enumerate(df_signal.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Imposta larghezze colonne
        worksheet.set_column(0, 0, 28)  # DeviceID
        worksheet.set_column(1, 1, 10)  # Linea
        worksheet.set_column(2, 2, 18)  # Sostegno
        worksheet.set_column(3, 3, 8)   # Vendor
        worksheet.set_column(4, 4, 8)   # Tipo
        
        # Colonne ore (più strette)
        hour_start_col = 5
        hour_end_col = hour_start_col + hours - 1
        for col in range(hour_start_col, hour_end_col + 1):
            worksheet.set_column(col, col, 12)
        
        # Colonne statistiche
        stats_start_col = hour_end_col + 1
        worksheet.set_column(stats_start_col, stats_start_col, 7)      # Media
        worksheet.set_column(stats_start_col + 1, stats_start_col + 1, 5)  # Min
        worksheet.set_column(stats_start_col + 2, stats_start_col + 2, 5)  # Max
        worksheet.set_column(stats_start_col + 3, stats_start_col + 3, 25) # Errore
        
        # Formattazione condizionale per le colonne segnale
        # Nota: i valori sono negativi (dBm), quindi:
        # > -70 (forte) significa valore più grande (es: -65 > -70)
        # < -85 (debole) significa valore più piccolo (es: -95 < -85)
        for col in range(hour_start_col, hour_end_col + 1):
            # Segnale forte: > -70 dBm
            worksheet.conditional_format(1, col, len(df_signal), col, {
                'type': 'cell',
                'criteria': '>',
                'value': -70,
                'format': strong_signal_format
            })
            # Segnale medio: tra -85 e -70 dBm
            worksheet.conditional_format(1, col, len(df_signal), col, {
                'type': 'cell',
                'criteria': 'between',
                'minimum': -85,
                'maximum': -70,
                'format': medium_signal_format
            })
            # Segnale debole: < -85 dBm
            worksheet.conditional_format(1, col, len(df_signal), col, {
                'type': 'cell',
                'criteria': '<',
                'value': -85,
                'format': weak_signal_format
            })
        
        # Freeze panes e autofilter
        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(df_signal), len(df_signal.columns) - 1)
    
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