import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DRAGON_GATE_DB_PATH", BASE_DIR / "sample_data.db"))
RRG_CSV_PATH = Path(os.getenv("DRAGON_GATE_RRG_CSV_PATH", BASE_DIR / "rrg_daily_result.csv"))
