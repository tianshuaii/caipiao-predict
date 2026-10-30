"""Single-admin, revocable server sessions. Public GETs remain unauthenticated."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re
import secrets
import time
from typing import Annotated
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .db import session_factory
from .models import AdminSession, LoginThrottle

COOKIE='lottery_admin'
ITERATIONS=600000
TTL=8*60*60


def database():
    with session_factory()() as session:yield session

DB=Annotated[Session,Depends(database)]


def password_hash(password):
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def settings():
    username=os.environ.get('ADMIN_USERNAME','tian')
    encoded=os.environ.get('ADMIN_PASSWORD_HASH','')
    origin=os.environ.get('ADMIN_ORIGIN','http://127.0.0.1:9998')
    try:
        url=urlsplit(origin);port=url.port
    except ValueError:return None
    valid_origin=url.scheme in ('http','https') and bool(url.netloc) and not(url.path or url.query or url.fragment or url.username or url.password)
    local=url.hostname in ('127.0.0.1','localhost','::1')
    if not valid_origin or url.scheme!='https' and not local:return None
    if not username or not re.fullmatch(r'pbkdf2_sha256\$600000\$[0-9a-f]{32}\$[0-9a-f]{64}',encoded):return None
    return username,encoded,origin,url.scheme=='https'


def fingerprint(config):return hashlib.sha256('|'.join(map(str,config)).encode()).hexdigest()
def now():return datetime.now(timezone.utc).replace(tzinfo=None)
def csrf(raw):return hashlib.sha256(('csrf:'+raw).encode()).hexdigest()


def origin_check(request):
    config=settings()
    origin=config[2] if config else os.environ.get('ADMIN_ORIGIN','http://127.0.0.1:9998')
    if request.headers.get('origin')!=origin:raise HTTPException(403,'请求来源不允许')


def current_session(request,db):
    config=settings();raw=request.cookies.get(COOKIE,'')
    if not config or not re.fullmatch(r'[A-Za-z0-9_-]{43}',raw):return None
    row=db.get(AdminSession,hashlib.sha256(raw.encode()).hexdigest())
    if row and row.expires_at>now() and hmac.compare_digest(row.credential_hash,fingerprint(config)):return row
    return None


def access_control(request:Request,db:DB):
    if request.method in ('GET','HEAD','OPTIONS'):return
    if request.url.path=='/api/auth/login':
        origin_check(request);return
    if not current_session(request,db):raise HTTPException(401,'需要有效管理员会话')
    origin_check(request)
    if not hmac.compare_digest(request.headers.get('x-csrf-token',''),csrf(request.cookies[COOKIE])):
        raise HTTPException(403,'CSRF校验失败')


def throttle(request,db):
    # Do not trust client-supplied X-Forwarded-For. A proxy may share one bucket.
    key=hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
    bucket=int(time.time())//900
    db.execute(delete(LoginThrottle).where(LoginThrottle.bucket<bucket-1))
    row=db.get(LoginThrottle,key)
    if row is None:
        try:
            db.add(LoginThrottle(key=key,bucket=bucket,attempts=0));db.commit()
        except IntegrityError:db.rollback()
    db.execute(update(LoginThrottle).where(LoginThrottle.key==key,LoginThrottle.bucket<bucket).values(bucket=bucket,attempts=0))
    result=db.execute(update(LoginThrottle).where(LoginThrottle.key==key,LoginThrottle.bucket==bucket,LoginThrottle.attempts<10).values(attempts=LoginThrottle.attempts+1))
    db.commit()
    if result.rowcount!=1:raise HTTPException(429,'登录尝试过多，请15分钟后重试',headers={'Retry-After':'900'})


class Credentials(BaseModel):
    username:str=Field(min_length=1,max_length=100)
    password:str=Field(min_length=1,max_length=1024)

router=APIRouter(prefix='/api/auth')

@router.post('/login')
def login(body:Credentials,request:Request,response:Response,db:DB):
    config=settings()
    if not config:raise HTTPException(503,'管理员登录未配置或安全配置无效')
    throttle(request,db)
    username,encoded,origin,secure=config
    _,_,salt,expected=encoded.split('$')
    actual=hashlib.pbkdf2_hmac('sha256',body.password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    if not (hmac.compare_digest(actual,expected) and hmac.compare_digest(body.username.encode(),username.encode())):
        raise HTTPException(401,'账号或密码错误')
    old=current_session(request,db)
    if old:db.delete(old)
    db.execute(delete(AdminSession).where(AdminSession.expires_at<=now()))
    raw=secrets.token_urlsafe(32);expires=now()+timedelta(seconds=TTL)
    db.add(AdminSession(token_hash=hashlib.sha256(raw.encode()).hexdigest(),credential_hash=fingerprint(config),expires_at=expires));db.commit()
    response.set_cookie(COOKIE,raw,max_age=TTL,httponly=True,secure=secure,samesite='strict',path='/api')
    response.headers['Cache-Control']='no-store'
    return {'authenticated':True,'username':username,'csrf_token':csrf(raw),'expires_at':expires.isoformat()+'Z'}

@router.get('/session')
def session_view(request:Request,response:Response,db:DB):
    response.headers['Cache-Control']='no-store'
    row=current_session(request,db)
    if not row:return {'authenticated':False}
    return {'authenticated':True,'username':settings()[0],'csrf_token':csrf(request.cookies[COOKIE]),'expires_at':row.expires_at.isoformat()+'Z'}

@router.post('/logout')
def logout(request:Request,response:Response,db:DB):
    row=current_session(request,db)
    if row:db.delete(row);db.commit()
    response.delete_cookie(COOKIE,path='/api',httponly=True,secure=settings()[3],samesite='strict')
    response.headers['Cache-Control']='no-store'
    return {'authenticated':False}

if __name__=='__main__':
    from getpass import getpass
    password=getpass('新管理员密码（至少12位）: ')
    if len(password)<12:raise SystemExit('密码至少12位')
    if password!=getpass('再次输入: '):raise SystemExit('两次输入不一致')
    print('将以下哈希保存为 backend/.env 的 ADMIN_PASSWORD_HASH（不要提交环境文件）：')
    print(password_hash(password))
