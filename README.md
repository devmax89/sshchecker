# DIGIL SSH Connectivity Checker

**Tool per la verifica della raggiungibilità SSH dei dispositivi DIGIL IoT**

Sviluppato per **Terna S.p.A.** - Team IoT

---

## 📋 Descrizione

Questo tool consente di verificare la raggiungibilità di rete dei dispositivi DIGIL installati sulle linee di trasmissione elettrica, **senza MAI accedere effettivamente ai dispositivi**.

### Test Eseguiti
1. **Connessione alla macchina ponte** - Verifica che la VPN sia attiva e la macchina ponte raggiungibile
2. **Ping verso il dispositivo** - Test ICMP dalla macchina ponte verso il DIGIL
3. **Verifica porta SSH** - Controllo che la porta 22 sia aperta (senza login)

### Vendor Supportati
- **INDRA** (DIGIL_IND_xxxx)
- **SIRTI** (DIGIL_SR2_xxxx)  
- **MII/Marini** (DIGIL_MRN_xxxx)

---

## 🚀 Installazione

### Prerequisiti
- Python 3.10 o superiore
- Connessione VPN alla rete Terna

### Setup Ambiente

```bash
# Clona o scarica il progetto
cd digil_ssh_checker

# Crea ambiente virtuale (opzionale ma consigliato)
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Installa dipendenze
pip install -r requirements.txt
```

### Configurazione

1. **Modifica il file `.env`** con le credenziali corrette:

```env
BRIDGE_HOST=10.147.131.41
BRIDGE_USER=reply
BRIDGE_PASSWORD=YOUR_PASSWORD
BRIDGE_TIMEOUT=10
DEVICE_TIMEOUT=5
SSH_PORT=22
```

2. **Posiziona il file di monitoraggio** nella cartella `data/`:
   - `Monitoraggio_APPARATI_DIGIL_INSTALLATI.xlsx`

3. **(Opzionale) Aggiungi il logo Terna** in `assets/logo_terna.png`

---

## 💻 Utilizzo

### Avvio Applicazione

```bash
python main.py
```

### Interfaccia Grafica

1. **Carica File** - Il tool cerca automaticamente il file di monitoraggio. Se non trovato, caricalo manualmente.

2. **Filtri** - Seleziona vendor e/o tipo dispositivo per testare un sottoinsieme.

3. **Thread Paralleli** - Imposta quanti test eseguire contemporaneamente (default: 10).

4. **Avvia Test** - Clicca per iniziare la verifica.

5. **Esporta Excel** - Al termine, esporta i risultati in un file Excel formattato.

### Indicatori di Stato

| Icona | Significato |
|-------|-------------|
| ✅ | Dispositivo raggiungibile (Ping OK + SSH OK) |
| ⚠️ | Ping OK ma SSH non risponde |
| ❌ | Dispositivo non raggiungibile |
| 🔌 | Errore VPN/ponte non raggiungibile |
| ⏳ | Test in attesa |
| 🔄 | Test in corso |

---

## 📦 Build Eseguibile (.exe)

Per creare un eseguibile standalone per Windows:

```bash
# Installa PyInstaller
pip install pyinstaller

# Esegui il build
python build_exe.py
```

L'eseguibile sarà creato in `dist/DIGIL_SSH_Checker.exe`

### Distribuzione

Per distribuire il tool:
1. Copia `DIGIL_SSH_Checker.exe`
2. Copia il file `.env` nella stessa cartella
3. Crea una cartella `data/` con il file di monitoraggio
4. (Opzionale) Crea `assets/` con il logo

---

## 📁 Struttura Progetto

```
digil_ssh_checker/
├── main.py                    # Applicazione GUI principale
├── connectivity_checker.py    # Modulo test connettività
├── data_handler.py           # Gestione file Excel
├── build_exe.py              # Script per creare .exe
├── requirements.txt          # Dipendenze Python
├── .env                      # Credenziali (NON committare!)
├── .env.example              # Template credenziali
├── README.md                 # Questo file
├── data/                     # File di monitoraggio
│   └── Monitoraggio_APPARATI_DIGIL_INSTALLATI.xlsx
└── assets/                   # Risorse grafiche
    ├── logo_terna.png
    └── icon.ico
```

---

## 🔒 Sicurezza

⚠️ **IMPORTANTE**:
- Il file `.env` contiene credenziali sensibili. **NON** condividerlo o committarlo in repository.
- Il tool **NON** accede mai ai dispositivi, esegue solo test di raggiungibilità.
- Tutte le connessioni passano attraverso la VPN aziendale.

---

## 📊 Output Excel

Il file Excel esportato contiene:

### Sheet "Risultati Test"
| Colonna | Descrizione |
|---------|-------------|
| Linea | Codice linea elettrica |
| ST Sostegno | Identificativo sostegno |
| DeviceID | ID univoco DIGIL |
| IP Address | Indirizzo IP SIM |
| Vendor | INDRA/SIRTI/MII |
| Tipo | master/slave |
| Ping Status | Esito test ping |
| Ping Time | Latenza in ms |
| SSH Status | Esito test porta SSH |
| Check LTE | Esito finale (OK/KO) |
| Note | Eventuali errori |
| Timestamp | Data/ora del test |

### Sheet "Riepilogo"
Statistiche aggregate del test.

---

## 🔧 Troubleshooting

### "Ponte non raggiungibile"
- Verifica che la VPN sia connessa
- Controlla le credenziali nel file `.env`
- Prova a pingare manualmente `10.147.131.41`

### "Molti dispositivi KO"
- Potrebbe essere un problema di rete generale
- Verifica prima la raggiungibilità di qualche IP manualmente dalla macchina ponte

### "File di monitoraggio non trovato"
- Posiziona il file in `data/Monitoraggio_APPARATI_DIGIL_INSTALLATI.xlsx`
- Oppure caricalo manualmente dall'interfaccia

### Interfaccia non risponde
- Riduci il numero di thread paralleli
- I test con molti dispositivi possono richiedere tempo

---

## 🔄 Aggiornamenti Futuri

Il tool è progettato per essere estensibile. Possibili evolutive:
- [ ] Integrazione con database PostgreSQL
- [ ] Scheduling test automatici
- [ ] Dashboard web-based
- [ ] Notifiche email/Teams per dispositivi KO
- [ ] Storico test con trend analysis
- [ ] Export in formati aggiuntivi (CSV, PDF)

---

## 👥 Contatti

**Team IoT - Terna S.p.A.**

---

## 📝 Changelog

### v1.0.0 (2025-01)
- Release iniziale
- Test ping e SSH multi-thread
- Interfaccia grafica PyQt5 stile Terna
- Export risultati in Excel
- Supporto vendor INDRA, SIRTI, MII
- Riconoscimento automatico master/slave
