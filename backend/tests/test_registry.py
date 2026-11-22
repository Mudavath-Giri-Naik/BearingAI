import shutil
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app import service


REPOSITORY_STORAGE = service.ROOT
APPROVED_FILES = ('nbc_cnn.pt', 'nbc_core_v3.joblib', 'timken_core_v3.joblib')


def test_approved_registry_and_real_csv_predictions(tmp_path, monkeypatch):
    storage = tmp_path / 'storage'
    models_dir = storage / 'models'
    models_dir.mkdir(parents=True)
    for filename in APPROVED_FILES:
        shutil.copyfile(REPOSITORY_STORAGE / 'models' / filename, models_dir / filename)
    monkeypatch.setattr(service, 'ROOT', storage)
    monkeypatch.setattr(service, 'DB', storage / 'registry.sqlite3')

    manifest = pd.read_csv(REPOSITORY_STORAGE / 'seed' / 'split_manifest.csv')
    samples = {}
    for company in ('NBC', 'TIMKEN'):
        row = manifest[(manifest.brand == company) & (manifest.split == 'train')].iloc[0]
        samples[company] = (REPOSITORY_STORAGE / 'seed' / row.path).read_bytes()

    with TestClient(service.app) as client:
        response = client.get('/api/v1/models')
        assert response.status_code == 200
        assert {item['id'] for item in response.json()} == set(service.PUBLIC_MODELS)
        assert {item['id'] for item in client.get('/api/v1/models?company=NBC').json()} == {
            'nbc-vision-1', 'nbc-core-3'
        }
        assert {item['id'] for item in client.get('/api/v1/models?company=TIMKEN').json()} == {
            'timken-core-3'
        }

        for company, model_id, filename in (
            ('NBC', 'nbc-vision-1', 'nbc_cnn.pt'),
            ('NBC', 'nbc-core-3', 'nbc_core_v3.joblib'),
            ('TIMKEN', 'timken-core-3', 'timken_core_v3.joblib'),
        ):
            result = client.post(
                '/api/v1/predict',
                data={'company': company, 'model': model_id},
                files={'file': (f'{company.lower()}-sample.csv', samples[company], 'text/csv')},
            )
            assert result.status_code == 200, result.text
            assert result.json()['model']['id'] == model_id
            assert result.json()['prediction'] in {'GOOD', 'BAD'}
            assert 0 <= result.json()['bad_score'] <= 1

        # A second initializer must remain idempotent and preserve exactly these IDs.
        service.init_db()
        with service.db() as conn:
            rows = conn.execute('SELECT id FROM models ORDER BY id').fetchall()
        assert [row['id'] for row in rows] == sorted(service.PUBLIC_MODELS)


def test_missing_or_changed_artifact_is_not_registered(tmp_path, monkeypatch):
    storage = tmp_path / 'storage'
    models_dir = storage / 'models'
    models_dir.mkdir(parents=True)
    shutil.copyfile(REPOSITORY_STORAGE / 'models' / 'nbc_cnn.pt', models_dir / 'nbc_cnn.pt')
    (models_dir / 'nbc_core_v3.joblib').write_bytes(b'not the approved artifact')
    monkeypatch.setattr(service, 'ROOT', storage)
    monkeypatch.setattr(service, 'DB', storage / 'registry.sqlite3')

    service.init_db()
    with service.db() as conn:
        rows = conn.execute('SELECT id FROM models').fetchall()
    assert [row['id'] for row in rows] == ['nbc-vision-1']
