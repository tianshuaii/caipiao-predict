"""Create a database/artifact backup and optionally restore into a NEW audit database."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import json
ROOT=Path(__file__).resolve().parents[1]
BASE=['docker','compose','exec','-T','mysql','sh','-c']
def mysql(sql,database='lottery'):
    return subprocess.check_output(BASE+['MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -N -B "$1"','sh',database],input=sql.encode(),cwd=ROOT).decode()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target=ROOT/'backups'/stamp;target.mkdir(parents=True,mode=0o700)
    dump=target/'lottery.sql'
    with dump.open('wb') as output:
        subprocess.run(BASE+['MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --no-tablespaces --set-gtid-purged=OFF lottery'],cwd=ROOT,stdout=output,check=True)
    dump.chmod(0o600)
    shutil.copytree(ROOT/'runtime/artifacts',target/'artifacts')
    counts=mysql("SELECT 'draws',COUNT(*) FROM draws UNION ALL SELECT 'predictions',COUNT(*) FROM predictions UNION ALL SELECT 'raw_fetches',COUNT(*) FROM raw_fetches;")
    result={'backup':str(target),'counts':counts,'restored':False}
    if args.verify:
        database='lottery_restore_'+stamp.lower()
        mysql(f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4;')
        with dump.open('rb') as source:
            subprocess.run(BASE+['MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot "$1"','sh',database],cwd=ROOT,stdin=source,check=True)
        restored=mysql("SELECT 'draws',COUNT(*) FROM draws UNION ALL SELECT 'predictions',COUNT(*) FROM predictions UNION ALL SELECT 'raw_fetches',COUNT(*) FROM raw_fetches;",database)
        if restored!=counts: raise RuntimeError('Restored row counts differ')
        result.update(restored=True,restore_database=database)
    (target/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
