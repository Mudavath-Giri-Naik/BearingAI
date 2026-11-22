"""Dedicated background worker: trains candidates without changing live models."""
import time,json,uuid,traceback,hashlib
from pathlib import Path
import numpy as np,pandas as pd,joblib,torch
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import confusion_matrix
from catboost import CatBoostClassifier
from .service import ROOT,db,utc,record,load_predict,THRESHOLD,SpectralCNN
from .features import parse,features,GRID

def compute(y,s):
 y=np.asarray(y,dtype=int);p=(np.asarray(s)>=THRESHOLD).astype(int)
 tn,fp,fn,tp=confusion_matrix(y,p,labels=[0,1]).ravel()
 return {'n':int(len(y)),'correct':int((p==y).sum()),'accuracy':float((p==y).mean()),'bad_recall':float(tp/max(1,tp+fn)),'good_specificity':float(tn/max(1,tn+fp)),'tp':int(tp),'tn':int(tn),'fp':int(fp),'fn':int(fn)}
def signal(raw):
 f,m=parse(raw);a=np.interp(GRID,f,m).astype('float32');lo=np.log10(np.maximum(a,1e-8));return np.stack([np.clip(lo,-8,1),np.clip((lo-lo.mean())/(lo.std()+1e-6),-6,6)]).astype('float32')
def train_cnn(X,y,epochs=15):
 torch.set_num_threads(2);torch.manual_seed(113);m=SpectralCNN();o=torch.optim.AdamW(m.parameters(),lr=.001,weight_decay=.03);loss=torch.nn.BCEWithLogitsLoss();x=torch.tensor(np.stack(X));t=torch.tensor(y,dtype=torch.float32)
 for ep in range(epochs):
  m.train();rng=np.random.default_rng(113+ep)
  for idx in np.array_split(rng.permutation(len(y)),max(1,int(np.ceil(len(y)/32)))):
   o.zero_grad();l=loss(m(x[idx]),t[idx]);l.backward();o.step()
 m.eval();return m
def scores_cnn(m,X):
 with torch.inference_mode():return torch.sigmoid(m(torch.tensor(np.stack(X)))).numpy()
def process(j):
 brand=j['company'];fam=j['family'];did=j['dataset_id'];uid=j['id']
 manifest=pd.read_csv(ROOT/'seed'/'split_manifest.csv'); subset=manifest[manifest.brand==brand]
 with db() as c:meta=json.loads(c.execute('SELECT stats FROM datasets WHERE id=?',(did,)).fetchone()[0])
 rows=[]
 for r in subset.itertuples():
  path=ROOT/'seed'/r.path
  if not path.exists():continue
  rows.append((int(r.label),str(r.group),r.split,path.read_bytes(),'seed'))
 for item in meta['items']:
  path=ROOT/'uploads'/did/item['file']
  # New upload records are grouped by their original directory, not individual CSV.
  import re
  stem=item['original_path'];g=re.search(r'(?:NBC|TIMKEN)[_\s-]?(\d{4,})',stem,re.I)
  group=('new-'+did+'-'+g.group(1)) if g else ('new-'+did+'-'+Path(stem).stem.rsplit('_SIG',1)[0])
  rows.append((item['label'],group,'new',path.read_bytes(),'new'))
 # Shared validation: original 'test' is not used for fitting, threshold tuning or choosing candidates.
 dev=[r for r in rows if r[2]!='test'];test=[r for r in rows if r[2]=='test']
 y=np.asarray([r[0] for r in dev]);groups=np.asarray([r[1] for r in dev]);
 if len(set(groups))<8 or len(set(y))<2:raise RuntimeError('Insufficient unique bearings/classes')
 splitter=GroupShuffleSplit(n_splits=1,test_size=.22,random_state=2026);tr,va=next(splitter.split(dev,y,groups))
 if fam=='core':
  feature_rows=[features(r[3]) for r in dev];X=pd.DataFrame(feature_rows).replace([np.inf,-np.inf],np.nan).fillna(0)
  def fit(idx):
   m=CatBoostClassifier(iterations=220,depth=5,learning_rate=.04,l2_leaf_reg=5,loss_function='Logloss',verbose=False,random_seed=2026,thread_count=2)
   m.fit(X.iloc[idx],y[idx]);return m
  candidate=fit(tr);candidate_scores=candidate.predict_proba(X.iloc[va])[:,1]
  with db() as c:active=c.execute("SELECT * FROM models WHERE company=? AND status='active'",(brand,)).fetchone()
  active_scores=np.array([load_predict(active,dev[int(i)][3])[0] for i in va])
  selection={'candidate':compute(y[va],candidate_scores),'active':compute(y[va],active_scores)}
  full=fit(np.arange(len(dev)))
  fset=list(X.columns);ref=X.median().to_dict()
  artifact={'model':full,'features':fset,'brand':brand,'algorithm':'catboost','version':'trained-'+uid,'threshold':THRESHOLD,'reference_features':ref}
  filename=brand.lower()+'-core-'+uid+'.joblib';joblib.dump(artifact,ROOT/'models'/filename)
  def score_test():return full.predict_proba(pd.DataFrame([features(r[3]) for r in test])[fset])[:,1]
 else:
  X=[signal(r[3]) for r in dev];candidate=train_cnn([X[i] for i in tr],y[tr],epochs=14)
  candidate_scores=scores_cnn(candidate,[X[i] for i in va]);
  with db() as c:active=c.execute("SELECT * FROM models WHERE company=? AND status='active'",(brand,)).fetchone()
  active_scores=np.array([load_predict(active,dev[int(i)][3])[0] for i in va])
  selection={'candidate':compute(y[va],candidate_scores),'active':compute(y[va],active_scores)}
  full=train_cnn(X,y,epochs=14);filename=brand.lower()+'-vision-'+uid+'.pt'
  torch.save({'state_dict':full.state_dict(),'architecture':'SpectralCNN','training_epochs':14},ROOT/'models'/filename)
  def score_test():return scores_cnn(full,[signal(r[3]) for r in test])
 benchmark=compute([r[0] for r in test],score_test()) if test else None
 metrics={'development_validation':selection,'previously_exposed_benchmark':benchmark,'warning':'Selection metrics are based on one grouped development split. Protected old test files are evaluation-only and previously examined. New blind testing is required.','data':{'original_dev':sum(r[4]=='seed' for r in dev),'new':sum(r[4]=='new' for r in dev)}}
 modelid=brand.lower()+'-'+fam+'-'+uid;name=('Pulse Vision' if fam=='vision' else 'Pulse Core')+' · '+uid[-6:]
 with db() as c:
  c.execute('INSERT INTO models VALUES(?,?,?,?,?,?,?,?,?,?)',(modelid,brand,name,'cnn' if fam=='vision' else 'feature',uid,filename,'candidate',json.dumps(metrics),utc(),did))
  c.execute('UPDATE jobs SET status=?,candidate_model=?,logs=?,updated_at=? WHERE id=?',('completed',modelid,'Training complete. Candidate preserved; manual promotion required.',utc(),uid))
  record(c,'training_completed',{'job_id':uid,'model_id':modelid,'validation':selection})
def run():
 from .service import init_db,AUTH_MODE
 if AUTH_MODE!='local':raise RuntimeError('Supabase production worker queue is not yet connected; refusing to poll local SQLite')
 init_db();print('BearingAI training worker started',flush=True)
 while True:
  with db() as c:
   r=c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
   if r:
    c.execute('UPDATE jobs SET status=?,logs=?,updated_at=? WHERE id=?',('running','Preparing features and grouped validation',utc(),r['id']))
  if not r:time.sleep(2);continue
  try:process(dict(r))
  except Exception as e:
   with db() as c:
    c.execute('UPDATE jobs SET status=?,logs=?,updated_at=? WHERE id=?',('failed',str(e)+'\n'+traceback.format_exc()[-3000:],utc(),r['id']));record(c,'training_failed',{'job_id':r['id'],'error':str(e)})
if __name__=='__main__':run()
