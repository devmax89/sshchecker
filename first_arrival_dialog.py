"""
DIGIL Diagnostic Checker - First Arrival Dialog
================================================
Dialog dedicata al check "Primo dato MongoDB": verifica senza limite
temporale se un dispositivo ha mai inviato dati a MongoDB.
"""

from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton,
    QButtonGroup, QPlainTextEdit, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView, QProgressBar,
    QTextEdit, QGroupBox, QFrame, QWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor


class FirstArrivalWorker(QThread):
    """Thread che esegue il check 'primo dato MongoDB' sui device forniti."""

    progress_signal = pyqtSignal(int, int, str)  # current, total, device_id
    result_signal = pyqtSignal(str, dict)        # device_id, result dict
    phase_signal = pyqtSignal(str)
    completed_signal = pyqtSignal()
    error_signal = pyqtSignal(str)

    def __init__(self, device_ids: list[str]):
        super().__init__()
        self.device_ids = device_ids
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        try:
            from mongodb_checker import MongoDBChecker, get_tunnel_manager

            tunnel_manager = get_tunnel_manager()

            if not tunnel_manager.is_active():
                self.phase_signal.emit("Avvio tunnel SSH verso MongoDB...")
                success, msg, _port = tunnel_manager.start_tunnel()
                if not success:
                    self.error_signal.emit(f"Tunnel SSH fallito: {msg}")
                    return

            self.phase_signal.emit("Connessione a MongoDB...")
            mongo_checker = MongoDBChecker(tunnel_manager)
            success, msg = mongo_checker.connect()
            if not success:
                self.error_signal.emit(f"Connessione MongoDB fallita: {msg}")
                return

            total = len(self.device_ids)
            self.phase_signal.emit(f"Check primo dato MongoDB per {total} dispositivi...")

            for i, device_id in enumerate(self.device_ids, start=1):
                if self._stop_requested:
                    break

                self.progress_signal.emit(i, total, device_id)

                try:
                    res = mongo_checker.check_device_first_data(device_id)
                    result_dict = {
                        "has_data": bool(res.has_data_24h),
                        "last_timestamp": res.last_timestamp,
                        "last_received_on": res.last_received_on,
                        "error": res.error
                    }
                except Exception as e:
                    result_dict = {
                        "has_data": False,
                        "last_timestamp": None,
                        "last_received_on": None,
                        "error": str(e)[:150]
                    }

                self.result_signal.emit(device_id, result_dict)

            mongo_checker.disconnect()
            self.completed_signal.emit()

        except Exception as e:
            self.error_signal.emit(str(e))


class FirstArrivalDialog(QDialog):
    """Dialog per il check 'Primo dato MongoDB'."""

    def __init__(self, data_loader, result_exporter, parent=None):
        super().__init__(parent)
        self.data_loader = data_loader
        self.result_exporter = result_exporter
        self.worker: Optional[FirstArrivalWorker] = None
        self.results: list[dict] = []
        self._external_file_ids: list[str] = []
        self._external_file_name: str = ""

        self.setWindowTitle("Check L.S. MongoDB")
        self.setMinimumSize(1250, 750)

        self._build_ui()
        self._update_source_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Intro
        intro = QLabel(
            "Verifica se i dispositivi hanno <b>mai</b> inviato dati a MongoDB "
            "(nessun limite temporale). Un dispositivo è KO solo se non esiste "
            "alcun documento nella collection <code>event</code>.<br>"
            "<i>Check MongoDB</i> = timestamp del payload (orologio del device) &mdash; "
            "<i>Ultimo receivedOn</i> = timestamp broker-side (ricezione reale su MongoDB)."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color: #444;")
        layout.addWidget(intro)

        # === Sorgente dispositivi ===
        source_group = QGroupBox("Sorgente dispositivi")
        source_layout = QVBoxLayout(source_group)

        radio_row = QHBoxLayout()
        self.radio_anagrafica = QRadioButton("Tutta l'anagrafica caricata")
        self.radio_text = QRadioButton("Lista testuale (un DeviceID per riga)")
        self.radio_file = QRadioButton("File Excel (una colonna senza header)")
        self.radio_anagrafica.setChecked(True)

        self.radio_group = QButtonGroup(self)
        self.radio_group.addButton(self.radio_anagrafica)
        self.radio_group.addButton(self.radio_text)
        self.radio_group.addButton(self.radio_file)
        self.radio_group.buttonClicked.connect(self._update_source_ui)

        radio_row.addWidget(self.radio_anagrafica)
        radio_row.addWidget(self.radio_text)
        radio_row.addWidget(self.radio_file)
        radio_row.addStretch()
        source_layout.addLayout(radio_row)

        # Anagrafica info
        self.anagrafica_label = QLabel()
        self.anagrafica_label.setStyleSheet("color: #0066CC; font-style: italic;")
        source_layout.addWidget(self.anagrafica_label)

        # Text input
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText(
            "Incolla qui i DeviceID, uno per riga.\n"
            "Esempio:\n"
            "1:1:2:16:21:DIGIL_IND_0905\n"
            "1:1:2:15:22:DIGIL_MRN_0051"
        )
        self.text_input.setMaximumHeight(120)
        source_layout.addWidget(self.text_input)

        # File picker
        file_row = QHBoxLayout()
        self.file_label = QLabel("Nessun file selezionato")
        self.file_label.setStyleSheet("color: #666666; font-style: italic;")
        self.file_btn = QPushButton("Sfoglia…")
        self.file_btn.setObjectName("secondaryButton")
        self.file_btn.clicked.connect(self._pick_file)
        file_row.addWidget(self.file_label, stretch=1)
        file_row.addWidget(self.file_btn)
        self.file_widget = QWidget()
        self.file_widget.setLayout(file_row)
        source_layout.addWidget(self.file_widget)

        layout.addWidget(source_group)

        # === Azioni ===
        action_row = QHBoxLayout()
        self.start_btn = QPushButton("▶ Avvia Check")
        self.start_btn.clicked.connect(self._start_check)
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_check)
        self.export_btn = QPushButton("📥 Esporta Excel")
        self.export_btn.setObjectName("exportButton")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export)

        action_row.addWidget(self.start_btn)
        action_row.addWidget(self.stop_btn)
        action_row.addStretch()
        action_row.addWidget(self.export_btn)
        layout.addLayout(action_row)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m (%p%)")
        layout.addWidget(self.progress_bar)

        # Stats
        self.stats_label = QLabel("OK: 0 | KO: 0")
        self.stats_label.setStyleSheet("color: #666666;")
        layout.addWidget(self.stats_label)

        # Table
        self.table = QTableWidget()
        columns = ["ST Sostegno", "DeviceID", "Data Installazione",
                   "Vendor", "Tipo", "Check MongoDB", "Ultimo receivedOn"]
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 160)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 80)
        self.table.setColumnWidth(5, 170)
        self.table.setColumnWidth(6, 170)

        layout.addWidget(self.table, stretch=1)

        # Log
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(100)
        self.log_area.setStyleSheet(
            "background-color: #1E1E1E; color: #CCCCCC;"
            "font-family: Consolas, 'Courier New', monospace; font-size: 11px;"
            "border: 1px solid #CCCCCC; border-radius: 4px;"
        )
        layout.addWidget(self.log_area)

        # Close
        close_row = QHBoxLayout()
        close_row.addStretch()
        self.close_btn = QPushButton("Chiudi")
        self.close_btn.setObjectName("secondaryButton")
        self.close_btn.clicked.connect(self.accept)
        close_row.addWidget(self.close_btn)
        layout.addLayout(close_row)

        self._refresh_anagrafica_info()

    def _refresh_anagrafica_info(self):
        summary = self.data_loader.get_summary()
        if summary.get("loaded"):
            total = summary.get("total_in_anagrafica", summary.get("total_devices", 0))
            self.anagrafica_label.setText(
                f"✓ Anagrafica caricata: {total} dispositivi disponibili"
            )
        else:
            self.anagrafica_label.setText(
                "⚠ Nessuna anagrafica caricata. Usa lista testuale o file Excel."
            )

    def _update_source_ui(self):
        is_text = self.radio_text.isChecked()
        is_file = self.radio_file.isChecked()
        self.text_input.setVisible(is_text)
        self.file_widget.setVisible(is_file)

    def _pick_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona Excel con lista DeviceID",
            "",
            "Excel Files (*.xlsx *.xls);;CSV Files (*.csv);;All Files (*)"
        )
        if not file_path:
            return

        try:
            path = Path(file_path)
            if path.suffix.lower() == ".csv":
                df = pd.read_csv(path, header=None, dtype=str)
            else:
                df = pd.read_excel(path, header=None, engine='openpyxl', dtype=str)

            if df.empty:
                raise ValueError("File vuoto")

            ids = df.iloc[:, 0].dropna().astype(str).tolist()
            ids = [i.strip() for i in ids if i.strip() and i.strip().lower() != 'nan']

            if not ids:
                raise ValueError("Nessun DeviceID valido trovato nella prima colonna")

            self._external_file_ids = ids
            self._external_file_name = path.name
            self.file_label.setText(f"✓ {path.name} ({len(ids)} DeviceID)")
            self.file_label.setStyleSheet("color: #009933;")
            self._log(f"File caricato: {len(ids)} DeviceID da {path.name}", "SUCCESS")
        except Exception as e:
            QMessageBox.warning(self, "Errore", f"Impossibile leggere il file:\n{e}")
            self._external_file_ids = []
            self._external_file_name = ""
            self.file_label.setText("Nessun file selezionato")
            self.file_label.setStyleSheet("color: #666666; font-style: italic;")

    def _collect_device_ids(self) -> list[str]:
        if self.radio_anagrafica.isChecked():
            devices = self.data_loader.get_devices(use_test_list=False)
            return [d.device_id for d in devices]

        if self.radio_text.isChecked():
            raw = self.text_input.toPlainText()
            ids = [line.strip() for line in raw.splitlines()]
            return [i for i in ids if i]

        if self.radio_file.isChecked():
            return list(self._external_file_ids)

        return []

    def _build_anagrafica_lookup(self) -> dict:
        """Ritorna dict {device_id: DeviceInfo} dall'anagrafica caricata."""
        lookup = {}
        try:
            for d in self.data_loader.get_devices(use_test_list=False):
                lookup[d.device_id] = d
        except Exception:
            pass
        return lookup

    def _start_check(self):
        device_ids = self._collect_device_ids()

        if not device_ids:
            QMessageBox.warning(
                self,
                "Nessun Dispositivo",
                "Nessun DeviceID da verificare. Seleziona una sorgente valida."
            )
            return

        # Deduplica preservando l'ordine
        seen = set()
        unique_ids = []
        for did in device_ids:
            if did not in seen:
                seen.add(did)
                unique_ids.append(did)

        reply = QMessageBox.question(
            self,
            "Conferma",
            f"Avviare il check 'Primo dato MongoDB' su {len(unique_ids)} dispositivi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        # Prepara UI
        self.results = []
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.progress_bar.setMaximum(len(unique_ids))
        self.progress_bar.setValue(0)
        self.stats_label.setText("OK: 0 | KO: 0")

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.export_btn.setEnabled(False)

        # Lookup anagrafica per arricchimento
        self._lookup = self._build_anagrafica_lookup()
        self._device_order = unique_ids

        # Pre-popola la tabella con "In attesa"
        waiting_color = QColor("#FFF3CD")
        for did in unique_ids:
            row = self.table.rowCount()
            self.table.insertRow(row)
            info = self._lookup.get(did)

            sostegno = info.sostegno if info else "-"
            vendor = info.vendor.value if info else "-"
            tipo = info.device_type.value if info else "-"
            data_inst = (
                info.data_installazione.strftime("%d/%m/%Y")
                if info and info.data_installazione else "-"
            )

            cells = [sostegno, did, data_inst, vendor, tipo, "⏳ In coda", "-"]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(waiting_color)
                if col == 1:
                    item.setData(Qt.UserRole, did)
                self.table.setItem(row, col, item)

        self._log(f"Avvio check su {len(unique_ids)} dispositivi...", "INFO")

        self.worker = FirstArrivalWorker(unique_ids)
        self.worker.progress_signal.connect(self._on_progress)
        self.worker.result_signal.connect(self._on_result)
        self.worker.phase_signal.connect(self._on_phase)
        self.worker.completed_signal.connect(self._on_completed)
        self.worker.error_signal.connect(self._on_error)
        self.worker.start()

    def _stop_check(self):
        if self.worker:
            self.worker.stop()
            self._log("Interruzione richiesta…", "WARNING")
            self.stop_btn.setEnabled(False)

    def _on_phase(self, message: str):
        self._log(f"📌 {message}", "INFO")

    def _on_progress(self, current: int, total: int, device_id: str):
        self.progress_bar.setValue(current)
        # Marca la riga come "in corso"
        testing_color = QColor("#CCE5FF")
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.data(Qt.UserRole) == device_id:
                for col in range(self.table.columnCount()):
                    cell = self.table.item(row, col)
                    if cell:
                        cell.setBackground(testing_color)
                status_cell = self.table.item(row, 5)
                if status_cell:
                    status_cell.setText("🔄 Test…")
                break

    def _on_result(self, device_id: str, result: dict):
        has_data = result.get("has_data", False)
        last_ts = result.get("last_timestamp")
        last_recv = result.get("last_received_on")
        error = result.get("error", "")

        if has_data:
            value = last_ts.strftime("%Y-%m-%d %H:%M:%S") if last_ts else "-"
            received_str = last_recv.strftime("%Y-%m-%d %H:%M:%S") if last_recv else "-"
            color = QColor("#C6EFCE")
            is_ko = False
        else:
            if error:
                self._log(f"{device_id}: errore → {error}", "ERROR")
            value = "KO"
            received_str = "-"
            color = QColor("#FFC7CE")
            is_ko = True

        info = self._lookup.get(device_id)
        sostegno = info.sostegno if info else "-"
        vendor = info.vendor.value if info else "-"
        tipo = info.device_type.value if info else "-"
        data_inst = (
            info.data_installazione.strftime("%d/%m/%Y")
            if info and info.data_installazione else "-"
        )

        self.results.append({
            "ST Sostegno": sostegno,
            "DeviceID": device_id,
            "Data Installazione": data_inst,
            "Vendor": vendor,
            "Tipo": tipo,
            "Check MongoDB": value,
            "Ultimo receivedOn": received_str
        })

        # Aggiorna riga
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.data(Qt.UserRole) == device_id:
                for col in range(self.table.columnCount()):
                    cell = self.table.item(row, col)
                    if cell:
                        cell.setBackground(color)
                status_cell = self.table.item(row, 5)
                if status_cell:
                    status_cell.setText(value)
                received_cell = self.table.item(row, 6)
                if received_cell:
                    received_cell.setText(received_str)
                break

        ok = sum(1 for r in self.results if r["Check MongoDB"] != "KO")
        ko = sum(1 for r in self.results if r["Check MongoDB"] == "KO")
        self.stats_label.setText(f"OK: {ok} | KO: {ko}")

    def _on_completed(self):
        self.table.setSortingEnabled(True)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.export_btn.setEnabled(bool(self.results))

        ok = sum(1 for r in self.results if r["Check MongoDB"] != "KO")
        ko = sum(1 for r in self.results if r["Check MongoDB"] == "KO")
        self._log(f"Check completato: {ok} OK, {ko} KO", "SUCCESS" if ko == 0 else "WARNING")

    def _on_error(self, message: str):
        self.table.setSortingEnabled(True)
        self._log(f"Errore: {message}", "ERROR")
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        QMessageBox.critical(self, "Errore", message)

    def _export(self):
        if not self.results:
            QMessageBox.warning(self, "Nessun risultato", "Nessun dato da esportare.")
            return

        default_name = f"DIGIL_LS_MongoDB_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva risultati",
            str(Path.home() / "Downloads" / default_name),
            "Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        success, result = self.result_exporter.export_first_arrival_results(
            self.results, file_path
        )
        if success:
            self._log(f"Esportato: {result}", "SUCCESS")
            reply = QMessageBox.question(
                self,
                "Esportazione completata",
                f"File salvato in:\n{result}\n\nAprire il file?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                import subprocess
                import platform
                import os as _os
                if platform.system() == 'Windows':
                    _os.startfile(result)
                elif platform.system() == 'Darwin':
                    subprocess.call(['open', result])
                else:
                    subprocess.call(['xdg-open', result])
        else:
            QMessageBox.critical(self, "Errore Esportazione", result)
            self._log(result, "ERROR")

    def _log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        color_map = {
            "INFO": "#CCCCCC",
            "SUCCESS": "#00CC00",
            "WARNING": "#FFCC00",
            "ERROR": "#FF6666"
        }
        color = color_map.get(level, "#CCCCCC")
        html = (
            f'<span style="color: #666666;">[{timestamp}]</span> '
            f'<span style="color: {color};">{message}</span>'
        )
        self.log_area.append(html)
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Check in corso",
                "Il check è ancora in esecuzione. Interrompere e chiudere?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.worker.stop()
                self.worker.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
