"""Daily snapshot — persists per-month energy metrics to disk for diff comparison."""

import json
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Optional

SNAPSHOT_DIR = Path("data/snapshots")


@dataclass
class MonthData:
    year: int
    month: int
    balance_mwh: float
    coverage_reg_pct: float
    coverage_nr_pct: float
    bolsa_buy_mwh: float
    is_current: bool = False


@dataclass
class DailySnapshot:
    snapshot_date: str          # YYYY-MM-DD
    current_year: int
    current_month: int
    version_name: str
    months: list[MonthData]     # current month + up to 18 forward months


def save_snapshot(snap: DailySnapshot) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{snap.snapshot_date}.json"
    data = {
        "snapshot_date": snap.snapshot_date,
        "current_year": snap.current_year,
        "current_month": snap.current_month,
        "version_name": snap.version_name,
        "months": [asdict(m) for m in snap.months],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _load(path: Path) -> Optional[DailySnapshot]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        months = [MonthData(**m) for m in data["months"]]
        return DailySnapshot(
            snapshot_date=data["snapshot_date"],
            current_year=data["current_year"],
            current_month=data["current_month"],
            version_name=data.get("version_name", ""),
            months=months,
        )
    except Exception:
        return None


def load_latest_snapshots(n: int = 2) -> list[DailySnapshot]:
    """Return up to n most-recent snapshots, newest first."""
    if not SNAPSHOT_DIR.exists():
        return []
    files = sorted(SNAPSHOT_DIR.glob("*.json"), reverse=True)
    snaps = []
    for f in files:
        s = _load(f)
        if s:
            snaps.append(s)
        if len(snaps) == n:
            break
    return snaps
