"""Fetches today's snapshot, diffs vs yesterday, returns formatted monitor report."""

from datetime import date

from src.api import OlibiaEnergy
from src.config import settings
from src.alerts.engine import build_month_snapshot

from .snapshot import DailySnapshot, MonthData, save_snapshot, load_latest_snapshots
from .diff import compute_diff, build_diff_report


def _fetch_today_snapshot(year: int, month: int, version_name: str) -> DailySnapshot:
    today = date.today()

    with OlibiaEnergy() as olibia:
        # ── Current month data ────────────────────────────────────────────────
        print("  Cargando mes actual…")
        dashboard = olibia.balance.dashboard(year, month, version_name)
        kpis = dashboard.get("kpis", {})

        def _cov(mkt: str) -> float:
            d = kpis.get(mkt, {})
            dem = d.get("demand_mwh", 0)
            return (d.get("contracts_mwh", 0) / dem * 100) if dem > 0 else 0.0

        current = MonthData(
            year=year,
            month=month,
            balance_mwh=kpis.get("total", {}).get("balance_mwh", 0.0),
            coverage_reg_pct=_cov("regulado"),
            coverage_nr_pct=_cov("no_regulado"),
            bolsa_buy_mwh=abs(min(kpis.get("total", {}).get("balance_mwh", 0.0), 0.0)),
            is_current=True,
        )

        # ── Future months ─────────────────────────────────────────────────────
        print("  Cargando horizonte 18 meses…")
        all_months = olibia.balance.available_months()["months"]
        future = sorted(
            [m for m in all_months if (m["year"], m["month"]) > (today.year, today.month)],
            key=lambda m: (m["year"], m["month"]),
        )[:18]

        month_data: list[MonthData] = [current]
        for m in future:
            y, mo = m["year"], m["month"]
            try:
                ctx = olibia.balance.context(y, mo)
                v = ctx["version_names"][-1] if ctx.get("version_names") else version_name
                d = olibia.balance.dashboard(y, mo, v, with_projected_contracts=True)
                snap = build_month_snapshot(y, mo, v, d)
                month_data.append(MonthData(
                    year=y, month=mo,
                    balance_mwh=snap.balance_mwh,
                    coverage_reg_pct=snap.coverage_reg_pct,
                    coverage_nr_pct=snap.coverage_nr_pct,
                    bolsa_buy_mwh=snap.bolsa_buy_mwh,
                    is_current=False,
                ))
            except Exception:
                continue

    return DailySnapshot(
        snapshot_date=today.isoformat(),
        current_year=year,
        current_month=month,
        version_name=version_name,
        months=month_data,
    )


def run_monitor(
    year: int = None,
    month: int = None,
    version_name: str = None,
    save: bool = True,
) -> str:
    today = date.today()
    vname = version_name or settings.default_version_name

    # Resolve reference month
    if year is None or month is None:
        with OlibiaEnergy() as olibia:
            months = olibia.balance.available_months()["months"]
            past = [m for m in months if (m["year"], m["month"]) <= (today.year, today.month)]
            latest = (past or months)[0]
            year, month = latest["year"], latest["month"]
            try:
                ctx = olibia.balance.context(year, month)
                vname = ctx["version_names"][-1] if ctx.get("version_names") else vname
            except Exception:
                pass

    # Load existing snapshots
    existing = load_latest_snapshots(2)
    today_str = today.isoformat()

    # Check if we already have today's snapshot
    today_snap = next((s for s in existing if s.snapshot_date == today_str), None)
    if today_snap is None:
        print("  Capturando snapshot de hoy…")
        today_snap = _fetch_today_snapshot(year, month, vname)
        if save:
            path = save_snapshot(today_snap)
            print(f"  Snapshot guardado: {path}")
    else:
        print("  Snapshot de hoy ya existe en disco.")

    # Find yesterday's snapshot for comparison
    prev_snap = next((s for s in existing if s.snapshot_date != today_str), None)

    if prev_snap is None:
        lines = [
            "═" * 64,
            "⚡ ENERGY BALANCE ADVISOR — MONITOR DIARIO",
            f"   {today_str}",
            "═" * 64,
            "",
            "  ℹ️  Primera ejecución — snapshot capturado.",
            "  Ejecuta de nuevo mañana para ver el diff vs hoy.",
            "",
            f"  Meses capturados: {len(today_snap.months)} (actual + horizonte)",
            "",
            "═" * 64,
        ]
        return "\n".join(lines)

    print("  Calculando diferencias vs ayer…")
    diff = compute_diff(prev_snap, today_snap)
    return build_diff_report(diff, today)
