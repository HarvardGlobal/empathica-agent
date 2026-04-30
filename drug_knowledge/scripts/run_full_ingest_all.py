from __future__ import annotations
import sys
sys.path.insert(0,'.')
from app.config import settings
from app.db import SessionLocal, init_db
from app.services.ingestion.dailymed_client import DailyMedClient
from app.services.ingestion.openfda_client import OpenFDAClient
from app.services.ingestion.parser import LabelParser
from app.services.ingestion.normalizer import LabelNormalizer
from app.services.ingestion.loader import DBLoader
from app.services.ingestion.updater import IngestionUpdater

print('START full ingest all')
init_db()
db = SessionLocal()
try:
    updater = IngestionUpdater(
        db=db,
        dailymed_client=DailyMedClient(settings.DAILYMED_BASE_URL),
        openfda_client=OpenFDAClient(settings.OPENFDA_BASE_URL, settings.OPENFDA_API_KEY),
        parser=LabelParser(),
        normalizer=LabelNormalizer(),
        loader=DBLoader(db),
    )
    run = updater.run_full_ingest(limit=200000)
    print('DONE', run.id, run.status, run.records_seen, run.records_inserted, run.records_updated, run.records_failed)
finally:
    db.close()
