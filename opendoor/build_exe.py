"""
Build script per creare l'eseguibile Windows
============================================
DIGIL Diagnostic Checker v2.0

Usa PyInstaller per creare un .exe standalone

Utilizzo:
    python build_exe.py

Requisiti:
    pip install pyinstaller

Output:
    dist/DIGIL_Diagnostic_Checker.exe
"""

import subprocess
import sys
import os
from pathlib import Path


def check_dependencies():
    """Verifica che tutte le dipendenze siano installate"""
    required = [
        'PyQt5',
        'pandas', 
        'openpyxl',
        'xlsxwriter',
        'paramiko',
        'python-dotenv',
        'requests',
        'pymongo',
        'sshtunnel'
    ]
    
    missing = []
    for pkg in required:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print("⚠️  Dipendenze mancanti:")
        for pkg in missing:
            print(f"   - {pkg}")
        print("\nInstalla con: pip install -r requirements.txt")
        return False
    
    return True


def create_directories(script_dir: Path):
    """Crea le directory necessarie se non esistono"""
    dirs = ['assets', 'data']
    for d in dirs:
        dir_path = script_dir / d
        dir_path.mkdir(exist_ok=True)
        print(f"✓ Directory: {dir_path}")


def create_env_example(script_dir: Path):
    """Crea il file .env.example se non esiste"""
    env_example = script_dir / ".env.example"
    
    if not env_example.exists():
        content = """# ============================================
# DIGIL Diagnostic Checker v2.0 - Configurazione
# ============================================

# Credenziali Macchina Ponte
BRIDGE_HOST=10.147.131.41
BRIDGE_USER=reply
BRIDGE_PASSWORD=YOUR_PASSWORD_HERE

# Timeout connessioni (secondi)
BRIDGE_TIMEOUT=10
DEVICE_TIMEOUT=5
SSH_PORT=22

# MongoDB (per check 24h via SSH tunnel)
MONGO_URI=mongodb://user:password@host1:27017,host2:27017,host3:27017/?authSource=ibm_iot&replicaSet=rs0
MONGO_DATABASE=ibm_iot
MONGO_COLLECTION=event
"""
        with open(env_example, 'w') as f:
            f.write(content)
        print(f"✓ Creato: {env_example}")


def build():
    """Esegue il build dell'applicazione"""
    
    print("=" * 60)
    print("DIGIL Diagnostic Checker v2.0 - Build Eseguibile")
    print("=" * 60)
    print()
    
    # Directory dello script
    script_dir = Path(__file__).parent
    
    # Verifica dipendenze
    print("Verifica dipendenze...")
    if not check_dependencies():
        print("\n❌ Build annullato: installa le dipendenze mancanti")
        sys.exit(1)
    print("✓ Tutte le dipendenze sono installate\n")
    
    # Crea directory necessarie
    print("Creazione directory...")
    create_directories(script_dir)
    create_env_example(script_dir)
    print()
    
    # Verifica che il file .env esista
    env_file = script_dir / ".env"
    if not env_file.exists():
        print("⚠️  File .env non trovato!")
        print("   Copia .env.example in .env e configura le credenziali")
        print("   Il build continuerà ma l'exe richiederà il file .env\n")
    
    # Verifica file sorgenti
    required_files = [
        'main.py',
        'connectivity_checker.py',
        'api_client.py',
        'mongodb_checker.py',
        'malfunction_classifier.py',
        'data_handler.py'
    ]
    
    print("Verifica file sorgenti...")
    for f in required_files:
        if not (script_dir / f).exists():
            print(f"❌ File mancante: {f}")
            sys.exit(1)
        print(f"✓ {f}")
    print()
    
    # Opzioni PyInstaller
    pyinstaller_args = [
        sys.executable, '-m', 'PyInstaller',
        '--name=DIGIL_Diagnostic_Checker',
        '--onefile',           # Singolo file .exe
        '--windowed',          # No console window (GUI app)
        '--clean',             # Pulisce cache prima del build
        
        # Moduli nascosti che potrebbero servire
        '--hidden-import=PyQt5',
        '--hidden-import=PyQt5.QtWidgets',
        '--hidden-import=PyQt5.QtCore',
        '--hidden-import=PyQt5.QtGui',
        '--hidden-import=PyQt5.sip',
        '--hidden-import=pandas',
        '--hidden-import=openpyxl',
        '--hidden-import=xlsxwriter',
        '--hidden-import=paramiko',
        '--hidden-import=requests',
        '--hidden-import=urllib3',
        '--hidden-import=pymongo',
        '--hidden-import=sshtunnel',
        '--hidden-import=dotenv',
        
        # Moduli del progetto
        '--hidden-import=connectivity_checker',
        '--hidden-import=api_client',
        '--hidden-import=mongodb_checker',
        '--hidden-import=malfunction_classifier',
        '--hidden-import=data_handler',
        
        # Raccogli tutti i file necessari per PyQt5
        '--collect-all=PyQt5',
        
        # Ottimizzazioni
        '--noupx',             # Non comprimere con UPX (più stabile)
        
        # Entry point
        str(script_dir / 'main.py'),
    ]
    
    # Aggiungi file .env se esiste
    if env_file.exists():
        pyinstaller_args.insert(-1, f'--add-data={env_file};.')
    
    # Aggiungi icona se esiste
    icon_path = script_dir / "assets" / "icon.ico"
    if icon_path.exists():
        pyinstaller_args.insert(-1, f'--icon={icon_path}')
        print(f"✓ Icona: {icon_path}")
    
    print("Esecuzione PyInstaller...")
    print("-" * 40)
    print()
    
    # Esegui PyInstaller
    result = subprocess.run(pyinstaller_args, cwd=script_dir)
    
    print()
    print("-" * 40)
    
    if result.returncode == 0:
        exe_path = script_dir / 'dist' / 'DIGIL_Diagnostic_Checker.exe'
        
        print()
        print("=" * 60)
        print("✅ BUILD COMPLETATO CON SUCCESSO!")
        print("=" * 60)
        print()
        print(f"📦 Eseguibile: {exe_path}")
        
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"📊 Dimensione: {size_mb:.1f} MB")
        
        print()
        print("=" * 60)
        print("📋 ISTRUZIONI PER LA DISTRIBUZIONE")
        print("=" * 60)
        print()
        print("Crea una cartella con questa struttura:")
        print()
        print("  DIGIL_Diagnostic_Checker/")
        print("  ├── DIGIL_Diagnostic_Checker.exe")
        print("  ├── .env                    ← Configura le credenziali!")
        print("  ├── data/")
        print("  │   └── Monitoraggio_APPARATI_DIGIL_INSTALLATI.xlsx")
        print("  └── assets/")
        print("      └── logo_terna.png      (opzionale)")
        print()
        print("⚠️  IMPORTANTE:")
        print("   1. Il file .env DEVE essere nella stessa cartella dell'exe")
        print("   2. Configura BRIDGE_PASSWORD e MONGO_URI nel .env")
        print("   3. L'utente deve essere connesso alla VPN Terna")
        print()
        
    else:
        print()
        print("=" * 60)
        print("❌ ERRORE DURANTE IL BUILD!")
        print("=" * 60)
        print()
        print(f"Exit code: {result.returncode}")
        print()
        print("Possibili soluzioni:")
        print("  1. Verifica che tutte le dipendenze siano installate")
        print("  2. Prova: pip install --upgrade pyinstaller")
        print("  3. Elimina le cartelle 'build' e 'dist' e riprova")
        print()
        sys.exit(1)


def clean():
    """Pulisce i file generati dal build precedente"""
    script_dir = Path(__file__).parent
    
    dirs_to_clean = ['build', 'dist', '__pycache__']
    files_to_clean = ['*.spec']
    
    print("Pulizia file di build precedenti...")
    
    import shutil
    for d in dirs_to_clean:
        dir_path = script_dir / d
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"  Rimosso: {d}/")
    
    import glob
    for pattern in files_to_clean:
        for f in glob.glob(str(script_dir / pattern)):
            os.remove(f)
            print(f"  Rimosso: {Path(f).name}")
    
    print("✓ Pulizia completata\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Build DIGIL Diagnostic Checker')
    parser.add_argument('--clean', action='store_true', help='Pulisce i file di build precedenti')
    parser.add_argument('--clean-only', action='store_true', help='Solo pulizia, senza build')
    
    args = parser.parse_args()
    
    if args.clean or args.clean_only:
        clean()
    
    if not args.clean_only:
        build()