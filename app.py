import os, sqlite3, secrets, hashlib, hmac, json, re, time, mimetypes
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
STATIC = BASE / 'static'
UPLOADS = STATIC / 'uploads'
DB = DATA / 'site.db'
DATA.mkdir(exist_ok=True)
for p in [UPLOADS/'images', UPLOADS/'audio', UPLOADS/'video']:
    p.mkdir(parents=True, exist_ok=True)

ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
SESSION_SECRET = os.getenv('SESSION_SECRET', secrets.token_urlsafe(32))
if not ADMIN_PASSWORD:
    pw_file = DATA / 'admin-password.txt'
    if pw_file.exists():
        ADMIN_PASSWORD = pw_file.read_text().strip()
    else:
        ADMIN_PASSWORD = 'Admin-' + secrets.token_urlsafe(9)
        pw_file.write_text(ADMIN_PASSWORD)

def password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

ADMIN_HASH = os.getenv('ADMIN_PASSWORD_SHA256', password_hash(ADMIN_PASSWORD))
app = FastAPI(title='Dr. Syed Farukh Shah – Spiritual Healer')
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site='lax', https_only=False, max_age=60*60*8)
app.mount('/static', StaticFiles(directory=str(STATIC)), name='static')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS media (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 type TEXT NOT NULL,
 title TEXT NOT NULL,
 description TEXT DEFAULT '',
 url TEXT NOT NULL,
 thumb TEXT DEFAULT '',
 external INTEGER DEFAULT 0,
 public INTEGER DEFAULT 1,
 sort INTEGER DEFAULT 0,
 created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS comments (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL,
 comment TEXT NOT NULL,
 status TEXT DEFAULT 'pending',
 ip_hash TEXT DEFAULT '',
 created_at INTEGER NOT NULL
);
'''
DEFAULT_SETTINGS = {
 'site_title':'Dr. Syed Farukh Shah – Spiritual Healer',
 'hero_name':'Dr. Syed Farukh Shah',
 'hero_subtitle':'Spiritual Healer',
 'hero_intro':'Trusted spiritual guidance, prayers, and compassionate support for families seeking clarity, peace, and healing.',
 'about_title':'Compassionate spiritual guidance with privacy and respect',
 'about_text':'This demo website is prepared for Dr. Syed Farukh Shah. Replace this text from the admin dashboard with the real biography, services, timings, and office details.',
 'phone':'Not configured yet',
 'whatsapp':'',
 'email':'',
 'address':'',
 'whatsapp_message':'Assalam-o-Alaikum, I am contacting you through the Dr. Syed Farukh Shah – Spiritual Healer website.',
 'contact_note':'For appointments and guidance, please contact through WhatsApp or phone once the real number is added.',
 'services':'Spiritual consultation\nFamily guidance\nPrayer support\nPersonal appointments',
}

def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    con = db(); con.executescript(SCHEMA)
    for k,v in DEFAULT_SETTINGS.items():
        con.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',(k,v))
    count = con.execute('SELECT COUNT(*) c FROM media').fetchone()['c']
    if count == 0:
        now=int(time.time())
        demo = [
          ('image','Demo healing poster','Placeholder poster. Replace or remove from admin dashboard.','/static/uploads/images/demo-poster-1.svg','',0,1,10,now),
          ('image','Demo consultation banner','Placeholder gallery image for layout testing.','/static/uploads/images/demo-poster-2.svg','',0,1,20,now),
          ('image','Demo prayer reminder','Placeholder gallery image for layout testing.','/static/uploads/images/demo-poster-3.svg','',0,1,30,now),
          ('video','Demo embedded video','Creative Commons Big Buck Bunny sample used only to test video display. Replace with real videos.','https://www.youtube-nocookie.com/embed/aqz-KE-bpKQ','/static/uploads/images/demo-video-thumb.svg',1,1,40,now),
          ('audio','Demo audio sample','Short generated chime for testing the audio player. Replace with real recording.','/static/uploads/audio/demo-chime.wav','',0,1,50,now),
        ]
        con.executemany('INSERT INTO media(type,title,description,url,thumb,external,public,sort,created_at) VALUES(?,?,?,?,?,?,?,?,?)', demo)
        con.execute('INSERT INTO comments(name,comment,status,created_at) VALUES(?,?,?,?)', ('Demo Visitor','This is a pending demo comment. Approve, hide, or delete it from the dashboard.','pending',now))
    con.commit(); con.close()
init_db()

SAFE_RE = re.compile(r'[^a-zA-Z0-9._-]+')
def clean_text(s, limit=1000):
    s = (s or '').strip()
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', s)
    return s[:limit]
def settings_dict(con=None):
    close=False
    if con is None: con=db(); close=True
    out={r['key']:r['value'] for r in con.execute('SELECT key,value FROM settings')}
    if close: con.close()
    return out
def public_media(kind, limit=None):
    con=db(); q='SELECT * FROM media WHERE type=? AND public=1 ORDER BY sort ASC,id DESC'
    rows=[dict(r) for r in con.execute(q+(f' LIMIT {int(limit)}' if limit else ''),(kind,))]
    con.close(); return rows
def require_admin(req: Request):
    if not req.session.get('admin'):
        raise HTTPException(401, 'Login required')
def wants_json(req: Request):
    return 'application/json' in req.headers.get('accept','')

def save_upload(file: UploadFile, folder: str, allowed: set):
    ext = Path(file.filename or '').suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, 'Unsupported file type')
    raw = file.file.read(60*1024*1024)
    if not raw: raise HTTPException(400, 'Empty upload')
    name = SAFE_RE.sub('-', Path(file.filename).stem).strip('-')[:40] or 'upload'
    unique = f'{int(time.time())}-{secrets.token_hex(4)}-{name}'
    if folder == 'images':
        src = UPLOADS/'images'/f'{unique}{ext}'
        src.write_bytes(raw)
        if Image:
            try:
                im = Image.open(src); im = ImageOps.exif_transpose(im).convert('RGB')
                im.thumbnail((1600,1600), Image.Resampling.LANCZOS)
                dest = UPLOADS/'images'/f'{unique}.webp'
                im.save(dest, 'WEBP', quality=82, method=6)
                src.unlink(missing_ok=True)
                return '/static/uploads/images/'+dest.name
            except Exception:
                src.unlink(missing_ok=True); raise HTTPException(400, 'Invalid image')
        return '/static/uploads/images/'+src.name
    dest = UPLOADS/folder/f'{unique}{ext}'
    dest.write_bytes(raw)
    return f'/static/uploads/{folder}/{dest.name}'

def render(page='home'):
    con=db(); s=settings_dict(con)
    imgs=public_media('image', 6 if page=='home' else None)
    vids=public_media('video', 3 if page=='home' else None)
    aud=public_media('audio', 3 if page=='home' else None)
    comments=[dict(r) for r in con.execute("SELECT name,comment,created_at FROM comments WHERE status='approved' ORDER BY id DESC LIMIT 20")]
    con.close()
    data=json.dumps({'settings':s,'images':imgs,'videos':vids,'audio':aud,'comments':comments,'page':page}, separators=(',',':'))
    return HTMLResponse(INDEX_HTML.replace('__DATA__', data))

@app.get('/', response_class=HTMLResponse)
def home(): return render('home')
@app.get('/gallery', response_class=HTMLResponse)
def gallery(): return render('gallery')
@app.get('/videos', response_class=HTMLResponse)
def videos(): return render('videos')
@app.get('/audio', response_class=HTMLResponse)
def audio(): return render('audio')
@app.get('/comments', response_class=HTMLResponse)
def comments_page(): return render('comments')
@app.get('/contact', response_class=HTMLResponse)
def contact(): return render('contact')
@app.get('/admin', response_class=HTMLResponse)
def admin(req: Request):
    if not req.session.get('admin'):
        return HTMLResponse(LOGIN_HTML)
    return HTMLResponse(ADMIN_HTML)
@app.post('/admin/login')
def login(req: Request, username: str = Form(...), password: str = Form(...)):
    if hmac.compare_digest(username, ADMIN_USER) and hmac.compare_digest(password_hash(password), ADMIN_HASH):
        req.session['admin']=True; return RedirectResponse('/admin', status_code=303)
    return HTMLResponse(LOGIN_HTML.replace('__ERR__','Invalid login'), status_code=401)
@app.post('/admin/logout')
def logout(req: Request):
    req.session.clear(); return RedirectResponse('/admin', status_code=303)
@app.get('/api/public')
def api_public():
    return {'settings':settings_dict(),'images':public_media('image'),'videos':public_media('video'),'audio':public_media('audio')}
@app.post('/api/comments')
def submit_comment(req: Request, name: str = Form(...), comment: str = Form(...), website: str = Form('')):
    if website: return {'ok': True, 'message':'Thank you. Your comment is awaiting moderation.'}
    name=clean_text(name,80); comment=clean_text(comment,800)
    if len(name)<2 or len(comment)<5: raise HTTPException(400,'Please enter a valid name and comment.')
    if len(re.findall(r'https?://|www\.', comment.lower()))>0: raise HTTPException(400,'Links are not allowed in comments.')
    ip=req.client.host if req.client else ''
    ip_hash=hashlib.sha256((ip+SESSION_SECRET).encode()).hexdigest()[:24]
    con=db(); recent=con.execute('SELECT COUNT(*) c FROM comments WHERE ip_hash=? AND created_at>?',(ip_hash,int(time.time())-60)).fetchone()['c']
    if recent>2: con.close(); raise HTTPException(429,'Please wait before submitting again.')
    con.execute('INSERT INTO comments(name,comment,status,ip_hash,created_at) VALUES(?,?,?,?,?)',(name,comment,'pending',ip_hash,int(time.time())))
    con.commit(); con.close(); return {'ok': True, 'message':'Thank you. Your comment is awaiting moderation.'}
@app.get('/api/admin')
def admin_data(req: Request):
    require_admin(req); con=db()
    data={'settings':settings_dict(con),'media':[dict(r) for r in con.execute('SELECT * FROM media ORDER BY type,sort,id DESC')], 'comments':[dict(r) for r in con.execute('SELECT * FROM comments ORDER BY id DESC LIMIT 200')]}
    con.close(); return data
@app.post('/api/admin/settings')
def update_settings(req: Request, payload: dict):
    require_admin(req); con=db()
    for k in DEFAULT_SETTINGS.keys():
        if k in payload: con.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,clean_text(str(payload[k]),3000)))
    con.commit(); con.close(); return {'ok':True}
@app.post('/api/admin/media')
def add_media(req: Request, type: str = Form(...), title: str = Form(...), description: str = Form(''), external_url: str = Form(''), public: int = Form(1), file: Optional[UploadFile] = File(None), thumb: Optional[UploadFile] = File(None)):
    require_admin(req); type=type.lower()
    if type not in ['image','video','audio']: raise HTTPException(400,'Bad media type')
    url=''; external=0; thumb_url=''
    if external_url.strip():
        url=clean_text(external_url,1000); external=1
    elif file:
        if type=='image': url=save_upload(file,'images',{'.jpg','.jpeg','.png','.webp'})
        elif type=='audio': url=save_upload(file,'audio',{'.mp3','.m4a','.aac','.ogg','.wav'})
        else: url=save_upload(file,'video',{'.mp4','.webm','.mov'})
    else: raise HTTPException(400,'Upload a file or provide an external URL')
    if thumb and thumb.filename: thumb_url=save_upload(thumb,'images',{'.jpg','.jpeg','.png','.webp'})
    con=db(); con.execute('INSERT INTO media(type,title,description,url,thumb,external,public,sort,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(type,clean_text(title,140),clean_text(description,900),url,thumb_url,external,1 if public else 0, int(time.time()), int(time.time())))
    con.commit(); con.close(); return {'ok':True}
@app.put('/api/admin/media/{mid}')
def edit_media(mid:int, req: Request, payload: dict):
    require_admin(req); con=db()
    fields=[]; vals=[]
    for k in ['title','description','url','thumb']:
        if k in payload: fields.append(f'{k}=?'); vals.append(clean_text(str(payload[k]),1000))
    for k in ['public','sort','external']:
        if k in payload: fields.append(f'{k}=?'); vals.append(int(payload[k]))
    if fields:
        vals.append(mid); con.execute('UPDATE media SET '+','.join(fields)+' WHERE id=?', vals); con.commit()
    con.close(); return {'ok':True}
@app.post('/api/admin/media/{mid}/replace')
def replace_media(mid:int, req: Request, file: UploadFile = File(...), thumb: Optional[UploadFile] = File(None)):
    require_admin(req)
    con=db(); row=con.execute('SELECT * FROM media WHERE id=?',(mid,)).fetchone()
    if not row:
        con.close(); raise HTTPException(404,'Media not found')
    kind=row['type']
    if kind=='image': url=save_upload(file,'images',{'.jpg','.jpeg','.png','.webp'})
    elif kind=='audio': url=save_upload(file,'audio',{'.mp3','.m4a','.aac','.ogg','.wav'})
    else: url=save_upload(file,'video',{'.mp4','.webm','.mov'})
    thumb_url=row['thumb'] or ''
    if thumb and thumb.filename:
        thumb_url=save_upload(thumb,'images',{'.jpg','.jpeg','.png','.webp'})
    con.execute('UPDATE media SET url=?, thumb=?, external=0 WHERE id=?',(url,thumb_url,mid)); con.commit(); con.close(); return {'ok':True,'url':url}
@app.delete('/api/admin/media/{mid}')
def delete_media(mid:int, req: Request):
    require_admin(req); con=db(); con.execute('DELETE FROM media WHERE id=?',(mid,)); con.commit(); con.close(); return {'ok':True}
@app.put('/api/admin/comments/{cid}')
def mod_comment(cid:int, req: Request, payload: dict):
    require_admin(req); status=payload.get('status','pending')
    if status not in ['pending','approved','hidden']: raise HTTPException(400,'Bad status')
    con=db(); con.execute('UPDATE comments SET status=? WHERE id=?',(status,cid)); con.commit(); con.close(); return {'ok':True}
@app.delete('/api/admin/comments/{cid}')
def delete_comment(cid:int, req: Request):
    require_admin(req); con=db(); con.execute('DELETE FROM comments WHERE id=?',(cid,)); con.commit(); con.close(); return {'ok':True}
@app.get('/health')
def health(): return {'ok': True}

INDEX_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dr. Syed Farukh Shah – Spiritual Healer</title><meta name="description" content="Professional spiritual guidance, healing and contact website for Dr. Syed Farukh Shah."><meta name="theme-color" content="#09261e"><link rel="preload" href="/static/style.css" as="style"><link rel="stylesheet" href="/static/style.css"></head><body><script>window.SITE=__DATA__</script><header class="top"><a class="brand" href="/" aria-label="Homepage"><span>Dr. Syed Farukh Shah</span><small>Spiritual Healer</small></a><button class="menu" aria-label="Open menu" onclick="document.body.classList.toggle('navopen')">☰</button><nav aria-label="Main navigation"><a href="/">Home</a><a href="/#about">About</a><a href="/gallery">Posters / Gallery</a><a href="/videos">Videos</a><a href="/audio">Audio</a><a href="/comments">Comments</a><a href="/contact">Contact</a></nav></header><main id="app"></main><a id="floatWa" class="float-wa" target="_blank" rel="noopener" aria-label="Contact on WhatsApp">WhatsApp</a><footer><b>Dr. Syed Farukh Shah – Spiritual Healer</b><p>Professional spiritual guidance website. Content is managed privately by the administrator.</p></footer><script src="/static/app.js" defer></script></body></html>'''
LOGIN_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin Login</title><link rel="stylesheet" href="/static/style.css"></head><body class="login"><form class="card loginbox" method="post" action="/admin/login"><h1>Admin Login</h1><p class="err">__ERR__</p><label>Username<input name="username" required autocomplete="username"></label><label>Password<input name="password" type="password" required autocomplete="current-password"></label><button class="btn">Login</button><a href="/">View website</a></form></body></html>'''
ADMIN_HTML = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin Dashboard</title><link rel="stylesheet" href="/static/style.css"></head><body><header class="top"><a class="brand" href="/admin"><span>Admin Dashboard</span><small>Dr. Syed Farukh Shah</small></a><nav><a href="/" target="_blank">View Site</a><form method="post" action="/admin/logout"><button class="linkbtn">Logout</button></form></nav></header><main class="admin"><section class="card"><h1>Website Settings</h1><form id="settingsForm" class="gridform"></form></section><section class="card"><h2>Add Media</h2><form id="mediaForm" enctype="multipart/form-data" class="gridform"><label>Type<select name="type"><option value="image">Poster / Image</option><option value="video">Video</option><option value="audio">Audio</option></select></label><label>Title<input name="title" required></label><label>Description<textarea name="description"></textarea></label><label>Upload file<input name="file" type="file"></label><label>External video/audio/embed URL<input name="external_url" placeholder="https://..."></label><label>Thumbnail for video/audio<input name="thumb" type="file" accept="image/*"></label><label class="check"><input name="public" type="checkbox" value="1" checked> Published</label><button class="btn">Add Media</button></form></section><section class="card"><h2>Manage Media</h2><div id="mediaList"></div></section><section class="card"><h2>Moderate Comments</h2><div id="commentList"></div></section></main><script src="/static/admin.js" defer></script></body></html>'''

if __name__ == '__main__':
    import uvicorn
    print('Admin username:', ADMIN_USER)
    print('Admin password source:', 'environment' if os.getenv('ADMIN_PASSWORD') else 'local data/admin-password.txt')
    uvicorn.run(app, host='0.0.0.0', port=int(os.getenv('PORT','8000')))
