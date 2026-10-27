import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
load_dotenv(BACKEND / '.env')
RUNTIME = ROOT / 'runtime'
RUNTIME.mkdir(exist_ok=True)

def database_url():
    return os.environ.get('DATABASE_URL', 'sqlite:///' + str(RUNTIME / 'lottery.db'))

def sendkey():
    # Read at send time so local configuration updates do not require an API restart.
    load_dotenv(BACKEND / '.env', override=True)
    return os.environ.get('SERVERCHAN_SENDKEY', '')
