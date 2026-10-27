"""Read a local source container; migrate and restore only a disposable MySQL copy.

No source writes, no notifications. Requires Docker and the backend environment.
Backups include business data: directory mode 0700, files mode 0600.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from alembic import command
from alembic.config import Config


def run(*args,input=None,env=None):
    return subprocess.run(args,input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,env=env).stdout


def sql(container,query):
    return run('docker','exec','-i',container,'sh','-c',
               'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot --batch --raw --skip-column-names',input=query.encode())


def signature(container):
    names=sql(container,'SHOW TABLES FROM lottery').decode().splitlines()
    result={}
    for name in names:
        if name=='alembic_version': continue
        assert re.fullmatch(r'[a-z_]+',name)
        keys=sql(container,f"SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA='lottery' AND TABLE_NAME='{name}' AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION").decode().splitlines()
        assert keys and all(re.fullmatch(r'[a-z_]+',k) for k in keys)
        rows=sql(container,f"SELECT * FROM lottery.`{name}` ORDER BY "+','.join(f'`{k}`' for k in keys))
        result[name]={'count':int(sql(container,f'SELECT COUNT(*) FROM lottery.`{name}`')),
                      'sha256':hashlib.sha256(rows).hexdigest()}
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-container',required=True)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    os.umask(0o077)
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    source=args.source_container
    clone='lottery-migration-audit-'+secrets.token_hex(5)
    report={'source_container':source,'clone_container':clone,'source_writes':False}
    before=signature(source)
    dump=run('docker','exec',source,'sh','-c',
             'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysqldump -uroot --single-transaction --no-tablespaces --set-gtid-purged=OFF --databases lottery')
    (output/'lottery.sql').write_bytes(dump)
    artifact_dir=Path('runtime/artifacts')
    run('tar','-czf',str(output/'artifacts.tar.gz'),'-C',str(artifact_dir.parent),'artifacts')
    artifact_hashes={str(p.relative_to(artifact_dir)):hashlib.sha256(p.read_bytes()).hexdigest() for p in artifact_dir.rglob('*') if p.is_file()}
    image=run('docker','inspect','--format','{{.Image}}',source).decode().strip()
    password=secrets.token_hex(24);env={**os.environ,'MYSQL_ROOT_PASSWORD':password}
    created=False
    try:
        run('docker','run','-d','--name',clone,'--memory','512m','-p','127.0.0.1::3306',
            '-e','MYSQL_ROOT_PASSWORD','-e','MYSQL_ROOT_HOST=%',image,
            '--innodb-buffer-pool-size=128M','--max-connections=20',env=env)
        created=True
        for attempt in range(90):
            try: sql(clone,'SELECT 1');break
            except subprocess.CalledProcessError: time.sleep(1)
        else: raise RuntimeError('Disposable database did not become ready')
        sql(clone,dump.decode())
        assert signature(clone)==before,'Restored copy differs from captured source; source may have changed'
        port=int(run('docker','port',clone,'3306').decode().strip().rsplit(':',1)[1])
        import lottery.db as db
        target=create_engine(URL.create('mysql+pymysql',username='root',password=password,host='127.0.0.1',port=port,database='lottery'))
        previous=db.engine;db.engine=lambda:target
        try:
            cfg=Config('backend/alembic.ini');command.upgrade(cfg,'head');command.upgrade(cfg,'head')
        finally:
            db.engine=previous;target.dispose()
        assert sql(clone,'SELECT version_num FROM lottery.alembic_version').strip()==b'005'
        assert signature(clone)==before,'Migration changed business rows'
        report['migration_preserved_business_rows']=True
        # Exercise detection and recovery only inside the disposable copy.
        sql(clone,"UPDATE lottery.predictions SET tickets=JSON_ARRAY()")
        if before['predictions']['count']:
            assert signature(clone)!=before
        sql(clone,'DROP DATABASE lottery')
        sql(clone,dump.decode())
        assert signature(clone)==before
        report['restored_business_rows']=True
        restored=output/'restored-artifacts';restored.mkdir()
        run('tar','-xzf',str(output/'artifacts.tar.gz'),'-C',str(restored))
        restored_hashes={str(p.relative_to(restored/'artifacts')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (restored/'artifacts').rglob('*') if p.is_file()}
        assert restored_hashes==artifact_hashes
        report.update({'artifact_count':len(artifact_hashes),'artifacts_restored':True,'tables':before,
                       'dump_sha256':hashlib.sha256(dump).hexdigest(),'source_schema_version':sql(source,'SELECT version_num FROM lottery.alembic_version').decode().strip()})
    finally:
        if created: run('docker','rm','-f','-v',clone)
    (output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('tables','clone_container')},ensure_ascii=False))

if __name__=='__main__':main()
