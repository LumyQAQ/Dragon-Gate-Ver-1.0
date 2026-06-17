import csv
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


class DataUpdatePipelineTests(unittest.TestCase):
    def test_data_modules_share_default_sample_database(self):
        import config
        import data_engine
        import strategy_engine
        import update_data

        self.assertEqual(os.fspath(config.DB_PATH), os.fspath(data_engine.DB_PATH))
        self.assertEqual(os.fspath(config.DB_PATH), os.fspath(strategy_engine.DB_PATH))
        self.assertEqual(os.fspath(config.DB_PATH), os.fspath(update_data.DB_PATH))
        self.assertEqual(config.DB_PATH.name, "sample_data.db")

    def test_rrg_snapshot_can_be_rebuilt_from_database(self):
        import strategy_engine

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "sample_data.db"
            csv_path = Path(temp_dir) / "rrg_daily_result.csv"
            self._seed_database(db_path)

            result_df = strategy_engine.build_rrg_snapshot(
                db_path=db_path,
                csv_path=csv_path,
                days_lookback=35,
            )

            self.assertFalse(result_df.empty)
            self.assertTrue(csv_path.exists())
            with csv_path.open(encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertGreaterEqual(len(rows), 2)
            self.assertEqual({row["日期"] for row in rows}, {"2026-06-17"})

    def test_update_data_does_not_clear_proxy_environment_by_default(self):
        env = os.environ.copy()
        env["https_proxy"] = "http://127.0.0.1:7890"
        env.pop("DRAGON_GATE_CLEAR_PROXY", None)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os, update_data; print(os.environ.get('https_proxy', ''))",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

        self.assertEqual(result.stdout.strip(), "http://127.0.0.1:7890")

    def _seed_database(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE stock_daily (
                代码 TEXT,
                日期 TEXT,
                开盘 REAL,
                收盘 REAL,
                最高 REAL,
                最低 REAL,
                成交量 REAL,
                成交额 REAL,
                振幅 REAL,
                涨跌幅 REAL,
                涨跌额 REAL,
                换手率 REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE stock_industry (
                行业名称 TEXT,
                代码 TEXT,
                名称 TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO stock_industry VALUES (?, ?, ?)",
            [
                ("银行", "000001", "平安银行"),
                ("银行", "000002", "万科A"),
                ("通信", "600001", "通信一号"),
                ("通信", "600002", "通信二号"),
            ],
        )

        start = date(2026, 5, 14)
        rows = []
        for i in range(35):
            current = start + timedelta(days=i)
            for code, base, daily_change in [
                ("000001", 10.0, 0.20),
                ("000002", 12.0, 0.18),
                ("600001", 20.0, 0.08),
                ("600002", 22.0, 0.07),
            ]:
                close = base + i * daily_change
                rows.append(
                    (
                        code,
                        current.isoformat(),
                        close - 0.1,
                        close,
                        close + 0.2,
                        close - 0.3,
                        1_000_000 - i * 1000,
                        close * 1_000_000,
                        1.0,
                        daily_change,
                        daily_change / 10,
                        3.0,
                    )
                )
        conn.executemany(
            """
            INSERT INTO stock_daily
            (代码, 日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 振幅, 涨跌幅, 涨跌额, 换手率)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        conn.close()
