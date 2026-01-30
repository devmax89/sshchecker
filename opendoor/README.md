# DIGIL Diagnostic Checker v2.0

**Tool avanzato per verifica connettività e diagnostica dispositivi DIGIL IoT**

Sviluppato per **Terna S.p.A.** - Team IoT

---

## 📋 Descrizione

Tool desktop professionale per la diagnostica completa dei dispositivi DIGIL installati sulle linee di trasmissione elettrica. Esegue verifiche multi-livello e classifica automaticamente i malfunzionamenti.

### Check Diagnostici Eseguiti

| Fase | Check | Descrizione |
|------|-------|-------------|
| 1 | **SSH/Ping** | Verifica raggiungibilità di rete via macchina ponte |
| 2 | **API Diagnostica** | Interroga le API REST per stato batteria, LTE, porta |
| 3 | **MongoDB 24h** | Verifica invio dati nelle ultime 24 ore via SSH tunnel |

### Classificazione Automatica Malfunzionamenti

| Tipo | Condizione | Azione Suggerita |
|------|------------|------------------|
| **OK** | Tutti i check passati | Nessuna |
| **Disconnesso** | SSH/Ping KO o LTE KO | Verificare connettività, SIM, antenna |
| **Metriche assenti** | Connesso ma MongoDB KO | Verificare configurazione invio dati |
| **Allarme batteria** | `battery_ok = False` | Programmare sostituzione batteria |
| **Porta aperta** | `door_open = True` | Verificare fisicamente il dispositivo |

### Vendor Supportati
- **INDRA** (DIGIL_IND_xxxx)
- **SIRTI** (DIGIL_SR2_xxxx)  
- **MII/Marini** (DIGIL_MRN_xxxx)

---

## 🚀 Installazione

### Prerequisiti
- Python 3.10 o superiore
- Connessione VPN alla rete Terna
- Accesso alla macchina ponte (10.147.131.41)

### Setup Ambiente

```bash
# Clona o scarica il progetto
cd digil_diagnostic_checker

# Crea ambiente virtuale (consigliato)
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Installa dipendenze
pip install -r requirements.txt
```

### Configurazione

1. **Crea/modifica il file `.env`** con le credenziali:

```env
# Credenziali Macchina Ponte
BRIDGE_HOST=10.147.131.41
BRIDGE_USER=reply
BRIDGE_PASSWORD=YOUR_PASSWORD

# Timeout connessioni (secondi)
BRIDGE_TIMEOUT=10
DEVICE_TIMEOUT=5
SSH_PORT=22

# MongoDB (per check 24h)
MONGO_URI=mongodb://user:password@host1:27017,host2:27017,host3:27017/?authSource=ibm_iot&replicaSet=rs0
MONGO_DATABASE=ibm_iot
MONGO_COLLECTION=event
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

1. **File Anagrafica** - Carica il file Excel di monitoraggio dispositivi
2. **Lista Test** (opzionale) - Carica una lista specifica di DeviceID da testare
3. **Filtri** - Filtra per vendor (INDRA/SIRTI/MII) e/o tipo (Master/Slave)
4. **Check da eseguire** - Seleziona quali diagnostiche attivare:
   - ✅ SSH/Ping (sempre attivo)
   - ☑️ API Diagnostica
   - ☑️ MongoDB 24h
5. **Thread** - Imposta il numero di test paralleli (default: 10)
6. **Avvia Test** - Lancia la diagnostica
7. **Esporta Excel** - Salva i risultati in formato Excel

### Indicatori di Stato nella Tabella

| Colore | Icona | Significato |
|--------|-------|-------------|
| 🟠 Arancione | ⏳ | In attesa di test |
| 🔵 Blu | 🔄 | Test in corso |
| 🟢 Verde | ✅ | Dispositivo OK |
| 🟡 Giallo | ⚠️ | Warning (alcuni check KO) |
| 🔴 Rosso | ❌ | Dispositivo con problemi |

### Colonne Diagnostiche

| Colonna | Valori | Descrizione |
|---------|--------|-------------|
| MongoDB | Data/KO/- | Ultimo invio dati o stato |
| LTE | OK/KO/0 | Stato connessione LTE da API |
| SSH | OK/KO/- | Raggiungibilità porta SSH |
| Batteria | OK/KO/- | Stato allarme batteria |
| Porta | OK/KO/- | Stato allarme porta aperta |
| Malfunzionamento | Tipo | Classificazione automatica |

---

## 📦 Build Eseguibile (.exe)

Per creare un eseguibile standalone per Windows:

```bash
# Installa PyInstaller (se non già installato)
pip install pyinstaller

# Esegui il build
python build_exe.py
```

L'eseguibile sarà creato in `dist/DIGIL_Diagnostic_Checker.exe`

### Distribuzione

Per distribuire il tool, crea una cartella con:
```
DIGIL_Diagnostic_Checker/
├── DIGIL_Diagnostic_Checker.exe
├── .env                          # Credenziali (da configurare)
├── data/
│   └── Monitoraggio_APPARATI_DIGIL_INSTALLATI.xlsx
└── assets/
    └── logo_terna.png            # (opzionale)
```

---

## 📁 Struttura Progetto

```
digil_diagnostic_checker/
├── main.py                    # Applicazione GUI principale (PyQt5)
├── connectivity_checker.py    # Modulo test SSH/Ping
├── api_client.py             # Client API REST diagnostica (OAuth2)
├── mongodb_checker.py        # Check MongoDB via SSH tunnel
├── malfunction_classifier.py # Classificazione malfunzionamenti
├── data_handler.py           # Gestione file Excel I/O
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
- Il file `.env` contiene credenziali sensibili. **NON** condividerlo o committarlo.
- Le credenziali MongoDB sono usate solo per query in lettura.
- Il tool **NON** accede mai ai dispositivi DIGIL, esegue solo verifiche di raggiungibilità.
- Tutte le connessioni passano attraverso la VPN aziendale.
- Il tunnel SSH verso MongoDB è temporaneo e viene chiuso al termine dei test.

---

## 📊 Output Excel

Il file Excel esportato contiene:

### Sheet "Risultati Diagnostici"

| Colonna | Descrizione |
|---------|-------------|
| Linea | Codice linea elettrica |
| ST Sostegno | Identificativo sostegno |
| DeviceID | ID univoco DIGIL |
| IP Address | Indirizzo IP SIM |
| Vendor | INDRA/SIRTI/MII |
| Tipo | master/slave |
| Check MongoDB | Data ultimo invio o KO |
| Check LTE | Stato connessione LTE |
| Check SSH | Esito test porta SSH |
| Batteria | Stato allarme batteria |
| Porta | Stato allarme porta |
| SOC % | State of Charge batteria |
| SOH % | State of Health batteria |
| Segnale dBm | Potenza segnale LTE |
| Canale | Canale LTE/NBIoT |
| Tipo Malfunzionamento | Classificazione automatica |
| Note | Eventuali errori |
| Timestamp Test | Data/ora del test |

### Sheet "Riepilogo"

Statistiche aggregate: totale dispositivi, OK, disconnessi, metriche assenti, allarmi batteria, porte aperte.

---

## 🔧 Troubleshooting

### "Ponte non raggiungibile"
- Verifica che la VPN sia connessa
- Controlla le credenziali nel file `.env`
- Prova: `ping 10.147.131.41`

### "Tunnel SSH fallito" (MongoDB)
- Verifica che `sshtunnel` sia installato: `pip install sshtunnel`
- Controlla la `MONGO_URI` nel file `.env`
- Verifica che MongoDB sia raggiungibile dalla macchina ponte

### "API Diagnostica fallita"
- Verifica la connettività verso `digil-back-end-onesait.servizi.prv`
- Il token OAuth2 potrebbe essere scaduto (si rinnova automaticamente)

### "Molti dispositivi Disconnessi"
- Potrebbe essere un problema di rete generale
- Verifica prima alcuni IP manualmente dalla macchina ponte
- I dispositivi **Slave** si svegliano ogni 15 minuti

### Interfaccia lenta o non risponde
- Riduci il numero di thread paralleli
- I test con molti dispositivi possono richiedere tempo (specialmente Slave)

---

## ⏱️ Tempistiche Test

| Tipo Device | Timeout Ping | Retry SSH |
|-------------|--------------|-----------|
| **Master** | 5 minuti | 5 tentativi |
| **Slave** | 20 minuti | 5 tentativi |

> **Nota**: I dispositivi Slave si svegliano ogni 15 minuti, quindi il timeout è più lungo.

---

## 🔄 Changelog

### v2.0.0 (2025-01)
- ✨ **Nuova architettura diagnostica multi-fase**
- ✨ Integrazione API REST diagnostica (OAuth2)
- ✨ Check MongoDB 24h via SSH tunnel
- ✨ Classificazione automatica malfunzionamenti
- ✨ Supporto lista test personalizzata
- ✨ Indicatori visivi migliorati (arancione/blu/verde/rosso)
- ✨ Colonne diagnostiche estese (batteria, porta, SOC, SOH, segnale)
- 🐛 Fix visualizzazione stato "in corso" (blu invece di rosso)
- 🎨 UI migliorata con checkbox per selezione check

### v1.0.0 (2024-12)
- Release iniziale
- Test ping e SSH multi-thread
- Interfaccia grafica PyQt5 stile Terna
- Export risultati in Excel
- Supporto vendor INDRA, SIRTI, MII

---

## 👥 Contatti

**Team IoT - Terna S.p.A.**

---

## 📝 Note Tecniche

### Architettura Connessioni

```
┌─────────────────┐     VPN      ┌──────────────────┐     SSH      ┌─────────────────┐
│   PC Locale     │ ──────────── │  Macchina Ponte  │ ──────────── │  Dispositivi    │
│   (Tool)        │              │  10.147.131.41   │              │  DIGIL          │
└─────────────────┘              └──────────────────┘              └─────────────────┘
        │                                 │
        │ HTTPS (API)                     │ SSH Tunnel
        ▼                                 ▼
┌─────────────────┐              ┌──────────────────┐
│  API Onesait    │              │    MongoDB       │
│  (Diagnostica)  │              │  (Telemetria)    │
└─────────────────┘              └──────────────────┘
```

### Formato DeviceID

```
1:1:2:XX:YY:DIGIL_VND_NNNN
      │  │       │    │
      │  │       │    └── Numero sequenziale
      │  │       └─────── Vendor (IND/SR2/MRN)
      │  └─────────────── Identificatore (es: 21, 22, 25)
      └────────────────── Tipo: 15=Master, 16=Slave
```