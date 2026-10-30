#!/usr/bin/env python3
"""Danil Prostudy: zero-dependency web server, SQLite orders, admin and notifications.
Run: python server.py    (Python 3.10+)
"""
from __future__ import annotations
import csv
import hashlib
import hmac
import html
import io
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time
from datetime import datetime, timezone, date
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'

def load_env(path=ROOT / '.env'):
    if not path.is_file(): return
    for line in path.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        if line.startswith('export '): line=line[7:]
        if '=' not in line: continue
        key,val=line.split('=',1)
        key=key.strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',key): continue
        val=val.strip()
        if len(val)>1 and val[0] in ('"', "'") and val[-1]==val[0]: val=val[1:-1]
        os.environ.setdefault(key,val)

load_env()
HOST=os.getenv('HOST','127.0.0.1')
PORT=int(os.getenv('PORT','8080'))
DATA=Path(os.getenv('DATA_DIR') or str(ROOT / 'data')).resolve()
DATA.mkdir(parents=True,exist_ok=True)
DB=DATA / 'orders.sqlite3'
ADMIN_PASSWORD=os.getenv('ADMIN_PASSWORD','')
PUBLIC_URL=os.getenv('PUBLIC_URL','http://localhost:8080').rstrip('/')
IS_HTTPS=PUBLIC_URL.startswith('https://')
VALID_SERVICES={'Курсова робота','Дипломна робота','Магістерська робота','Правки та оформлення','Презентація','Інше завдання'}
VALID_STATUSES={'Нова','У роботі','Завершена','Скасована'}
VALID_MESSENGERS={'Telegram','Viber','WhatsApp'}
RATE_LOCK=threading.Lock()
RATE={}
LOG=logging.getLogger('prostudy')
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')


def db_connect():
    c=sqlite3.connect(DB,timeout=15)
    c.row_factory=sqlite3.Row
    c.execute('PRAGMA busy_timeout=15000')
    c.execute('PRAGMA foreign_keys=ON')
    return c


def init_db():
    with db_connect() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          name TEXT NOT NULL,
          contact TEXT NOT NULL,
          messenger TEXT NOT NULL DEFAULT 'Не вказано',
          service TEXT NOT NULL,
          deadline TEXT NOT NULL DEFAULT '',
          topic TEXT NOT NULL DEFAULT '',
          details TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'Нова',
          admin_note TEXT NOT NULL DEFAULT '',
          telegram_status TEXT NOT NULL DEFAULT 'skipped',
          email_status TEXT NOT NULL DEFAULT 'skipped'
        );
        CREATE INDEX IF NOT EXISTS idx_orders_date ON orders(created_at DESC);
        CREATE TABLE IF NOT EXISTS sessions(
          session_hash TEXT PRIMARY KEY,
          csrf TEXT NOT NULL,
          expires_at INTEGER NOT NULL
        );
        ''')
        # Existing databases may have been created before the messenger selector.
        cols={r['name'] for r in c.execute('PRAGMA table_info(orders)')}
        if 'messenger' not in cols:
            c.execute("ALTER TABLE orders ADD COLUMN messenger TEXT NOT NULL DEFAULT 'Не вказано'")


def rate_allowed(ip, category, limit, seconds):
    now=time.monotonic()
    key=(ip,category)
    with RATE_LOCK:
        hits=[t for t in RATE.get(key,[]) if now-t<seconds]
        if len(hits)>=limit:
            RATE[key]=hits
            return False
        hits.append(now)
        RATE[key]=hits
        if len(RATE)>3000:
            for k,v in list(RATE.items()):
                recent=[t for t in v if now-t<seconds]
                if not recent: RATE.pop(k,None)
        return True


def validate_order(data):
    if not isinstance(data,dict): raise ValueError('Некоректні дані заявки.')
    if data.get('website'): return None  # honeypot: pretend accepted without saving
    def field(name,maxlen):
        val=data.get(name,'')
        if not isinstance(val,str): raise ValueError('Перевірте заповнені поля.')
        val=val.strip()
        if len(val)>maxlen: raise ValueError('Одне з полів занадто довге.')
        return val
    name=field('name',80)
    contact=field('contact',160)
    messenger=field('messenger',20)
    service=field('service',100)
    topic=field('topic',200)
    details=field('details',3000)
    deadline=field('deadline',10)
    if len(name)<2: raise ValueError('Вкажи ім’я (від 2 символів).')
    if messenger not in VALID_MESSENGERS: raise ValueError('Обери Telegram, Viber або WhatsApp.')
    if messenger=='Telegram':
        if not re.fullmatch(r'@[A-Za-z0-9_]{5,32}',contact):
            raise ValueError('Вкажи свій Telegram-нік у форматі @username (від 5 символів).')
    else:
        if not re.fullmatch(r'\+[0-9()\s-]+',contact) or not 8<=len(re.sub(r'\D','',contact))<=15:
            raise ValueError('Для Viber або WhatsApp потрібен номер із кодом країни, наприклад +380 99 123 45 67.')
    if service not in VALID_SERVICES: raise ValueError('Обери тип завдання зі списку.')
    if deadline:
        try: parsed=date.fromisoformat(deadline)
        except ValueError: raise ValueError('Некоректна дата дедлайну.')
        if parsed<datetime.now().date(): raise ValueError('Дедлайн не може бути в минулому.')
    return dict(name=name,contact=contact,messenger=messenger,service=service,deadline=deadline,topic=topic,details=details)


def telegram_notify(order):
    token=os.getenv('TELEGRAM_BOT_TOKEN','').strip()
    chat=os.getenv('TELEGRAM_CHAT_ID','').strip()
    if not token or not chat:return 'skipped'
    def e(val): return html.escape(str(val or '—'))
    content=(f'🟣 <b>НОВА ЗАЯВКА #{order["id"]}</b>\n\n'
        f'👤 <b>Ім’я:</b> {e(order["name"])}\n'
        f'📱 <b>Куди написати:</b> {e(order["messenger"])} — {e(order["contact"])}\n'
        f'📘 <b>Послуга:</b> {e(order["service"])}\n'
        f'📆 <b>Дедлайн:</b> {e(order["deadline"])}\n'
        f'📌 <b>Тема:</b> {e(order["topic"])}\n'
        f'💬 <b>Деталі:</b> {e(order["details"][:1800])}\n\n'
        f'📋 {e(PUBLIC_URL)}/admin')
    payload=json.dumps({'chat_id':chat,'text':content,'parse_mode':'HTML','disable_web_page_preview':True}).encode('utf-8')
    req=Request('https://api.telegram.org/bot'+token+'/sendMessage',data=payload,headers={'Content-Type':'application/json'},method='POST')
    try:
        with urlopen(req,timeout=8) as response:
            result=json.loads(response.read(2048))
            if not result.get('ok'): raise RuntimeError('Telegram API returned not ok')
        return 'sent'
    except (HTTPError,URLError,OSError,RuntimeError,ValueError) as exc:
        LOG.warning('Telegram delivery failed for #%s: %s',order['id'],type(exc).__name__)
        return 'failed'


def email_notify(order):
    host=os.getenv('SMTP_HOST','')
    to=os.getenv('NOTIFY_EMAIL_TO','')
    sender=os.getenv('SMTP_FROM','')
    if not (host and to and sender):return 'skipped'
    msg=EmailMessage()
    msg['Subject']=f'Нова заявка #{order["id"]} — Prostudy'
    msg['From']=sender
    msg['To']=to
    msg.set_content('\n'.join([f'Заявка #{order["id"]}',f'Ім’я: {order["name"]}',f'Месенджер: {order["messenger"]}',f'Контакт: {order["contact"]}',f'Послуга: {order["service"]}',f'Дедлайн: {order["deadline"]}',f'Тема: {order["topic"]}',f'Деталі: {order["details"]}',PUBLIC_URL+'/admin']))
    try:
        port=int(os.getenv('SMTP_PORT','587'))
        context=ssl.create_default_context()
        if port==465: smtp=smtplib.SMTP_SSL(host,port,timeout=9,context=context)
        else: smtp=smtplib.SMTP(host,port,timeout=9)
        with smtp:
            if port!=465: smtp.starttls(context=context)
            if os.getenv('SMTP_USER'): smtp.login(os.getenv('SMTP_USER',''),os.getenv('SMTP_PASSWORD',''))
            smtp.send_message(msg)
        return 'sent'
    except Exception as exc:
        LOG.warning('Email delivery failed for #%s: %s',order['id'],type(exc).__name__)
        return 'failed'


def notify(order):
    # Order is saved BEFORE notifying. Telegram/email failures do not erase it.
    telegram=telegram_notify(order)
    email=email_notify(order)
    with db_connect() as c:
        c.execute('UPDATE orders SET telegram_status=?,email_status=? WHERE id=?',(telegram,email,order['id']))
    return telegram,email


def session_from_request(handler):
    try:
        cookie=SimpleCookie()
        cookie.load(handler.headers.get('Cookie',''))
        token=cookie['prostudy_session'].value
        if len(token)>160:return None
    except Exception:
        return None
    with db_connect() as c:
        row=c.execute('SELECT csrf,expires_at FROM sessions WHERE session_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if row and row['expires_at']>time.time():return {'token':token,'csrf':row['csrf']}
    return None


class Handler(BaseHTTPRequestHandler):
    server_version='ProstudyServer/1.0'
    def log_message(self,fmt,*args):LOG.info('%s %s',self.address_string(),fmt%args)
    def do_HEAD(self):
        path=urlparse(self.path).path
        if path in ('/','/index.html','/health'):
            self.base_headers(200,'text/html; charset=utf-8',0)
        else:
            self.base_headers(404,'text/plain; charset=utf-8',0)
    def base_headers(self,status=200,content_type='text/html; charset=utf-8',length=None,other=None):
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','strict-origin-when-cross-origin')
        self.send_header('Cache-Control','no-store' if not content_type.startswith(('image/','text/css','application/javascript')) else 'public,max-age=300')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; form-action 'self'; base-uri 'self'; frame-ancestors 'none'")
        if length is not None:self.send_header('Content-Length',str(length))
        for k,v in (other or {}).items():self.send_header(k,v)
        self.end_headers()
    def send_bytes(self,data,status=200,content_type='text/html; charset=utf-8',other=None):
        self.base_headers(status,content_type,len(data),other)
        self.wfile.write(data)
    def send_text(self,text,status=200,content_type='text/html; charset=utf-8',other=None):
        self.send_bytes(text.encode('utf-8'),status,content_type,other)
    def json(self,obj,status=200,other=None):
        self.send_text(json.dumps(obj,ensure_ascii=False),status,'application/json; charset=utf-8',other)
    def error(self,msg,status=400):self.json({'error':msg},status)
    def redirect(self,to):
        self.base_headers(302,'text/plain; charset=utf-8',0,{'Location':to})
    def read_json(self):
        if not self.headers.get('Content-Type','').lower().startswith('application/json'):raise ValueError('Очікуються дані у форматі JSON.')
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:raise ValueError('Некоректний запит.')
        if length<1 or length>16384:raise ValueError('Заявка завелика або порожня.')
        try:return json.loads(self.rfile.read(length).decode('utf-8'))
        except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('Некоректний формат даних.')
    def serve_static(self,path):
        # Only exact files inside the public static directory may be served.
        relative=path.removeprefix('/static/')
        target=(STATIC/relative).resolve()
        if not target.is_relative_to(STATIC.resolve()) or not target.is_file():return self.send_text('Не знайдено',404)
        content_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if content_type.startswith('text/') or content_type=='application/javascript': content_type+='; charset=utf-8'
        return self.send_bytes(target.read_bytes(),200,content_type)
    def require_admin(self):
        session=session_from_request(self)
        if not session:self.error('Потрібна авторизація.',401)
        return session
    def require_csrf(self,sess):
        token=self.headers.get('X-CSRF-Token','')
        if not hmac.compare_digest(token,sess['csrf']):
            self.error('Невірний захисний токен.',403);return False
        return True

    def do_GET(self):
        path=urlparse(self.path).path
        if path=='/' or path=='/index.html':return self.serve_static('/static/index.html')
        if path.startswith('/static/'):return self.serve_static(path)
        if path=='/health':return self.json({'ok':True})
        if path=='/privacy':return self.serve_static('/static/privacy.html')
        if path=='/admin/login':
            if session_from_request(self):return self.redirect('/admin')
            return self.serve_static('/static/login.html')
        if path=='/admin':
            if not session_from_request(self):return self.redirect('/admin/login')
            return self.serve_static('/static/admin.html')
        if path=='/api/admin/session':
            sess=self.require_admin()
            if sess:return self.json({'csrf':sess['csrf']})
            return
        if path=='/api/admin/orders':
            if not self.require_admin():return
            q=parse_qs(urlparse(self.path).query)
            status=q.get('status',[''])[0]
            search=q.get('q',[''])[0][:160]
            page=max(1,min(100000,int(q.get('page',['1'])[0]) if q.get('page',['1'])[0].isdigit() else 1))
            limit=30
            conditions=[];params=[]
            if status in VALID_STATUSES:conditions.append('status=?');params.append(status)
            if search:
                conditions.append('(name LIKE ? OR contact LIKE ? OR topic LIKE ? OR CAST(id AS TEXT)=?)')
                params.extend([f'%{search}%',f'%{search}%',f'%{search}%',search])
            where=' WHERE '+' AND '.join(conditions) if conditions else ''
            with db_connect() as c:
                total=c.execute('SELECT COUNT(*) FROM orders'+where,params).fetchone()[0]
                rows=c.execute('SELECT * FROM orders'+where+' ORDER BY id DESC LIMIT ? OFFSET ?',params+[limit,(page-1)*limit]).fetchall()
                stats=dict(c.execute('SELECT status,COUNT(*) n FROM orders GROUP BY status').fetchall())
                overall=c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
            return self.json({'orders':[dict(r) for r in rows],'total':total,'overall':overall,'page':page,'pages':max(1,(total+limit-1)//limit),'stats':stats})
        if path=='/api/admin/export':
            if not self.require_admin():return
            out=io.StringIO(newline='')
            writer=csv.writer(out)
            cols=['id','created_at','name','messenger','contact','service','deadline','topic','details','status','admin_note','telegram_status','email_status']
            writer.writerow(cols)
            with db_connect() as c:
                for row in c.execute('SELECT '+','.join(cols)+' FROM orders ORDER BY id DESC'):
                    # Prevent spreadsheet formula injection for user-controlled CSV fields.
                    writer.writerow([("'"+str(v) if str(v).lstrip().startswith(('=','+','-','@','\t','\r')) else v) for v in row])
            payload=('\ufeff'+out.getvalue()).encode('utf-8')
            return self.send_bytes(payload,200,'text/csv; charset=utf-8',{'Content-Disposition':'attachment; filename="prostudy-orders.csv"'})
        return self.send_text('Сторінку не знайдено',404)

    def do_POST(self):
        path=urlparse(self.path).path
        if path=='/api/orders':
            ip=self.client_address[0]
            if not rate_allowed(ip,'orders',6,600):return self.error('Забагато запитів. Спробуй пізніше.',429)
            try:
                data=validate_order(self.read_json())
                if data is None:return self.json({'id':0,'ok':True},201)
                created=datetime.now(timezone.utc).isoformat(timespec='seconds')
                with db_connect() as c:
                    cur=c.execute('''INSERT INTO orders(created_at,name,messenger,contact,service,deadline,topic,details)
                      VALUES(?,?,?,?,?,?,?,?)''',(created,data['name'],data['messenger'],data['contact'],data['service'],data['deadline'],data['topic'],data['details']))
                    order_id=cur.lastrowid
                data['id']=order_id
                notify(data)
                return self.json({'id':order_id,'ok':True},201)
            except ValueError as exc:return self.error(str(exc),400)
            except Exception:
                LOG.exception('Could not save order')
                return self.error('Не вдалося зберегти заявку. Спробуй ще раз.',500)
        if path=='/api/admin/login':
            if not rate_allowed(self.client_address[0],'login',8,900):return self.error('Забагато спроб. Спробуйте пізніше.',429)
            if not ADMIN_PASSWORD:return self.error('Адмінка не налаштована. Задайте ADMIN_PASSWORD у .env.',503)
            try:data=self.read_json()
            except ValueError as exc:return self.error(str(exc))
            password=data.get('password','') if isinstance(data,dict) else ''
            if not isinstance(password,str) or not hmac.compare_digest(password,ADMIN_PASSWORD):return self.error('Невірний пароль.',401)
            session_token=secrets.token_urlsafe(40)
            csrf=secrets.token_urlsafe(32)
            expiry=int(time.time())+12*3600
            with db_connect() as c:
                c.execute('DELETE FROM sessions WHERE expires_at<?',(int(time.time()),))
                c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(session_token.encode()).hexdigest(),csrf,expiry))
            cookie=f'prostudy_session={session_token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200'
            if IS_HTTPS:cookie+='; Secure'
            return self.json({'ok':True},200,{'Set-Cookie':cookie})
        if path=='/api/admin/logout':
            sess=self.require_admin()
            if not sess or not self.require_csrf(sess):return
            with db_connect() as c:c.execute('DELETE FROM sessions WHERE session_hash=?',(hashlib.sha256(sess['token'].encode()).hexdigest(),))
            return self.json({'ok':True},200,{'Set-Cookie':'prostudy_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0'+('; Secure' if IS_HTTPS else '')})
        if path.startswith('/api/admin/orders/'):
            sess=self.require_admin()
            if not sess or not self.require_csrf(sess):return
            try:
                identifier=int(path.rsplit('/',1)[1]);data=self.read_json()
                if identifier<1:raise ValueError()
            except (ValueError,TypeError):return self.error('Некоректні дані.')
            if not isinstance(data,dict):return self.error('Некоректні дані.')
            status=data.get('status')
            note=data.get('admin_note')
            if status not in VALID_STATUSES or not isinstance(note,str) or len(note)>3000:return self.error('Некоректний статус або нотатка.')
            with db_connect() as c:
                cur=c.execute('UPDATE orders SET status=?,admin_note=? WHERE id=?',(status,note.strip(),identifier))
                if not cur.rowcount:return self.error('Заявку не знайдено.',404)
            return self.json({'ok':True})
        return self.error('Не знайдено',404)


def main():
    init_db()
    if not ADMIN_PASSWORD:LOG.warning('ADMIN_PASSWORD not set: admin login disabled')
    if not (os.getenv('TELEGRAM_BOT_TOKEN') and os.getenv('TELEGRAM_CHAT_ID')):LOG.warning('Telegram alerts disabled: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID')
    httpd=ThreadingHTTPServer((HOST,PORT),Handler)
    LOG.info('Serving http://%s:%s | DB: %s',HOST,PORT,DB)
    try:httpd.serve_forever()
    except KeyboardInterrupt:pass
    finally:httpd.server_close()

if __name__=='__main__':main()
