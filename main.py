"""
DIGIL Diagnostic Checker - Main GUI Application
================================================
Tool per verifica connettività e diagnostica avanzata dispositivi DIGIL
con interfaccia grafica professionale in stile Terna.

Versione: 2.0.0

Features:
- Check SSH/Ping (via macchina ponte)
- API Diagnostica (batteria, LTE, porta aperta)
- MongoDB 24h (verifica invio dati)
- Classificazione automatica malfunzionamenti
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional
import threading

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QProgressBar,
    QComboBox, QSpinBox, QGroupBox, QFileDialog, QMessageBox,
    QHeaderView, QAbstractItemView, QStatusBar, QFrame, QSplitter,
    QTextEdit, QCheckBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QPixmap, QColor

from connectivity_checker import (
    DeviceInfo, ConnectionStatus, DeviceType, Vendor,
    MultiThreadChecker, BridgeConnection
)
from data_handler import DataLoader, ResultExporter, update_monitoring_file


# Stile CSS Terna
TERNA_STYLE = """
/* Colori Terna */
/* Blu principale: #0066CC */
/* Blu scuro: #004C99 */
/* Azzurro chiaro: #E6F2FF */
/* Grigio: #F5F5F5 */

QMainWindow {
    background-color: #FFFFFF;
}

QWidget {
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}

/* Header e titoli */
QLabel#headerTitle {
    font-size: 24px;
    font-weight: bold;
    color: #0066CC;
}

QLabel#headerSubtitle {
    font-size: 12px;
    color: #666666;
}

/* Gruppi */
QGroupBox {
    font-weight: bold;
    border: 1px solid #CCCCCC;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    background-color: #FAFAFA;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #0066CC;
}

/* Bottoni */
QPushButton {
    background-color: #0066CC;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
    min-width: 100px;
}

QPushButton:hover {
    background-color: #004C99;
}

QPushButton:pressed {
    background-color: #003366;
}

QPushButton:disabled {
    background-color: #CCCCCC;
    color: #666666;
}

QPushButton#stopButton {
    background-color: #CC3300;
}

QPushButton#stopButton:hover {
    background-color: #992600;
}

QPushButton#exportButton {
    background-color: #009933;
}

QPushButton#exportButton:hover {
    background-color: #006622;
}

QPushButton#secondaryButton {
    background-color: #FFFFFF;
    color: #0066CC;
    border: 2px solid #0066CC;
}

QPushButton#secondaryButton:hover {
    background-color: #E6F2FF;
}

QPushButton#clearButton {
    background-color: #CC3300;
    min-width: 30px;
    padding: 8px;
}

QPushButton#clearButton:hover {
    background-color: #992600;
}

/* Tabella */
QTableWidget {
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    gridline-color: #E0E0E0;
    background-color: white;
    alternate-background-color: #F8FBFF;
}

QTableWidget::item {
    padding: 5px;
}

QTableWidget::item:selected {
    background-color: #CCE5FF;
    color: black;
}

QHeaderView::section {
    background-color: #0066CC;
    color: white;
    padding: 8px;
    border: none;
    font-weight: bold;
}

QHeaderView::section:hover {
    background-color: #004C99;
}

/* Progress Bar */
QProgressBar {
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    text-align: center;
    background-color: #F0F0F0;
    height: 25px;
}

QProgressBar::chunk {
    background-color: #0066CC;
    border-radius: 3px;
}

/* ComboBox */
QComboBox {
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    padding: 5px 10px;
    background-color: white;
    min-width: 150px;
}

QComboBox:hover {
    border-color: #0066CC;
}

QComboBox::drop-down {
    border: none;
    width: 30px;
}

/* SpinBox */
QSpinBox {
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    padding: 5px;
    background-color: white;
}

QSpinBox:hover {
    border-color: #0066CC;
}

/* Log area */
QTextEdit#logArea {
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    background-color: #1E1E1E;
    color: #CCCCCC;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
}

/* Status bar */
QStatusBar {
    background-color: #F5F5F5;
    border-top: 1px solid #CCCCCC;
}

/* Frame separatore */
QFrame#separator {
    background-color: #CCCCCC;
    max-height: 1px;
}

/* CheckBox */
QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
}

QCheckBox::indicator:unchecked {
    border: 2px solid #CCCCCC;
    border-radius: 3px;
    background-color: white;
}

QCheckBox::indicator:checked {
    border: 2px solid #0066CC;
    border-radius: 3px;
    background-color: #0066CC;
}
"""


class DiagnosticWorkerThread(QThread):
    """Thread worker per eseguire i test diagnostici completi"""
    
    progress_signal = pyqtSignal(object, str, int, int)  # device, message, current, total
    completed_signal = pyqtSignal(list)  # results
    error_signal = pyqtSignal(str)  # error message
    bridge_status_signal = pyqtSignal(object, str)  # connected (bool/None), message
    phase_signal = pyqtSignal(str)  # current phase description
    
    def __init__(self, devices: list, max_workers: int = 10,
                 check_ssh: bool = True, check_api: bool = True, check_mongodb: bool = True):
        super().__init__()
        self.devices = devices
        self.max_workers = max_workers
        self.check_ssh = check_ssh
        self.check_api = check_api
        self.check_mongodb = check_mongodb
        self.checker: Optional[MultiThreadChecker] = None
        self._stop_requested = False
        
    def run(self):
        try:
            # Fase 1: SSH/Ping
            if self.check_ssh:
                self.phase_signal.emit("Fase 1/3: Check SSH/Ping...")
                self.checker = MultiThreadChecker(max_workers=self.max_workers)
                
                def on_progress(device, message, current, total):
                    self.progress_signal.emit(device, message, current, total)
                
                def on_bridge_status(connected, message):
                    self.bridge_status_signal.emit(connected, message)
                
                results = self.checker.check_devices(
                    self.devices,
                    progress_callback=on_progress,
                    bridge_callback=on_bridge_status
                )
            else:
                results = self.devices
            
            # Fase 2: API Diagnostica
            if self.check_api and not self._stop_requested:
                self.phase_signal.emit("Fase 2/3: API Diagnostica...")
                self._run_api_checks(results)
            
            # Fase 3: MongoDB
            if self.check_mongodb and not self._stop_requested:
                self.phase_signal.emit("Fase 3/3: Check MongoDB 24h...")
                self._run_mongodb_checks(results)
            
            # Classificazione finale
            if not self._stop_requested:
                self.phase_signal.emit("Classificazione malfunzionamenti...")
                self._classify_malfunctions(results)
            
            self.completed_signal.emit(results)
            
        except Exception as e:
            self.error_signal.emit(str(e))
    
    def _run_api_checks(self, devices: list):
        """Esegue i check API per ogni dispositivo"""
        try:
            from api_client import DigilAPIClient
            api_client = DigilAPIClient()
            
            for i, device in enumerate(devices):
                if self._stop_requested:
                    break
                    
                self.progress_signal.emit(device, f"API check {i+1}/{len(devices)}...", i, len(devices))
                
                try:
                    api_result = api_client.get_device_diagnostics(device.device_id)
                    if api_result:
                        device.api_data = api_result
                        device.battery_ok = api_result.get('battery_ok', None)
                        device.door_open = api_result.get('door_open', None)
                        device.lte_ok = api_result.get('lte_ok', None)
                        device.soc_percent = api_result.get('soc_percent', None)
                        device.soh_percent = api_result.get('soh_percent', None)
                        device.lte_signal_dbm = api_result.get('lte_signal_dbm', None)
                        device.channel = api_result.get('channel', None)
                except Exception as e:
                    device.api_error = str(e)[:100]
                    
        except ImportError:
            # api_client non disponibile
            for device in devices:
                device.api_error = "api_client module not available"
    
    def _run_mongodb_checks(self, devices: list):
        """Esegue i check MongoDB per ogni dispositivo tramite SSH tunnel."""
        try:
            from mongodb_checker import MongoDBChecker, get_tunnel_manager, cleanup_tunnel
            
            # Usa il tunnel manager singleton
            tunnel_manager = get_tunnel_manager()
            
            # Avvia il tunnel SSH (una sola volta per tutti i device)
            self.phase_signal.emit("Fase 3/3: Avvio tunnel SSH verso MongoDB...")
            success, msg, port = tunnel_manager.start_tunnel()
            
            if not success:
                for device in devices:
                    device.mongodb_error = f"Tunnel SSH fallito: {msg}"
                return
            
            # Connetti a MongoDB attraverso il tunnel
            mongo_checker = MongoDBChecker(tunnel_manager)
            success, msg = mongo_checker.connect()
            
            if not success:
                for device in devices:
                    device.mongodb_error = f"Connessione MongoDB fallita: {msg}"
                return
            
            self.phase_signal.emit("Fase 3/3: Check MongoDB 24h in corso...")
            
            for i, device in enumerate(devices):
                if self._stop_requested:
                    break
                    
                self.progress_signal.emit(device, f"MongoDB check {i+1}/{len(devices)}...", i, len(devices))
                
                try:
                    mongo_result = mongo_checker.check_device(device.device_id)
                    device.mongodb_has_data = mongo_result.has_data_24h
                    device.mongodb_last_timestamp = mongo_result.last_timestamp
                    device.mongodb_checked = mongo_result.checked
                    if mongo_result.error:
                        device.mongodb_error = mongo_result.error
                except Exception as e:
                    device.mongodb_error = str(e)[:100]
            
            # Chiudi connessione MongoDB (ma mantieni tunnel per eventuali altri usi)
            mongo_checker.disconnect()
                    
        except ImportError as e:
            for device in devices:
                device.mongodb_error = f"Modulo non disponibile: {str(e)}"
    
    def _classify_malfunctions(self, devices: list):
        """Classifica i malfunzionamenti per ogni dispositivo"""
        try:
            from malfunction_classifier import MalfunctionClassifier
            classifier = MalfunctionClassifier()
            
            for device in devices:
                device.malfunction_type = classifier.classify(device)
        except ImportError:
            # Classificazione semplificata se il modulo non è disponibile
            for device in devices:
                device.malfunction_type = self._simple_classify(device)
    
    def _simple_classify(self, device) -> str:
        """Classificazione semplificata di fallback"""
        # SSH KO
        ssh_ok = device.ssh_status == ConnectionStatus.SSH_PORT_OPEN if hasattr(device, 'ssh_status') else None
        ping_ok = device.ping_status == ConnectionStatus.PING_OK if hasattr(device, 'ping_status') else None
        
        # API data
        battery_ok = getattr(device, 'battery_ok', None)
        door_open = getattr(device, 'door_open', None)
        lte_ok = getattr(device, 'lte_ok', None)
        
        # MongoDB
        mongodb_ok = getattr(device, 'mongodb_has_data', None)
        
        # Logica di classificazione
        if door_open == True:
            return "Porta aperta"
        if battery_ok == False:
            return "Allarme batteria"
        if not ssh_ok and not ping_ok:
            return "Disconnesso"
        if mongodb_ok == False and (ssh_ok or lte_ok):
            return "Metriche assenti"
        if ssh_ok and lte_ok and mongodb_ok:
            return "OK"
        if not lte_ok:
            return "Disconnesso"
        
        return "Non classificato"
    
    def stop(self):
        self._stop_requested = True
        if self.checker:
            self.checker.stop()


class MainWindow(QMainWindow):
    """Finestra principale dell'applicazione"""
    
    def __init__(self):
        super().__init__()
        
        self.data_loader = DataLoader()
        self.result_exporter = ResultExporter()
        self.worker_thread: Optional[DiagnosticWorkerThread] = None
        self.results: list = []
        
        self.init_ui()
        self.apply_style()
        
        # Prova a caricare il file di default
        QTimer.singleShot(100, self.auto_load_file)
        
        # Carica il logo Terna se presente
        QTimer.singleShot(50, self.auto_load_logo)
    
    def auto_load_logo(self):
        """Cerca e carica automaticamente il logo Terna dalla cartella assets"""
        # Possibili percorsi del logo
        script_dir = Path(__file__).parent
        possible_paths = [
            script_dir / "assets" / "logo_terna.png",
            script_dir / "assets" / "logo.png",
            script_dir / "assets" / "terna_logo.png",
            script_dir / "logo_terna.png",
            script_dir / "logo.png",
            Path.cwd() / "assets" / "logo_terna.png",
            Path.cwd() / "assets" / "logo.png",
        ]
        
        for logo_path in possible_paths:
            if logo_path.exists():
                try:
                    pixmap = QPixmap(str(logo_path))
                    if not pixmap.isNull():
                        self.logo_label.setPixmap(pixmap.scaled(120, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                        self.logo_label.setText("")
                        self.logo_label.setStyleSheet("background-color: transparent;")
                        self.log(f"Logo caricato: {logo_path.name}", "INFO")
                        return
                except Exception as e:
                    self.log(f"Errore caricamento logo: {e}", "WARNING")
        
        # Logo non trovato, mantieni il placeholder "T"
        self.log("Logo non trovato in assets/ - usando placeholder", "WARNING")
        
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        self.setWindowTitle("DIGIL Diagnostic Checker - Terna IoT Team")
        self.setMinimumSize(1400, 850)
        
        # Widget centrale
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Separatore
        separator = QFrame()
        separator.setObjectName("separator")
        separator.setFrameShape(QFrame.HLine)
        main_layout.addWidget(separator)
        
        # Area principale con splitter
        splitter = QSplitter(Qt.Vertical)
        
        # Parte superiore: controlli e tabella
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        # Controlli
        controls = self.create_controls()
        top_layout.addWidget(controls)
        
        # Progress
        progress_widget = self.create_progress_section()
        top_layout.addWidget(progress_widget)
        
        # Tabella risultati
        table_group = QGroupBox("Risultati Test Diagnostici")
        table_layout = QVBoxLayout(table_group)
        self.results_table = self.create_results_table()
        table_layout.addWidget(self.results_table)
        top_layout.addWidget(table_group, stretch=1)
        
        splitter.addWidget(top_widget)
        
        # Parte inferiore: log
        log_group = QGroupBox("Log Operazioni")
        log_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit()
        self.log_area.setObjectName("logArea")
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        log_layout.addWidget(self.log_area)
        splitter.addWidget(log_group)
        
        splitter.setSizes([600, 150])
        main_layout.addWidget(splitter, stretch=1)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Pronto")
        self.status_bar.addWidget(self.status_label, stretch=1)
        
        self.device_count_label = QLabel("Dispositivi: 0")
        self.status_bar.addPermanentWidget(self.device_count_label)
        
    def create_header(self) -> QWidget:
        """Crea l'header con logo e titolo"""
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 10)
        
        # Logo placeholder (sarà sostituito con logo Terna)
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(120, 50)
        self.logo_label.setStyleSheet("""
            background-color: #0066CC;
            border-radius: 8px;
            color: white;
            font-size: 24px;
            font-weight: bold;
        """)
        self.logo_label.setText("T")
        self.logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.logo_label)
        
        # Titoli
        title_widget = QWidget()
        title_layout = QVBoxLayout(title_widget)
        title_layout.setContentsMargins(15, 0, 0, 0)
        title_layout.setSpacing(2)
        
        title = QLabel("DIGIL Diagnostic Checker")
        title.setObjectName("headerTitle")
        title_layout.addWidget(title)
        
        subtitle = QLabel("Verifica connettività e diagnostica IoT - Terna S.p.A.")
        subtitle.setObjectName("headerSubtitle")
        title_layout.addWidget(subtitle)
        
        layout.addWidget(title_widget)
        layout.addStretch()
        
        # Info versione
        version_label = QLabel("v2.0.0")
        version_label.setStyleSheet("color: #999999; font-size: 11px;")
        layout.addWidget(version_label)
        
        return header
    
    def create_controls(self) -> QWidget:
        """Crea i controlli per filtri e azioni"""
        controls = QGroupBox("Configurazione Test")
        main_layout = QVBoxLayout(controls)
        main_layout.setSpacing(15)
        
        # === RIGA 1: File Anagrafica e Lista Test ===
        files_layout = QHBoxLayout()
        files_layout.setSpacing(20)
        
        # File Anagrafica (Monitoraggio)
        anagrafica_layout = QVBoxLayout()
        anagrafica_label = QLabel("📁 File Anagrafica:")
        anagrafica_label.setStyleSheet("font-weight: bold;")
        anagrafica_layout.addWidget(anagrafica_label)
        
        anagrafica_btn_layout = QHBoxLayout()
        self.file_path_label = QLabel("Nessun file caricato")
        self.file_path_label.setStyleSheet("color: #666666; font-style: italic;")
        anagrafica_btn_layout.addWidget(self.file_path_label, stretch=1)
        
        self.load_file_btn = QPushButton("Carica")
        self.load_file_btn.setObjectName("secondaryButton")
        self.load_file_btn.clicked.connect(self.load_file)
        anagrafica_btn_layout.addWidget(self.load_file_btn)
        
        anagrafica_layout.addLayout(anagrafica_btn_layout)
        files_layout.addLayout(anagrafica_layout, stretch=1)
        
        # Separatore verticale
        v_sep = QFrame()
        v_sep.setFrameShape(QFrame.VLine)
        v_sep.setStyleSheet("color: #CCCCCC;")
        files_layout.addWidget(v_sep)
        
        # File Lista Test
        test_list_layout = QVBoxLayout()
        test_list_label = QLabel("📋 Lista Dispositivi Test:")
        test_list_label.setStyleSheet("font-weight: bold;")
        test_list_layout.addWidget(test_list_label)
        
        test_list_btn_layout = QHBoxLayout()
        self.test_list_label = QLabel("Nessuna lista (testerà tutti)")
        self.test_list_label.setStyleSheet("color: #666666; font-style: italic;")
        test_list_btn_layout.addWidget(self.test_list_label, stretch=1)
        
        self.load_test_list_btn = QPushButton("Carica Lista")
        self.load_test_list_btn.setObjectName("secondaryButton")
        self.load_test_list_btn.clicked.connect(self.load_test_list)
        test_list_btn_layout.addWidget(self.load_test_list_btn)
        
        self.clear_test_list_btn = QPushButton("✕")
        self.clear_test_list_btn.setObjectName("clearButton")
        self.clear_test_list_btn.setFixedWidth(35)
        self.clear_test_list_btn.setToolTip("Rimuovi lista test")
        self.clear_test_list_btn.clicked.connect(self.clear_test_list)
        self.clear_test_list_btn.setVisible(False)
        test_list_btn_layout.addWidget(self.clear_test_list_btn)
        
        test_list_layout.addLayout(test_list_btn_layout)
        files_layout.addLayout(test_list_layout, stretch=1)
        
        main_layout.addLayout(files_layout)
        
        # Separatore orizzontale
        h_sep = QFrame()
        h_sep.setFrameShape(QFrame.HLine)
        h_sep.setStyleSheet("color: #E0E0E0;")
        main_layout.addWidget(h_sep)
        
        # === RIGA 2: Filtri, Check da eseguire, Opzioni e Azioni ===
        options_layout = QHBoxLayout()
        options_layout.setSpacing(20)
        
        # Filtri
        filter_layout = QVBoxLayout()
        filter_label = QLabel("Filtri:")
        filter_label.setStyleSheet("font-weight: bold;")
        filter_layout.addWidget(filter_label)
        
        filter_row = QHBoxLayout()
        
        filter_row.addWidget(QLabel("Vendor:"))
        self.vendor_combo = QComboBox()
        self.vendor_combo.addItems(["Tutti", "INDRA", "SIRTI", "MII"])
        filter_row.addWidget(self.vendor_combo)
        
        filter_row.addSpacing(10)
        
        filter_row.addWidget(QLabel("Tipo:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Tutti", "Master", "Slave"])
        filter_row.addWidget(self.type_combo)
        
        filter_layout.addLayout(filter_row)
        options_layout.addLayout(filter_layout, stretch=1)
        
        # Separatore verticale
        v_sep2 = QFrame()
        v_sep2.setFrameShape(QFrame.VLine)
        v_sep2.setStyleSheet("color: #CCCCCC;")
        options_layout.addWidget(v_sep2)
        
        # Check da eseguire
        checks_layout = QVBoxLayout()
        checks_label = QLabel("Check da eseguire:")
        checks_label.setStyleSheet("font-weight: bold;")
        checks_layout.addWidget(checks_label)
        
        checks_row = QHBoxLayout()
        
        self.check_ssh = QCheckBox("SSH/Ping")
        self.check_ssh.setChecked(True)
        self.check_ssh.setEnabled(False)  # Sempre attivo
        checks_row.addWidget(self.check_ssh)
        
        self.check_api = QCheckBox("API Diagnostica")
        self.check_api.setChecked(True)
        checks_row.addWidget(self.check_api)
        
        self.check_mongodb = QCheckBox("MongoDB (24h)")
        self.check_mongodb.setChecked(True)
        checks_row.addWidget(self.check_mongodb)
        
        checks_layout.addLayout(checks_row)
        options_layout.addLayout(checks_layout, stretch=1)
        
        # Separatore verticale
        v_sep3 = QFrame()
        v_sep3.setFrameShape(QFrame.VLine)
        v_sep3.setStyleSheet("color: #CCCCCC;")
        options_layout.addWidget(v_sep3)
        
        # Opzioni test
        thread_layout = QVBoxLayout()
        thread_label = QLabel("Opzioni:")
        thread_label.setStyleSheet("font-weight: bold;")
        thread_layout.addWidget(thread_label)
        
        thread_row = QHBoxLayout()
        thread_row.addWidget(QLabel("Thread:"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 50)
        self.threads_spin.setValue(10)
        self.threads_spin.setToolTip("Numero di test eseguiti contemporaneamente")
        thread_row.addWidget(self.threads_spin)
        
        thread_layout.addLayout(thread_row)
        options_layout.addLayout(thread_layout, stretch=0)
        
        # Separatore verticale
        v_sep4 = QFrame()
        v_sep4.setFrameShape(QFrame.VLine)
        v_sep4.setStyleSheet("color: #CCCCCC;")
        options_layout.addWidget(v_sep4)
        
        # Bottoni azione
        action_layout = QVBoxLayout()
        action_label = QLabel("Azioni:")
        action_label.setStyleSheet("font-weight: bold;")
        action_layout.addWidget(action_label)
        
        action_btn_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("▶ Avvia Test")
        self.start_btn.clicked.connect(self.start_test)
        action_btn_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("■ Stop")
        self.stop_btn.setObjectName("stopButton")
        self.stop_btn.clicked.connect(self.stop_test)
        self.stop_btn.setEnabled(False)
        action_btn_layout.addWidget(self.stop_btn)
        
        action_layout.addLayout(action_btn_layout)
        options_layout.addLayout(action_layout, stretch=1)
        
        main_layout.addLayout(options_layout)
        
        return controls
    
    def create_progress_section(self) -> QWidget:
        """Crea la sezione progress"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 5, 0, 5)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m (%p%)")
        layout.addWidget(self.progress_bar, stretch=3)
        
        # Stats in tempo reale
        self.stats_label = QLabel("OK: 0 | KO: 0")
        self.stats_label.setStyleSheet("color: #666666; margin-left: 20px;")
        layout.addWidget(self.stats_label)
        
        # Bottone export
        self.export_btn = QPushButton("📥 Esporta Excel")
        self.export_btn.setObjectName("exportButton")
        self.export_btn.clicked.connect(self.export_results)
        self.export_btn.setEnabled(False)
        layout.addWidget(self.export_btn)
        
        return widget
    
    def create_results_table(self) -> QTableWidget:
        """Crea la tabella risultati con colonne diagnostiche"""
        table = QTableWidget()
        
        # Colonne estese per diagnostica
        columns = [
            "Stato", "Linea", "Sostegno", "DeviceID", "IP",
            "Vendor", "Tipo", "MongoDB", "LTE", "SSH",
            "Batteria", "Porta", "Malfunzionamento", "Note"
        ]
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        
        # Configurazione
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setSortingEnabled(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Header
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Fixed)  # Stato
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # DeviceID
        
        # Larghezze colonne
        table.setColumnWidth(0, 50)   # Stato
        table.setColumnWidth(1, 80)   # Linea
        table.setColumnWidth(2, 140)  # Sostegno
        table.setColumnWidth(3, 200)  # DeviceID
        table.setColumnWidth(4, 110)  # IP
        table.setColumnWidth(5, 55)   # Vendor
        table.setColumnWidth(6, 55)   # Tipo
        table.setColumnWidth(7, 65)   # MongoDB
        table.setColumnWidth(8, 45)   # LTE
        table.setColumnWidth(9, 45)   # SSH
        table.setColumnWidth(10, 60)  # Batteria
        table.setColumnWidth(11, 50)  # Porta
        table.setColumnWidth(12, 130) # Malfunzionamento
        
        return table
    
    def apply_style(self):
        """Applica lo stile CSS"""
        self.setStyleSheet(TERNA_STYLE)
    
    def log(self, message: str, level: str = "INFO"):
        """Aggiunge un messaggio al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        color_map = {
            "INFO": "#CCCCCC",
            "SUCCESS": "#00CC00",
            "WARNING": "#FFCC00",
            "ERROR": "#FF6666"
        }
        color = color_map.get(level, "#CCCCCC")
        
        html = f'<span style="color: #666666;">[{timestamp}]</span> <span style="color: {color};">{message}</span>'
        self.log_area.append(html)
        
        # Auto-scroll
        scrollbar = self.log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def auto_load_file(self):
        """Tenta di caricare automaticamente il file di monitoraggio"""
        # Prova prima nella directory del progetto
        project_file = Path("/mnt/project/Monitoraggio_APPARATI_DIGIL_INSTALLATI.xlsx")
        if project_file.exists():
            success, msg, count = self.data_loader.load_file(str(project_file))
            if success:
                self.update_file_info()
                self.log(f"File caricato automaticamente: {count} dispositivi", "SUCCESS")
                return
        
        # Prova nella directory data
        self.data_loader.data_dir = Path(__file__).parent / "data"
        file_path = self.data_loader.find_monitoring_file()
        
        if file_path:
            success, msg, count = self.data_loader.load_file(str(file_path))
            if success:
                self.update_file_info()
                self.log(f"File caricato: {count} dispositivi", "SUCCESS")
            else:
                self.log(f"Errore caricamento: {msg}", "ERROR")
        else:
            self.log("File di monitoraggio non trovato. Caricalo manualmente.", "WARNING")
    
    def load_file(self):
        """Dialog per caricare il file di monitoraggio"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona File Monitoraggio DIGIL",
            "",
            "Excel Files (*.xlsx *.xls);;All Files (*)"
        )
        
        if file_path:
            success, msg, count = self.data_loader.load_file(file_path)
            
            if success:
                self.update_file_info()
                self.log(f"File caricato: {count} dispositivi", "SUCCESS")
            else:
                QMessageBox.warning(self, "Errore", msg)
                self.log(msg, "ERROR")
    
    def update_file_info(self):
        """Aggiorna le info del file caricato"""
        summary = self.data_loader.get_summary()
        
        if summary.get("loaded"):
            file_name = Path(summary["file"]).name
            self.file_path_label.setText(f"✓ {file_name}")
            self.file_path_label.setStyleSheet("color: #009933;")
            
            # Info dispositivi
            total_anagrafica = summary.get('total_in_anagrafica', summary['total_devices'])
            total_test = summary['total_devices']
            
            if summary.get('test_list_loaded'):
                self.device_count_label.setText(
                    f"Da testare: {total_test} / {total_anagrafica} | "
                    f"INDRA: {summary['by_vendor'].get('INDRA', 0)} | "
                    f"SIRTI: {summary['by_vendor'].get('SIRTI', 0)} | "
                    f"MII: {summary['by_vendor'].get('MII', 0)}"
                )
            else:
                self.device_count_label.setText(
                    f"Dispositivi: {total_anagrafica} | "
                    f"INDRA: {summary['by_vendor'].get('INDRA', 0)} | "
                    f"SIRTI: {summary['by_vendor'].get('SIRTI', 0)} | "
                    f"MII: {summary['by_vendor'].get('MII', 0)}"
                )
        else:
            self.file_path_label.setText("Nessun file caricato")
            self.file_path_label.setStyleSheet("color: #666666; font-style: italic;")
    
    def load_test_list(self):
        """Dialog per caricare la lista dei dispositivi da testare"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleziona Lista Dispositivi da Testare",
            "",
            "Excel Files (*.xlsx *.xls);;CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_path:
            return
        
        success, msg, count = self.data_loader.load_test_list(
            file_path, 
            device_id_column=0,
            has_header=False
        )
        
        if success:
            self.test_list_label.setText(f"✓ {Path(file_path).name} ({count})")
            self.test_list_label.setStyleSheet("color: #009933;")
            self.clear_test_list_btn.setVisible(True)
            self.log(f"Lista test caricata: {count} dispositivi", "SUCCESS")
            
            summary = self.data_loader.get_summary()
            if summary.get('not_found_count', 0) > 0:
                not_found = summary['not_found_in_anagrafica']
                self.log(f"Attenzione: {len(not_found)} DeviceID non trovati in anagrafica", "WARNING")
            
            self.update_file_info()
        else:
            QMessageBox.warning(self, "Errore", msg)
            self.log(msg, "ERROR")
    
    def clear_test_list(self):
        """Rimuove la lista test caricata"""
        self.data_loader.clear_test_list()
        self.test_list_label.setText("Nessuna lista (testerà tutti)")
        self.test_list_label.setStyleSheet("color: #666666; font-style: italic;")
        self.clear_test_list_btn.setVisible(False)
        self.update_file_info()
        self.log("Lista test rimossa", "INFO")
    
    def get_filtered_devices(self) -> list:
        """Ottiene i dispositivi filtrati"""
        vendor_filter = self.vendor_combo.currentText()
        if vendor_filter == "Tutti":
            vendor_filter = None
        
        type_filter = self.type_combo.currentText().lower()
        if type_filter == "tutti":
            type_filter = None
        
        return self.data_loader.get_devices(
            filter_vendor=vendor_filter,
            filter_type=type_filter
        )
    
    def start_test(self):
        """Avvia i test diagnostici"""
        devices = self.get_filtered_devices()
        
        if not devices:
            QMessageBox.warning(
                self,
                "Nessun Dispositivo",
                "Nessun dispositivo da testare. Carica un file di monitoraggio."
            )
            return
        
        # Conferma
        checks = []
        if self.check_ssh.isChecked():
            checks.append("SSH/Ping")
        if self.check_api.isChecked():
            checks.append("API Diagnostica")
        if self.check_mongodb.isChecked():
            checks.append("MongoDB 24h")
        
        reply = QMessageBox.question(
            self,
            "Conferma Avvio Test",
            f"Avviare i test diagnostici per {len(devices)} dispositivi?\n\n"
            f"Check attivi: {', '.join(checks)}\n"
            f"Thread paralleli: {self.threads_spin.value()}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply != QMessageBox.Yes:
            return
        
        # Prepara UI
        self.results = []
        self.results_table.setRowCount(0)
        self.progress_bar.setMaximum(len(devices))
        self.progress_bar.setValue(0)
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.export_btn.setEnabled(False)
        self.load_file_btn.setEnabled(False)
        
        self.log(f"Avvio test diagnostici per {len(devices)} dispositivi...", "INFO")
        
        # Popola tabella con stato "In attesa"
        for device in devices:
            self.add_device_to_table(device)
        
        # Avvia worker thread
        self.worker_thread = DiagnosticWorkerThread(
            devices, 
            self.threads_spin.value(),
            check_ssh=self.check_ssh.isChecked(),
            check_api=self.check_api.isChecked(),
            check_mongodb=self.check_mongodb.isChecked()
        )
        self.worker_thread.progress_signal.connect(self.on_progress)
        self.worker_thread.completed_signal.connect(self.on_completed)
        self.worker_thread.error_signal.connect(self.on_error)
        self.worker_thread.bridge_status_signal.connect(self.on_bridge_status)
        self.worker_thread.phase_signal.connect(self.on_phase_change)
        self.worker_thread.start()
    
    def on_phase_change(self, phase: str):
        """Callback per cambio fase"""
        self.log(f"📌 {phase}", "INFO")
        self.status_label.setText(phase)
    
    def on_bridge_status(self, connected, message: str):
        """Callback per stato connessione macchina ponte"""
        if connected is None:
            self.log(f"🔌 {message}", "INFO")
            self.status_label.setText("Connessione al ponte...")
        elif connected:
            self.log(f"✅ PONTE CONNESSO: {message}", "SUCCESS")
            self.status_label.setText("Ponte connesso - Avvio test...")
        else:
            self.log(f"❌ PONTE NON RAGGIUNGIBILE: {message}", "ERROR")
            self.status_label.setText(f"Errore: {message}")
    
    def stop_test(self):
        """Ferma i test in corso"""
        if self.worker_thread:
            self.worker_thread.stop()
            self.log("Interruzione richiesta...", "WARNING")
            self.stop_btn.setEnabled(False)
    
    def add_device_to_table(self, device):
        """Aggiunge un dispositivo alla tabella con stato 'In attesa' (arancione)"""
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        
        # Colore arancione per "in attesa"
        waiting_color = QColor("#FFF3CD")  # Arancione chiaro
        
        # Stato
        status_item = QTableWidgetItem("⏳")
        status_item.setTextAlignment(Qt.AlignCenter)
        status_item.setBackground(waiting_color)
        self.results_table.setItem(row, 0, status_item)
        
        # Dati base - tutti con sfondo arancione
        items_data = [
            device.linea,
            device.sostegno, 
            device.device_id,
            device.ip_address,
            device.vendor.value,
            device.device_type.value
        ]
        
        for col, text in enumerate(items_data, start=1):
            item = QTableWidgetItem(text)
            item.setBackground(waiting_color)
            self.results_table.setItem(row, col, item)
        
        # Colonne diagnostiche (vuote inizialmente) - tutte arancione
        for col in range(7, 14):
            item = QTableWidgetItem("-")
            item.setBackground(waiting_color)
            self.results_table.setItem(row, col, item)
        
        # Salva riferimento al device_id
        status_item.setData(Qt.UserRole, device.device_id)
    
    def set_device_testing(self, device_id: str, phase: str = ""):
        """Imposta un dispositivo come 'in corso di test' (blu)"""
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item and item.data(Qt.UserRole) == device_id:
                testing_color = QColor("#CCE5FF")  # Blu chiaro
                item.setText("🔄")
                
                # Colora tutta la riga blu
                for col in range(self.results_table.columnCount()):
                    cell = self.results_table.item(row, col)
                    if cell:
                        cell.setBackground(testing_color)
                
                # Mostra la fase corrente nella colonna Note (ultima colonna)
                note_col = self.results_table.columnCount() - 1
                note_item = self.results_table.item(row, note_col)
                if note_item and phase:
                    note_item.setText(phase)
                
                break
    
    def update_device_in_table(self, device):
        """Aggiorna lo stato di un dispositivo nella tabella"""
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item and item.data(Qt.UserRole) == device.device_id:
                # Determina stato generale
                ssh_ok = device.ssh_status == ConnectionStatus.SSH_PORT_OPEN if hasattr(device, 'ssh_status') else None
                mongodb_ok = getattr(device, 'mongodb_has_data', None)
                lte_ok = getattr(device, 'lte_ok', None)
                battery_ok = getattr(device, 'battery_ok', None)
                door_open = getattr(device, 'door_open', None)
                malfunction = getattr(device, 'malfunction_type', '')
                
                # Icona stato
                if malfunction == "OK":
                    status = "✅"
                    status_color = QColor("#C6EFCE")
                elif malfunction in ["Disconnesso", "Allarme batteria"]:
                    status = "❌"
                    status_color = QColor("#FFC7CE")
                elif mongodb_ok == False or lte_ok == False:
                    status = "⚠️"
                    status_color = QColor("#FFEB9C")
                elif ssh_ok:
                    status = "✅"
                    status_color = QColor("#C6EFCE")
                else:
                    status = "❌"
                    status_color = QColor("#FFC7CE")
                
                item.setText(status)
                
                # Colora riga
                for col in range(self.results_table.columnCount()):
                    cell = self.results_table.item(row, col)
                    if cell:
                        cell.setBackground(status_color)
                
                # Aggiorna colonne diagnostiche
                # MongoDB
                if mongodb_ok is True:
                    ts = getattr(device, 'mongodb_last_timestamp', None)
                    mongo_text = ts.strftime("%d/%m/%Y %H:%M") if ts else "Data"
                elif mongodb_ok is False:
                    mongo_text = "KO"
                else:
                    mongo_error = getattr(device, 'mongodb_error', '')
                    mongo_text = mongo_error[:15] if mongo_error else "-"
                self.results_table.item(row, 7).setText(mongo_text)
                
                # LTE
                lte_text = "OK" if lte_ok else ("KO" if lte_ok is False else "0")
                self.results_table.item(row, 8).setText(lte_text)
                
                # SSH
                ssh_text = "OK" if ssh_ok else ("KO" if ssh_ok is False else "-")
                self.results_table.item(row, 9).setText(ssh_text)
                
                # Batteria
                battery_text = "OK" if battery_ok else ("KO" if battery_ok is False else "-")
                self.results_table.item(row, 10).setText(battery_text)
                
                # Porta
                door_text = "KO" if door_open else ("OK" if door_open is False else "-")
                self.results_table.item(row, 11).setText(door_text)
                
                # Malfunzionamento
                self.results_table.item(row, 12).setText(malfunction if malfunction else "-")
                
                # Note
                errors = []
                if hasattr(device, 'error_message') and device.error_message:
                    errors.append(device.error_message)
                if hasattr(device, 'api_error') and device.api_error:
                    errors.append(device.api_error)
                if hasattr(device, 'mongodb_error') and device.mongodb_error:
                    errors.append(device.mongodb_error)
                self.results_table.item(row, 13).setText("; ".join(errors)[:50] if errors else "")
                
                break
    
    def on_progress(self, device, message: str, current: int, total: int):
        """Callback progresso - mostra cosa sta facendo il tool"""
        self.progress_bar.setValue(current)
        
        # Se il messaggio indica che il test è "in corso", colora la riga blu
        # Se è "Completato" o contiene risultati finali, aggiorna normalmente
        if "Completato" in message or device.test_timestamp:
            self.update_device_in_table(device)
        else:
            # Test in corso - colora blu e mostra fase
            self.set_device_testing(device.device_id, message[:30] if message else "Testing...")
        
        # Aggiorna statistiche
        ok_count = sum(1 for r in self.results if getattr(r, 'malfunction_type', '') == "OK")
        ko_count = sum(1 for r in self.results if getattr(r, 'malfunction_type', '') and getattr(r, 'malfunction_type', '') != "OK")
        in_progress = total - len(self.results)
        
        self.stats_label.setText(f"OK: {ok_count} | KO: {ko_count} | In corso: {in_progress}")
        self.status_label.setText(f"{message[:50]}..." if len(message) > 50 else message)
    
    def on_completed(self, results: list):
        """Callback completamento"""
        self.results = results
        
        for device in results:
            self.update_device_in_table(device)
        
        # Ripristina UI
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.export_btn.setEnabled(True)
        self.load_file_btn.setEnabled(True)
        
        # Statistiche finali
        ok_count = sum(1 for r in results if getattr(r, 'malfunction_type', '') == "OK")
        ko_count = len(results) - ok_count
        
        self.status_label.setText(f"Completato: {ok_count} OK, {ko_count} problemi su {len(results)} dispositivi")
        self.log(f"Test completato: {ok_count} OK, {ko_count} problemi", "SUCCESS" if ko_count == 0 else "WARNING")
        
        QMessageBox.information(
            self,
            "Test Completato",
            f"Test completato per {len(results)} dispositivi.\n\n"
            f"✅ OK: {ok_count}\n"
            f"❌ Problemi: {ko_count}\n\n"
            "Usa 'Esporta Excel' per salvare i risultati."
        )
    
    def on_error(self, error_message: str):
        """Callback errore"""
        self.log(f"Errore: {error_message}", "ERROR")
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.load_file_btn.setEnabled(True)
        
        QMessageBox.critical(self, "Errore", f"Errore durante i test:\n\n{error_message}")
    
    def export_results(self):
        """Esporta i risultati in Excel"""
        if not self.results:
            QMessageBox.warning(self, "Nessun Risultato", "Nessun risultato da esportare.")
            return
        
        default_name = f"DIGIL_Diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva Risultati",
            str(Path.home() / "Downloads" / default_name),
            "Excel Files (*.xlsx)"
        )
        
        if file_path:
            success, result = self.result_exporter.export_diagnostic_results(self.results, file_path)
            
            if success:
                self.log(f"Risultati esportati: {result}", "SUCCESS")
                
                reply = QMessageBox.question(
                    self,
                    "Esportazione Completata",
                    f"File salvato in:\n{result}\n\nAprire il file?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                
                if reply == QMessageBox.Yes:
                    import subprocess
                    import platform
                    
                    if platform.system() == 'Windows':
                        os.startfile(result)
                    elif platform.system() == 'Darwin':
                        subprocess.call(['open', result])
                    else:
                        subprocess.call(['xdg-open', result])
            else:
                QMessageBox.critical(self, "Errore Esportazione", result)
                self.log(result, "ERROR")
    
    def closeEvent(self, event):
        """Gestisce la chiusura dell'applicazione"""
        if self.worker_thread and self.worker_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Test in Corso",
                "Ci sono test in corso. Vuoi interromperli e uscire?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.worker_thread.stop()
                self.worker_thread.wait(5000)
                self._cleanup_resources()
                event.accept()
            else:
                event.ignore()
        else:
            self._cleanup_resources()
            event.accept()
    
    def _cleanup_resources(self):
        """Pulisce le risorse (tunnel SSH, connessioni, ecc.)"""
        try:
            from mongodb_checker import cleanup_tunnel
            cleanup_tunnel()
            self.log("Tunnel SSH chiuso", "INFO")
        except:
            pass


def main():
    """Entry point dell'applicazione"""
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("DIGIL Diagnostic Checker")
    app.setOrganizationName("Terna")
    
    # Icona (se disponibile)
    icon_path = Path(__file__).parent / "assets" / "icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()