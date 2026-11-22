"""BearingAI API: experimental classification, versioned artifacts and guarded studio operations."""
import os, json, sqlite3, io, hashlib, zipfile, uuid, time, threading, re, urllib.request, urllib.error
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
import numpy as np, pandas as pd, joblib, torch
from torch import nn
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from catboost import Pool
from .features import parse, features, GRID, InvalidSignal

ROOT=Path(os.environ.get('BEARING_STORAGE',Path(__file__).resolve().parents[2]/'storage')).resolve()
ROOT.mkdir(parents=True,exist_ok=True)
(ROOT/'models').mkdir(exist_ok=True);(ROOT/'uploads').mkdir(exist_ok=True)
DB=ROOT/'registry.sqlite3'; ADMIN_KEY=os.environ.get('BEARING_ADMIN_KEY','')
THRESHOLD=0.8
AUTH_MODE=os.environ.get('BEARING_AUTH_MODE','local').lower()
class SpectralCNN(nn.Module):
 def __init__(self):
  super().__init__(); self.conv=nn.Sequential(nn.Conv1d(2,16,9,padding=4),nn.BatchNorm1d(16),nn.GELU(),nn.MaxPool1d(2),nn.Conv1d(16,32,7,padding=3),nn.BatchNorm1d(32),nn.GELU(),nn.MaxPool1d(2),nn.Conv1d(32,48,5,padding=2),nn.BatchNorm1d(48),nn.GELU(),nn.AdaptiveAvgPool1d(12))
  self.fc=nn.Sequential(nn.Flatten(),nn.Dropout(.35),nn.Linear(48*12,32),nn.GELU(),nn.Dropout(.3),nn.Linear(32,1))
 def forward(self,x): return self.fc(self.conv(x)).squeeze(-1)

def utc(): return datetime.now(timezone.utc).isoformat()
@contextmanager
def db():
 c=sqlite3.connect(DB,timeout=30);c.row_factory=sqlite3.Row
 try:
  yield c;c.commit()
 finally:c.close()
def init_db():
 with db() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY,company TEXT NOT NULL,name TEXT NOT NULL,kind TEXT NOT NULL,version TEXT NOT NULL,path TEXT NOT NULL,status TEXT NOT NULL,metrics TEXT NOT NULL,created_at TEXT NOT NULL,training_dataset TEXT);
  CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY,name TEXT NOT NULL,company TEXT NOT NULL,path TEXT NOT NULL,stats TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,company TEXT NOT NULL,family TEXT NOT NULL,dataset_id TEXT NOT NULL,status TEXT NOT NULL,logs TEXT NOT NULL,candidate_model TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,event TEXT NOT NULL,detail TEXT NOT NULL,created_at TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS predictions(id TEXT PRIMARY KEY,company TEXT NOT NULL,model_id TEXT NOT NULL,label TEXT NOT NULL,score REAL NOT NULL,created_at TEXT NOT NULL);''')
  seeds=[('nbc-vision-1','NBC','Pulse Vision 1','cnn','1.0.0','nbc_cnn.pt',{'accuracy':.9,'bad_recall':.96,'good_specificity':.6,'test_n':30},'active'),('nbc-core-3','NBC','Pulse Core 3','feature','3.0.0','nbc_core_v3.joblib',{'accuracy':.8667,'bad_recall':.96,'good_specificity':.4,'test_n':30},'available'),('timken-core-3','TIMKEN','Pulse Core 3','feature','3.0.0','timken_core_v3.joblib',{'accuracy':.825,'bad_recall':.84375,'good_specificity':.75,'test_n':40},'active'),('nbc-legacy-1','NBC','Pulse Legacy 1','feature','1.0.0','nbc_legacy_v1.joblib',{'accuracy':.7333,'bad_recall':.72,'good_specificity':.8,'test_n':30},'available'),('timken-legacy-1','TIMKEN','Pulse Legacy 1','feature','1.0.0','timken_legacy_v1.joblib',{'accuracy':.625,'bad_recall':.5625,'good_specificity':.875,'test_n':40},'available')]
  for id,company,name,kind,version,path,metrics,status in seeds:
   if (ROOT/'models'/path).exists():c.execute('INSERT OR IGNORE INTO models VALUES(?,?,?,?,?,?,?,?,?,?)',(id,company,name,kind,version,path,status,json.dumps(metrics),utc(),'seed-dev'))
  c.execute("UPDATE models SET status='available' WHERE company='NBC' AND id='nbc-core-3' AND status='active' AND EXISTS (SELECT 1 FROM models WHERE id='nbc-vision-1' AND status='active')")
def admin(x_admin_key:str|None=Header(default=None),authorization:str|None=Header(default=None)):
 if AUTH_MODE=='supabase':
  base=os.environ.get('SUPABASE_URL','').rstrip('/');anon=os.environ.get('SUPABASE_ANON_KEY','')
  scheme,_,token=(authorization or '').partition(' ')
  if not base or not anon:raise HTTPException(503,'Supabase Auth is not configured')
  if scheme.lower()!='bearer' or not token:raise HTTPException(401,'Supabase sign-in required')
  try:
   req=urllib.request.Request(base+'/auth/v1/user',headers={'apikey':anon,'authorization':'Bearer '+token})
   with urllib.request.urlopen(req,timeout=8) as response:user=json.loads(response.read())
   uid=user.get('id')
   if not uid:raise ValueError('No user id')
   profile_req=urllib.request.Request(base+'/rest/v1/user_profiles?select=role,status&user_id=eq.'+uid,headers={'apikey':anon,'authorization':'Bearer '+token})
   with urllib.request.urlopen(profile_req,timeout=8) as response:profiles=json.loads(response.read())
  except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError,ValueError,TypeError):
   raise HTTPException(401,'Supabase session could not be verified')
  if not profiles or profiles[0].get('status')!='verified' or profiles[0].get('role') not in ('developer','admin'):
   raise HTTPException(403,'Verified developer access required')
  return uid
 if AUTH_MODE!='local':raise HTTPException(503,'Unsupported authentication mode')
 if not ADMIN_KEY or not x_admin_key or not __import__('hmac').compare_digest(x_admin_key,ADMIN_KEY):raise HTTPException(403,'Developer access required')
def record(c,event,detail):c.execute('INSERT INTO audit(event,detail,created_at) VALUES(?,?,?)',(event,json.dumps(detail),utc()))
def row_model(r):return {**{k:r[k] for k in ('id','company','name','kind','version','status','created_at','training_dataset')},'metrics':json.loads(r['metrics']),'decision_threshold':THRESHOLD}
app=FastAPI(title='BearingAI API',version='1.0.0',description='Experimental research system; NOT validated for industrial acceptance')
app.add_middleware(CORSMiddleware,allow_origins=[],allow_credentials=False,allow_methods=['GET','POST','DELETE'],allow_headers=['*'])
@app.on_event('startup')
def start():
 if AUTH_MODE!='local':
  raise RuntimeError('Supabase production runtime is not yet connected; refusing to start with an unsupported auth mode')
 init_db()
@app.get('/health')
def health():return {'status':'ok','database':DB.exists(),'disclaimer':'Research-only predictions'}
@app.get('/api/v1/models')
def models(company:str|None=None):
 with db() as c:
  rows=c.execute("SELECT * FROM models WHERE status IN ('active','available') ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END,name",()).fetchall()
 return [row_model(r) for r in rows if not company or r['company']==company.upper()]
@app.get('/api/v1/studio/models',dependencies=[Depends(admin)])
def studio_models():
 with db() as c:return [row_model(r) for r in c.execute('SELECT * FROM models ORDER BY created_at DESC').fetchall()]
def load_predict(r,raw):
 path=(ROOT/'models'/r['path']).resolve()
 if path.parent!=(ROOT/'models').resolve() or not path.is_file():raise HTTPException(503,'Model artifact unavailable')
 if r['kind']=='cnn':
  ckpt=torch.load(path,map_location='cpu',weights_only=True);m=SpectralCNN();m.load_state_dict(ckpt['state_dict']);m.eval()
  freq,mag=parse(raw);a=np.interp(GRID,freq,mag).astype('float32');lo=np.log10(np.maximum(a,1e-8));norm=(lo-lo.mean())/(lo.std()+1e-6)
  x=torch.from_numpy(np.stack([np.clip(lo,-8,1),np.clip(norm,-6,6)]).astype('float32'))[None]
  with torch.inference_mode():score=float(torch.sigmoid(m(x)).item())
  top=np.argsort(a)[-3:][::-1];ev=[{'feature':f'Peak near {GRID[i]:.1f} Hz','direction':'observed signal feature','value':round(float(a[i]),6)} for i in top]
 else:
  entry=joblib.load(path) # trusted, server-produced artifacts only
  f=features(raw);x=pd.DataFrame([{k:f[k] for k in entry['features']}]);m=entry['model'];score=float(m.predict_proba(x)[0,1])
  if entry['algorithm']=='catboost':
   impact=np.asarray(m.get_feature_importance(Pool(x),type='ShapValues'))[0,:-1]
  elif entry['algorithm']=='logistic':impact=m.named_steps['standardscaler'].transform(x)[0]*m.named_steps['logisticregression'].coef_[0]
  else:
   ref=entry.get('reference_features',{});base=score; impact=np.zeros(len(entry['features']))
   for i,k in enumerate(entry['features']):
    if k in ref:
     alt=x.copy();alt.iloc[0,i]=ref[k];impact[i]=base-float(m.predict_proba(alt)[0,1])
  top=np.argsort(np.abs(impact))[::-1][:5];ev=[{'feature':entry['features'][int(i)],'direction':'toward BAD' if impact[i]>0 else 'toward GOOD','value':round(float(impact[i]),5)} for i in top]
 return score,ev
@app.post('/api/v1/predict')
async def predict(company:str=Form(...),model:str|None=Form(None),file:UploadFile=File(...)):
 company=company.upper()
 if company not in ('NBC','TIMKEN'):raise HTTPException(422,'Company must be NBC or TIMKEN')
 if not file.filename or not file.filename.lower().endswith('.csv'):raise HTTPException(422,'Upload a CSV file')
 raw=await file.read(2_000_001)
 if len(raw)>2_000_000:raise HTTPException(413,'CSV exceeds 2 MB')
 with db() as c:
  r=c.execute('SELECT * FROM models WHERE id=? AND company=? AND status IN (\'active\',\'available\')',(model,company)).fetchone() if model else c.execute('SELECT * FROM models WHERE company=? AND status=\'active\'',(company,)).fetchone()
 if r is None:raise HTTPException(404,'No selectable model for this company')
 try:score,ev=load_predict(r,raw)
 except (InvalidSignal,ValueError) as e:raise HTTPException(422,str(e)) from e
 label='BAD' if score>=THRESHOLD else 'GOOD';pid=uuid.uuid4().hex
 with db() as c:c.execute('INSERT INTO predictions VALUES(?,?,?,?,?,?)',(pid,company,r['id'],label,score,utc()))
 return {'id':pid,'company':company,'model':{'id':r['id'],'name':r['name'],'version':r['version'],'algorithm':r['kind']},'prediction':label,'bad_score':round(score,6),'decision_threshold':THRESHOLD,'evidence':ev,'warning':'Research-only. Model scores are not calibrated defect probabilities. False GOOD/BAD predictions remain possible. CNN peaks are observed features, not causal explanations.'}
@app.get('/api/v1/studio/summary',dependencies=[Depends(admin)])
def summary():
 with db() as c:
  n=c.execute('SELECT COUNT(*) FROM datasets').fetchone()[0];j=c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0];p=c.execute('SELECT COUNT(*) FROM predictions').fetchone()[0]
  models=[row_model(r) for r in c.execute('SELECT * FROM models WHERE status=\'active\'').fetchall()]
 return {'datasets':n,'jobs':j,'predictions':p,'active_models':models}
@app.get('/api/v1/studio/datasets',dependencies=[Depends(admin)])
def datasets():
 with db() as c:return [{**dict(r),'stats':json.loads(r['stats'])} for r in c.execute('SELECT * FROM datasets ORDER BY created_at DESC').fetchall()]
@app.post('/api/v1/studio/datasets',dependencies=[Depends(admin)])
async def upload_dataset(company:str=Form(...),name:str=Form(...),file:UploadFile=File(...)):
 company=company.upper()
 if company not in ('NBC','TIMKEN') or not name.strip():raise HTTPException(422,'Company and dataset name required')
 if not file.filename or not file.filename.lower().endswith('.zip'):raise HTTPException(422,'Upload ZIP with GOOD/ and BAD/ CSV folders')
 raw=await file.read(60_000_001)
 if len(raw)>60_000_000:raise HTTPException(413,'ZIP exceeds 60 MB')
 try:z=zipfile.ZipFile(io.BytesIO(raw))
 except zipfile.BadZipFile:raise HTTPException(422,'Invalid ZIP file')
 rows=[];seen=set();total=0
 manifest=pd.read_csv(ROOT/'seed'/'split_manifest.csv');protected=set(manifest['hash'].astype(str));protected_bearings=set(manifest.loc[manifest['split']=='test','bearing'].astype(str).str.upper())
 for info in z.infolist():
  if info.is_dir():continue
  if len(rows)>=1500 or info.file_size>2_000_000:raise HTTPException(422,'Too many CSV files or oversized CSV')
  if not info.filename.lower().endswith('.csv'):continue
  parts=[p.upper() for p in Path(info.filename.replace('\\','/')).parts]
  labels=[p for p in parts if p in ('GOOD','BAD','REJECTED')]
  if not labels:raise HTTPException(422,'Each CSV must be under GOOD/ or BAD/ folder')
  if any(p in ('NBC','TIMKEN') and p!=company for p in parts):raise HTTPException(422,'ZIP contains another company')
  content=z.read(info);total+=len(content)
  if total>30_000_000:raise HTTPException(413,'Total uncompressed CSV bytes exceed 30 MB')
  try:parse(content)
  except InvalidSignal as e:raise HTTPException(422,f'{info.filename}: {e}')
  digest=hashlib.sha256(content).hexdigest()
  if digest in protected:raise HTTPException(422,'Upload overlaps existing seed dataset; original test bearings must remain excluded')
  found=re.search(r'(NBC|TIMKEN)[_\s-]?(\d{4,})',info.filename,re.I)
  bearing_id=(found.group(1)+'_'+found.group(2)).upper() if found else None
  if bearing_id in protected_bearings:raise HTTPException(422,'Bearing ID overlaps the frozen test set')
  if digest in seen:continue
  seen.add(digest);rows.append((1 if labels[-1] in ('BAD','REJECTED') else 0,info.filename,content,digest))
 if not rows or len(set(v[0] for v in rows))<2:raise HTTPException(422,'Include at least one GOOD and one BAD CSV')
 uid='data-'+uuid.uuid4().hex[:12];dest=ROOT/'uploads'/uid;dest.mkdir(parents=True)
 for i,(label,path,content,digest) in enumerate(rows): (dest/f'{i:05d}_{digest[:12]}.csv').write_bytes(content)
 meta={'files':len(rows),'good':sum(1 for r in rows if r[0]==0),'bad':sum(1 for r in rows if r[0]==1),'items':[{'file':f'{i:05d}_{r[3][:12]}.csv','label':r[0],'original_path':r[1],'sha256':r[3]} for i,r in enumerate(rows)]}
 with db() as c:
  c.execute('INSERT INTO datasets VALUES(?,?,?,?,?,?,?)',(uid,name,company,str(dest.relative_to(ROOT)),json.dumps(meta),'ready',utc()));record(c,'dataset_uploaded',{'id':uid,'company':company,'files':len(rows)})
 return {'id':uid,'name':name,'company':company,'stats':{'files':len(rows),'good':meta['good'],'bad':meta['bad']},'status':'ready'}
@app.get('/api/v1/studio/jobs',dependencies=[Depends(admin)])
def jobs():
 with db() as c:return [dict(r) for r in c.execute('SELECT * FROM jobs ORDER BY created_at DESC').fetchall()]
class TrainRequest(BaseModel):
 company:str
 family:str
 dataset_id:str
@app.post('/api/v1/studio/jobs',dependencies=[Depends(admin)])
def train(req:TrainRequest):
 if req.company not in ('NBC','TIMKEN') or req.family not in ('core','vision'):raise HTTPException(422,'Unsupported company or family')
 if req.family=='vision' and req.company!='NBC':raise HTTPException(422,'Only NBC Vision CNN currently supported')
 with db() as c:
  d=c.execute('SELECT * FROM datasets WHERE id=? AND company=? AND status=\'ready\'',(req.dataset_id,req.company)).fetchone()
  if not d:raise HTTPException(404,'Dataset not found for company')
  jid='job-'+uuid.uuid4().hex[:12];c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(jid,req.company,req.family,req.dataset_id,'queued','Queued for training',None,utc(),utc()));record(c,'training_queued',{'job':jid})
 return {'id':jid,'status':'queued'}
class ModelAction(BaseModel):
 model_id:str
@app.post('/api/v1/studio/models/promote',dependencies=[Depends(admin)])
def promote(a:ModelAction):
 with db() as c:
  r=c.execute('SELECT * FROM models WHERE id=?',(a.model_id,)).fetchone()
  if not r or r['status'] not in ('candidate','available','active'):raise HTTPException(404,'Model unavailable')
  c.execute("UPDATE models SET status='available' WHERE company=? AND status='active'",(r['company'],));c.execute("UPDATE models SET status='active' WHERE id=?",(a.model_id,));record(c,'model_promoted',{'model_id':a.model_id,'company':r['company']})
 return {'promoted':a.model_id,'company':r['company']}
@app.post('/api/v1/studio/models/archive',dependencies=[Depends(admin)])
def archive(a:ModelAction):
 with db() as c:
  r=c.execute('SELECT * FROM models WHERE id=?',(a.model_id,)).fetchone()
  if not r or r['status']=='active':raise HTTPException(409,'Cannot archive active or missing model')
  c.execute("UPDATE models SET status='archived' WHERE id=?",(a.model_id,));record(c,'model_archived',{'model_id':a.model_id})
 return {'archived':a.model_id}
@app.get('/api/v1/studio/audit',dependencies=[Depends(admin)])
def audit():
 with db() as c:return [dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100').fetchall()]
