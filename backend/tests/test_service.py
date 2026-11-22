import os
from fastapi.testclient import TestClient
from app.service import app

def test_health_and_models():
 with TestClient(app) as c:
  assert c.get('/health').status_code==200
  m=c.get('/api/v1/models').json()
  assert any(x['id']=='nbc-vision-1' for x in m)
  assert any(x['id']=='timken-core-3' for x in m)
  assert all(x['decision_threshold']==.8 for x in m)
def test_admin_denied():
 with TestClient(app) as c:assert c.get('/api/v1/studio/summary').status_code==403
