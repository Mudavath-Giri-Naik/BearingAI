import os, io, zipfile, sqlite3
from fastapi.testclient import TestClient
from app.service import app,ROOT
import pandas as pd

def test_dataset_job_and_auth():
 m=pd.read_csv(ROOT/'seed'/'split_manifest.csv')
 # Freshly modified CSV samples are used only as an API plumbing test.
 contents=[]
 for label in (0,1):
  r=m[(m.brand=='NBC') & (m.label==label) & (m.split=='train')].iloc[0]
  frame=pd.read_csv(ROOT/'seed'/r.path,encoding='utf-8-sig');frame.iloc[:,1]=frame.iloc[:,1].astype(float)*1.001
  contents.append(('GOOD' if label==0 else 'BAD',frame.to_csv(index=False).encode()))
 archive=io.BytesIO()
 with zipfile.ZipFile(archive,'w') as z:
  for i,(label,content) in enumerate(contents):z.writestr(f'{label}/NBC_9988{i}1_SIG1.csv',content)
 archive.seek(0)
 with TestClient(app) as c:
  h={'x-admin-key':os.environ['BEARING_ADMIN_KEY']}
  r=c.post('/api/v1/studio/datasets',data={'company':'NBC','name':'Temporary functional test'},files={'file':('test.zip',archive.getvalue(),'application/zip')},headers=h)
  assert r.status_code==200,r.text
  did=r.json()['id'];j=c.post('/api/v1/studio/jobs',json={'company':'NBC','family':'core','dataset_id':did},headers=h)
  assert j.status_code==200,j.text
  assert j.json()['status']=='queued'
  # Cleanup temporary files and DB rows; worker has not run in this test.
  uid=j.json()['id'];
  import shutil
  with sqlite3.connect(ROOT/'registry.sqlite3') as db:
   db.execute('DELETE FROM jobs WHERE id=?',(uid,));db.execute('DELETE FROM datasets WHERE id=?',(did,));db.execute('DELETE FROM audit WHERE detail LIKE ?',('%'+did+'%',))
  shutil.rmtree(ROOT/'uploads'/did)
