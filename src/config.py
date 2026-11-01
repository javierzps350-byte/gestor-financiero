import os
import sys
from pathlib import Path

APP_NAME = "Gestor Financiero"
APP_VERSION = "0.1.3"

if getattr(sys, "frozen", False):
    # Los recursos del programa van en el paquete; los datos del usuario quedan
    # fuera del ejecutable para sobrevivir a actualizaciones y reinstalaciones.
    ROOT_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DATA_HOME = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GestorFinanciero"
    DATA_DIR = DATA_HOME / "data"
    EVIDENCE_DIR = DATA_HOME / "evidencias"
    BACKUP_DIR = DATA_HOME / "copias_seguridad"
    LOG_DIR = DATA_HOME / "logs"
else:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    DATA_HOME = ROOT_DIR
    DATA_DIR = ROOT_DIR / "data"
    EVIDENCE_DIR = DATA_DIR / "evidencias"
    BACKUP_DIR = DATA_DIR / "copias_seguridad"
    LOG_DIR = ROOT_DIR / "logs"

DB_PATH = DATA_DIR / "gestor_financiero.sqlite3"
MODEL_DIR = DATA_HOME / "models"

for _path in (DATA_DIR, EVIDENCE_DIR, BACKUP_DIR, LOG_DIR, MODEL_DIR):
    _path.mkdir(parents=True, exist_ok=True)
