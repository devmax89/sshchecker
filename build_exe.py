"""
Build script per creare l'eseguibile Windows
============================================
Usa PyInstaller per creare un .exe standalone

Utilizzo:
    python build_exe.py

Requisiti:
    pip install pyinstaller

Output:
    dist/DIGIL_SSH_Checker.exe
"""

import subprocess
import sys
import os
from pathlib import Path

def build():
    """Esegue il build dell'applicazione"""
    
    # Directory dello script
    script_dir = Path(__file__).parent
    
    # Assicurati che la directory assets esista
    assets_dir = script_dir / "assets"
    assets_dir.mkdir(exist_ok=True)
    
    # Directory data
    data_dir = script_dir / "data"
    data_dir.mkdir(exist_ok=True)
    
    # Crea file .env di esempio se non esiste
    env_example = script_dir / ".env.example"
    if not env_example.exists():
        with open(env_example, 'w') as f:
            f.write("""# Credenziali Macchina Ponte
BRIDGE_HOST=10.147.131.41
BRIDGE_USER=reply
BRIDGE_PASSWORD=YOUR_PASSWORD_HERE

# Timeout connessioni (secondi)
BRIDGE_TIMEOUT=10
DEVICE_TIMEOUT=5
SSH_PORT=22
""")
    
    # Opzioni PyInstaller
    pyinstaller_args = [
        sys.executable, '-m', 'PyInstaller',
        '--name=DIGIL_SSH_Checker',
        '--onefile',  # Singolo file .exe
        '--windowed',  # No console window
        '--clean',
        
        # Aggiungi file dati
        f'--add-data={script_dir / ".env"};.',
        
        # Icona (se esiste)
        # '--icon=assets/icon.ico',
        
        # Moduli nascosti che potrebbero servire
        '--hidden-import=PyQt5.sip',
        '--hidden-import=pandas',
        '--hidden-import=openpyxl',
        '--hidden-import=xlsxwriter',
        '--hidden-import=paramiko',
        
        # Ottimizzazioni
        '--noupx',
        
        # Entry point
        str(script_dir / 'main.py'),
    ]
    
    print("=" * 60)
    print("DIGIL SSH Checker - Build Eseguibile")
    print("=" * 60)
    print()
    print("Esecuzione PyInstaller...")
    print()
    
    # Esegui PyInstaller
    result = subprocess.run(pyinstaller_args, cwd=script_dir)
    
    if result.returncode == 0:
        print()
        print("=" * 60)
        print("BUILD COMPLETATO CON SUCCESSO!")
        print("=" * 60)
        print()
        print(f"Eseguibile: {script_dir / 'dist' / 'DIGIL_SSH_Checker.exe'}")
        print()
        print("IMPORTANTE:")
        print("1. Copia il file .env nella stessa directory dell'exe")
        print("2. Copia il file di monitoraggio Excel nella cartella 'data'")
        print("3. (Opzionale) Copia il logo Terna in assets/")
        print()
    else:
        print()
        print("ERRORE durante il build!")
        print(f"Exit code: {result.returncode}")
        sys.exit(1)


if __name__ == "__main__":
    build()
