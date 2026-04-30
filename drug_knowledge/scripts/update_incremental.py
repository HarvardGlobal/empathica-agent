#!/usr/bin/env python3
"""
CLI script: run an incremental update from DailyMed (labels updated in the last N days).

Usage:
    python scripts/update_incremental.py [--days-back N]
"""
from __future__ import annotations

import argparse
import logging
import sys
import os

# Make 'app' importable when running from the drug_knowledge/ directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.db import SessionLocal, init_db
from app.services.ingestion.dailymed_client import DailyMedClient
from app.services.ingestion.loader import DBLoader
from app.services.ingestion.normalizer import LabelNormalizer
from app.services.ingestion.openfda_client import OpenFDAClient
from app.services.ingestion.parser import LabelParser
from app.services.ingestion.updater import IngestionUpdater

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run incremental DailyMed update for recently changed labels."
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=7,
        help="Number of days back to check for updated labels (default: 7)",
    )
    args = parser.parse_args()

    logger.info("Initializing database...")
    init_db()

    db = SessionLocal()
    try:
        logger.info("Starting incremental update (days_back=%d)...", args.days_back)

        dailymed_client = DailyMedClient(base_url=settings.DAILYMED_BASE_URL)
        openfda_client = OpenFDAClient(
            base_url=settings.OPENFDA_BASE_URL,
            api_key=settings.OPENFDA_API_KEY,
        )
        label_parser = LabelParser()
        normalizer = LabelNormalizer()
        loader = DBLoader(db)
        updater = IngestionUpdater(
            db=db,
            dailymed_client=dailymed_client,
            openfda_client=openfda_client,
            parser=label_parser,
            normalizer=normalizer,
            loader=loader,
        )

        run = updater.run_incremental_update(days_back=args.days_back)

        logger.info(
            "Incremental update finished: status=%s seen=%d inserted=%d updated=%d failed=%d",
            run.status,
            run.records_seen,
            run.records_inserted,
            run.records_updated,
            run.records_failed,
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
