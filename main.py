"""
DIGIL SSH Checker - Main GUI Application
========================================
Tool per verificare la raggiungibilità SSH dei dispositivi DIGIL
con interfaccia grafica professionale in stile Terna.

Versione: 1.0.0
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
    QTextEdit, QCheckBox, QTabWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QIcon, QPixmap, QFont, QColor, QPalette, QBrush

from connectivity_checker import (
    DeviceInfo, ConnectionStatus, DeviceType, Vendor,
    MultiThreadChecker
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

QComboBox::down-arrow {
    width: 12px;
    height: 12px;
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

/* Tab Widget */
QTabWidget::pane {
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    background-color: white;
}

QTabBar::tab {
    background-color: #F0F0F0;
    border: 1px solid #CCCCCC;
    padding: 8px 16px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #0066CC;
    color: white;
}

QTabBar::tab:hover:!selected {
    background-color: #E6F2FF;
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


class WorkerThread(QThread):
    """Thread worker per eseguire i test senza bloccare la GUI"""
    
    progress_signal = pyqtSignal(object, str, int, int)  # device, message, current, total
    completed_signal = pyqtSignal(list)  # results
    error_signal = pyqtSignal(str)  # error message
    bridge_status_signal = pyqtSignal(object, str)  # connected (bool/None), message
    
    def __init__(self, devices: list[DeviceInfo], max_workers: int = 10):
        super().__init__()
        self.devices = devices
        self.max_workers = max_workers
        self.checker: Optional[MultiThreadChecker] = None
        self._stop_requested = False
        
    def run(self):
        try:
            self.checker = MultiThreadChecker(max_workers=self.max_workers)
            
            def on_progress(device, message, current, total):
                self.progress_signal.emit(device, message, current, total)
            
            def on_complete(results):
                self.completed_signal.emit(results)
            
            def on_bridge_status(connected, message):
                self.bridge_status_signal.emit(connected, message)
            
            # Esegue i test
            self.checker.check_devices(
                self.devices,
                progress_callback=on_progress,
                completion_callback=on_complete,
                bridge_callback=on_bridge_status
            )
            
        except Exception as e:
            self.error_signal.emit(str(e))
    
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
        self.worker_thread: Optional[WorkerThread] = None
        self.results: list[DeviceInfo] = []
        
        self.init_ui()
        self.apply_style()
        
        # Prova a caricare il file di default
        QTimer.singleShot(100, self.auto_load_file)
        
        # Carica il logo Terna se presente
        self.auto_load_logo()
    
    def auto_load_logo(self):
        """Cerca e carica automaticamente il logo Terna"""
        # Possibili percorsi del logo
        possible_paths = [
            Path(__file__).parent / "assets" / "logo_terna.png",
            Path(__file__).parent / "assets" / "logo.png",
            Path(__file__).parent / "logo_terna.png",
            Path(__file__).parent / "logo.png",
            Path.cwd() / "assets" / "logo_terna.png",
            Path.cwd() / "assets" / "logo.png",
        ]
        
        for logo_path in possible_paths:
            if logo_path.exists():
                self.load_logo(str(logo_path))
                self.log(f"Logo caricato: {logo_path.name}", "INFO")
                return
        
        # Logo non trovato, mantieni il placeholder "T"
        pass
        
    def init_ui(self):
        """Inizializza l'interfaccia utente"""
        self.setWindowTitle("DIGIL SSH Connectivity Checker - Terna IoT Team")
        self.setMinimumSize(1200, 800)
        
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
        table_group = QGroupBox("Risultati Test")
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
        
        title = QLabel("DIGIL SSH Connectivity Checker")
        title.setObjectName("headerTitle")
        title_layout.addWidget(title)
        
        subtitle = QLabel("Verifica raggiungibilità dispositivi IoT - Terna S.p.A.")
        subtitle.setObjectName("headerSubtitle")
        title_layout.addWidget(subtitle)
        
        layout.addWidget(title_widget)
        layout.addStretch()
        
        # Info versione
        version_label = QLabel("v1.0.0")
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
        anagrafica_label = QLabel("📁 File Anagrafica (Monitoraggio DIGIL):")
        anagrafica_label.setStyleSheet("font-weight: bold;")
        anagrafica_layout.addWidget(anagrafica_label)
        
        anagrafica_btn_layout = QHBoxLayout()
        self.file_path_label = QLabel("Nessun file caricato")
        self.file_path_label.setStyleSheet("color: #666666; font-style: italic;")
        anagrafica_btn_layout.addWidget(self.file_path_label, stretch=1)
        
        self.load_file_btn = QPushButton("Carica Anagrafica")
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
        test_list_label = QLabel("📋 Lista Dispositivi da Testare:")
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
        self.clear_test_list_btn.setFixedWidth(30)
        self.clear_test_list_btn.setToolTip("Rimuovi lista test")
        self.clear_test_list_btn.setStyleSheet("""
            QPushButton {
                background-color: #CC3300;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #992600; }
        """)
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
        
        # === RIGA 2: Filtri, Opzioni e Azioni ===
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
        
        filter_row.addSpacing(20)
        
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
        
        # Opzioni test
        thread_layout = QVBoxLayout()
        thread_label = QLabel("Opzioni:")
        thread_label.setStyleSheet("font-weight: bold;")
        thread_layout.addWidget(thread_label)
        
        thread_row = QHBoxLayout()
        thread_row.addWidget(QLabel("Thread paralleli:"))
        self.threads_spin = QSpinBox()
        self.threads_spin.setRange(1, 50)
        self.threads_spin.setValue(10)
        self.threads_spin.setToolTip("Numero di test eseguiti contemporaneamente")
        thread_row.addWidget(self.threads_spin)
        
        thread_layout.addLayout(thread_row)
        options_layout.addLayout(thread_layout, stretch=1)
        
        # Separatore verticale
        v_sep3 = QFrame()
        v_sep3.setFrameShape(QFrame.VLine)
        v_sep3.setStyleSheet("color: #CCCCCC;")
        options_layout.addWidget(v_sep3)
        
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
        self.stats_label = QLabel("OK: 0 | KO: 0 | In corso: 0")
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
        """Crea la tabella risultati"""
        table = QTableWidget()
        
        # Colonne
        columns = [
            "Stato", "Linea", "Sostegno", "DeviceID", "IP Address",
            "Vendor", "Tipo", "Ping", "SSH", "Note"
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
        table.setColumnWidth(0, 80)   # Stato
        table.setColumnWidth(1, 90)   # Linea
        table.setColumnWidth(2, 150)  # Sostegno
        table.setColumnWidth(3, 220)  # DeviceID
        table.setColumnWidth(4, 120)  # IP
        table.setColumnWidth(5, 70)   # Vendor
        table.setColumnWidth(6, 60)   # Tipo
        table.setColumnWidth(7, 100)  # Ping
        table.setColumnWidth(8, 100)  # SSH
        
        return table
    
    def apply_style(self):
        """Applica lo stile CSS"""
        self.setStyleSheet(TERNA_STYLE)
    
    def load_logo(self, logo_path: str):
        """Carica il logo Terna"""
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            self.logo_label.setPixmap(pixmap.scaled(120, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.logo_label.setText("")
            self.logo_label.setStyleSheet("background-color: transparent;")
    
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
                
                # Chiedi se copiare il file nella directory dati
                reply = QMessageBox.question(
                    self,
                    "Aggiorna File Predefinito",
                    "Vuoi impostare questo file come predefinito per i prossimi avvii?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    success, msg = update_monitoring_file(file_path)
                    if success:
                        self.log(msg, "SUCCESS")
                    else:
                        self.log(msg, "ERROR")
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
        
        # Carica la lista SENZA header (i DeviceID partono dalla riga 1, colonna A)
        success, msg, count = self.data_loader.load_test_list(
            file_path, 
            device_id_column=0,
            has_header=False
        )
        
        if success:
            self.test_list_label.setText(f"✓ {Path(file_path).name} ({count} dispositivi)")
            self.test_list_label.setStyleSheet("color: #009933;")
            self.clear_test_list_btn.setVisible(True)
            self.log(f"Lista test caricata: {count} dispositivi", "SUCCESS")
            
            # Aggiorna info con eventuale warning per DeviceID non trovati
            summary = self.data_loader.get_summary()
            if summary.get('not_found_count', 0) > 0:
                not_found = summary['not_found_in_anagrafica']
                warning_msg = (f"⚠️ {len(not_found)} DeviceID non trovati in anagrafica:\n\n"
                              f"{chr(10).join(not_found[:10])}"
                              f"{chr(10) + '...' if len(not_found) > 10 else ''}")
                QMessageBox.warning(self, "DeviceID Non Trovati", warning_msg)
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
        self.log("Lista test rimossa - verranno testati tutti i dispositivi", "INFO")
    
    def get_filtered_devices(self) -> list[DeviceInfo]:
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
        """Avvia i test di connettività"""
        devices = self.get_filtered_devices()
        
        if not devices:
            QMessageBox.warning(
                self,
                "Nessun Dispositivo",
                "Nessun dispositivo da testare. Carica un file di monitoraggio."
            )
            return
        
        # Conferma
        reply = QMessageBox.question(
            self,
            "Conferma Avvio Test",
            f"Avviare il test di connettività per {len(devices)} dispositivi?\n\n"
            f"Thread paralleli: {self.threads_spin.value()}\n\n"
            "NOTA: Il tool verificherà solo la raggiungibilità,\n"
            "senza MAI accedere ai dispositivi.",
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
        
        self.log(f"Avvio test per {len(devices)} dispositivi...", "INFO")
        
        # Popola tabella con stato "In attesa"
        for device in devices:
            self.add_device_to_table(device)
        
        # Avvia worker thread
        self.worker_thread = WorkerThread(devices, self.threads_spin.value())
        self.worker_thread.progress_signal.connect(self.on_progress)
        self.worker_thread.completed_signal.connect(self.on_completed)
        self.worker_thread.error_signal.connect(self.on_error)
        self.worker_thread.bridge_status_signal.connect(self.on_bridge_status)
        self.worker_thread.start()
    
    def on_bridge_status(self, connected, message: str):
        """Callback per stato connessione macchina ponte"""
        if connected is None:
            # Tentativo di connessione in corso
            self.log(f"🔌 {message}", "INFO")
            self.status_label.setText(f"Connessione al ponte...")
        elif connected:
            # Connesso con successo
            self.log(f"✅ PONTE CONNESSO: {message}", "SUCCESS")
            self.status_label.setText(f"Ponte connesso - Avvio test...")
        else:
            # Connessione fallita
            self.log(f"❌ PONTE NON RAGGIUNGIBILE: {message}", "ERROR")
            self.status_label.setText(f"Errore: {message}")
    
    def stop_test(self):
        """Ferma i test in corso"""
        if self.worker_thread:
            self.worker_thread.stop()
            self.log("Interruzione richiesta...", "WARNING")
            self.stop_btn.setEnabled(False)
    
    def add_device_to_table(self, device: DeviceInfo):
        """Aggiunge un dispositivo alla tabella"""
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        
        # Stato
        status_item = QTableWidgetItem("⏳")
        status_item.setTextAlignment(Qt.AlignCenter)
        self.results_table.setItem(row, 0, status_item)
        
        # Dati
        self.results_table.setItem(row, 1, QTableWidgetItem(device.linea))
        self.results_table.setItem(row, 2, QTableWidgetItem(device.sostegno))
        self.results_table.setItem(row, 3, QTableWidgetItem(device.device_id))
        self.results_table.setItem(row, 4, QTableWidgetItem(device.ip_address))
        self.results_table.setItem(row, 5, QTableWidgetItem(device.vendor.value))
        self.results_table.setItem(row, 6, QTableWidgetItem(device.device_type.value))
        self.results_table.setItem(row, 7, QTableWidgetItem("-"))
        self.results_table.setItem(row, 8, QTableWidgetItem("-"))
        self.results_table.setItem(row, 9, QTableWidgetItem(""))
        
        # Salva riferimento al device_id per aggiornamento
        status_item.setData(Qt.UserRole, device.device_id)
    
    def update_device_in_table(self, device: DeviceInfo):
        """Aggiorna lo stato di un dispositivo nella tabella"""
        # Trova la riga
        for row in range(self.results_table.rowCount()):
            item = self.results_table.item(row, 0)
            if item and item.data(Qt.UserRole) == device.device_id:
                # Aggiorna stato
                if device.ssh_status == ConnectionStatus.SSH_PORT_OPEN:
                    status = "✅"
                    status_color = QColor("#C6EFCE")
                elif device.ping_status == ConnectionStatus.PING_OK:
                    status = "⚠️"
                    status_color = QColor("#FFEB9C")
                elif device.ping_status == ConnectionStatus.VPN_ERROR:
                    status = "🔌"
                    status_color = QColor("#FFC7CE")
                elif device.ping_status == ConnectionStatus.PENDING:
                    status = "🔄"
                    status_color = QColor("#FFFFFF")
                else:
                    status = "❌"
                    status_color = QColor("#FFC7CE")
                
                item.setText(status)
                
                # Colora riga
                for col in range(self.results_table.columnCount()):
                    cell = self.results_table.item(row, col)
                    if cell:
                        cell.setBackground(status_color)
                
                # Aggiorna ping
                ping_text = device.ping_status.value
                if device.ping_time_ms:
                    ping_text += f" ({device.ping_time_ms:.1f}ms)"
                self.results_table.item(row, 7).setText(ping_text)
                
                # Aggiorna SSH
                self.results_table.item(row, 8).setText(device.ssh_status.value)
                
                # Aggiorna note
                self.results_table.item(row, 9).setText(device.error_message)
                
                break
    
    def on_progress(self, device: DeviceInfo, message: str, current: int, total: int):
        """Callback progresso dal worker thread"""
        self.progress_bar.setValue(current)
        self.update_device_in_table(device)
        
        # Aggiorna statistiche
        ok_count = sum(1 for r in self.results if r.ssh_status == ConnectionStatus.SSH_PORT_OPEN)
        ko_count = sum(1 for r in self.results if r.ping_status in [
            ConnectionStatus.PING_FAILED, ConnectionStatus.ERROR, ConnectionStatus.VPN_ERROR
        ])
        in_progress = total - len(self.results)
        
        self.stats_label.setText(f"OK: {ok_count} | KO: {ko_count} | In corso: {in_progress}")
        self.status_label.setText(f"Testing: {device.device_id}")
    
    def on_completed(self, results: list[DeviceInfo]):
        """Callback completamento dal worker thread"""
        self.results = results
        
        # Aggiorna tutti nella tabella
        for device in results:
            self.update_device_in_table(device)
        
        # Ripristina UI
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.export_btn.setEnabled(True)
        self.load_file_btn.setEnabled(True)
        
        # Statistiche finali
        ok_count = sum(1 for r in results if r.ssh_status == ConnectionStatus.SSH_PORT_OPEN)
        ko_count = len(results) - ok_count
        
        self.status_label.setText(f"Completato: {ok_count} OK, {ko_count} problemi su {len(results)} dispositivi")
        self.log(f"Test completato: {ok_count} OK, {ko_count} problemi", "SUCCESS" if ko_count == 0 else "WARNING")
        
        # Notifica
        QMessageBox.information(
            self,
            "Test Completato",
            f"Test completato per {len(results)} dispositivi.\n\n"
            f"✅ OK: {ok_count}\n"
            f"❌ Problemi: {ko_count}\n\n"
            "Usa 'Esporta Excel' per salvare i risultati."
        )
    
    def on_error(self, error_message: str):
        """Callback errore dal worker thread"""
        self.log(f"Errore: {error_message}", "ERROR")
        
        # Ripristina UI
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.load_file_btn.setEnabled(True)
        
        QMessageBox.critical(self, "Errore", f"Errore durante i test:\n\n{error_message}")
    
    def export_results(self):
        """Esporta i risultati in Excel"""
        if not self.results:
            QMessageBox.warning(self, "Nessun Risultato", "Nessun risultato da esportare.")
            return
        
        # Dialog per salvare
        default_name = f"DIGIL_SSH_Check_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Salva Risultati",
            str(Path.home() / "Downloads" / default_name),
            "Excel Files (*.xlsx)"
        )
        
        if file_path:
            success, result = self.result_exporter.export_results(self.results, file_path)
            
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
                    elif platform.system() == 'Darwin':  # macOS
                        subprocess.call(['open', result])
                    else:  # Linux
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
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """Entry point dell'applicazione"""
    # High DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("DIGIL SSH Checker")
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