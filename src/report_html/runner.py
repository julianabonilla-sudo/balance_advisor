"""Fetches all data and produces the HTML executive report."""

import calendar
from datetime import date

from src.api import OlibiaEnergy
from src.config import settings
from src.monitor.snapshot import load_latest_snapshots, save_snapshot, DailySnapshot, MonthData

from .builder import build_html_report

BUY_THRESHOLD_PCT = 80.0
SELL_THRESHOLD_PCT = 100.0


def _signal_reg(cov: float) -> str:
    return "COMPRA" if cov < BUY_THRESHOLD_PCT else "—"


def _signal_nr(cov: float) -> str:
    if cov < BUY_THRESHOLD_PCT:
        return "COMPRA"
    if cov > SELL_THRESHOLD_PCT:
        return "VENTA"
    return "—"


def _explain_change(reg_delta: float, nr_delta: float, prev_reg: float, curr_reg: float) -> tuple[str, str]:
    parts = []
    is_warning = False

    if abs(reg_delta) >= 2:
        if reg_delta <= -15:
            parts.append(
                f"Cobertura regulada cayó {abs(reg_delta):.0f} pp "
                f"(de {prev_reg:.0f}% a {curr_reg:.0f}%) — posible vencimiento de contratos"
            )
            is_warning = True
        elif reg_delta < 0:
            parts.append(f"Cobertura regulada −{abs(reg_delta):.1f} pp — actualización proyección de demanda")
        else:
            parts.append(f"Cobertura regulada +{reg_delta:.1f} pp — ingresó un contrato al portafolio")

    if abs(nr_delta) >= 2:
        if nr_delta <= -15:
            parts.append(f"Cobertura NR cayó {abs(nr_delta):.0f} pp — vencimiento de contratos NR")
            is_warning = True
        elif nr_delta < 0:
            parts.append(f"Cobertura NR −{abs(nr_delta):.1f} pp — actualización proyección")
        else:
            parts.append(f"Cobertura NR +{nr_delta:.1f} pp — nuevo contrato en portafolio")

    if not parts:
        return "none", ""
    return ("warning" if is_warning else "info"), ". ".join(parts)


def _compute_day_diff(daily_balance: list[dict], bolsa_sell_price: float = 0) -> dict | None:
    filled = [d for d in daily_balance if d.get("bolsa_buy_r", 0) > 0 or d.get("bolsa_sell_nr", 0) > 0]
    if len(filled) < 2:
        return None
    prev, curr = filled[-2], filled[-1]

    reg_kwh_p = max(1.0, prev.get("demand_r", 0) - prev.get("dispatch_r", 0))
    reg_kwh_c = max(1.0, curr.get("demand_r", 0) - curr.get("dispatch_r", 0))
    reg_cop_p = prev.get("bolsa_buy_r", 0)
    reg_cop_c = curr.get("bolsa_buy_r", 0)
    reg_price_p = reg_cop_p / reg_kwh_p
    reg_price_c = reg_cop_c / reg_kwh_c

    # NR compra: volumen = demand_nr - dispatch_nr cuando positivo
    nr_buy_cop_p = prev.get("bolsa_buy_nr", 0)
    nr_buy_cop_c = curr.get("bolsa_buy_nr", 0)
    nr_buy_kwh_p = max(0.0, prev.get("demand_nr", 0) - prev.get("dispatch_nr", 0))
    nr_buy_kwh_c = max(0.0, curr.get("demand_nr", 0) - curr.get("dispatch_nr", 0))
    nr_buy_price_p = nr_buy_cop_p / nr_buy_kwh_p if nr_buy_kwh_p > 100 else (reg_price_p or 1.0)
    nr_buy_price_c = nr_buy_cop_c / nr_buy_kwh_c if nr_buy_kwh_c > 100 else (reg_price_c or 1.0)

    # NR venta: volumen = dispatch_nr - demand_nr cuando positivo
    nr_sel_cop_p = prev.get("bolsa_sell_nr", 0)
    nr_sel_cop_c = curr.get("bolsa_sell_nr", 0)
    nr_sel_kwh_p = max(0.0, prev.get("dispatch_nr", 0) - prev.get("demand_nr", 0))
    nr_sel_kwh_c = max(0.0, curr.get("dispatch_nr", 0) - curr.get("demand_nr", 0))
    nr_sel_price_p = nr_sel_cop_p / nr_sel_kwh_p if nr_sel_kwh_p > 100 else (reg_price_p or 1.0)
    # NR venta precio: no se puede calcular desde totales diarios porque dispatch_nr - demand_nr
    # incluye ventas bilaterales, no solo bolsa. Usar bolsa_sell_price como referencia real.
    sel_ref = bolsa_sell_price if bolsa_sell_price > 0 else (reg_price_p or 1.0)
    nr_sel_price_p = sel_ref
    nr_sel_price_c = sel_ref

    # MWh NR venta: estimado desde COP / precio_referencia (consistente con el precio mostrado)
    mkt_p = reg_price_p if reg_price_p > 0 else 1.0
    mkt_c = reg_price_c if reg_price_c > 0 else 1.0
    nr_buy_mwh_p = nr_buy_kwh_p / 1_000 if nr_buy_kwh_p > 0 else nr_buy_cop_p / mkt_p / 1_000
    nr_buy_mwh_c = nr_buy_kwh_c / 1_000 if nr_buy_kwh_c > 0 else nr_buy_cop_c / mkt_c / 1_000
    nr_sel_mwh_p = nr_sel_cop_p / sel_ref / 1_000 if sel_ref > 0 else 0.0
    nr_sel_mwh_c = nr_sel_cop_c / sel_ref / 1_000 if sel_ref > 0 else 0.0

    total_net_cop_p = reg_cop_p + nr_buy_cop_p - nr_sel_cop_p
    total_net_cop_c = reg_cop_c + nr_buy_cop_c - nr_sel_cop_c
    total_net_kwh_p = max(1.0, reg_kwh_p + nr_buy_kwh_p - nr_sel_kwh_p)
    total_net_kwh_c_raw = reg_kwh_c + nr_buy_kwh_c - nr_sel_kwh_c

    return {
        "day_prev": prev["day"], "day_curr": curr["day"],
        "reg_cop_prev": reg_cop_p, "reg_cop_curr": reg_cop_c,
        "reg_mwh_prev": reg_kwh_p / 1_000, "reg_mwh_curr": reg_kwh_c / 1_000,
        "reg_price_prev": reg_price_p, "reg_price_curr": reg_price_c,
        "nr_buy_cop_prev": nr_buy_cop_p, "nr_buy_cop_curr": nr_buy_cop_c,
        "nr_buy_mwh_prev": nr_buy_mwh_p, "nr_buy_mwh_curr": nr_buy_mwh_c,
        "nr_sel_cop_prev": nr_sel_cop_p, "nr_sel_cop_curr": nr_sel_cop_c,
        "nr_sel_mwh_prev": nr_sel_mwh_p, "nr_sel_mwh_curr": nr_sel_mwh_c,
        "nr_buy_price_prev": nr_buy_price_p, "nr_buy_price_curr": nr_buy_price_c,
        "nr_sel_price_prev": nr_sel_price_p, "nr_sel_price_curr": nr_sel_price_c,
        "nr_net_cop_prev": nr_buy_cop_p - nr_sel_cop_p,
        "nr_net_cop_curr": nr_buy_cop_c - nr_sel_cop_c,
        "total_net_cop_prev": total_net_cop_p,
        "total_net_cop_curr": total_net_cop_c,
        "total_net_price_prev": total_net_cop_p / total_net_kwh_p,
        "total_net_price_curr": total_net_cop_c / total_net_kwh_c_raw if abs(total_net_kwh_c_raw) > 0.001 else 0,
    }


def run_html_report(
    year: int = None,
    month: int = None,
    version_name: str = None,
    horizon_months: int = 18,
    save_snap: bool = True,
) -> str:
    today = date.today()

    with OlibiaEnergy() as olibia:
        if year is None or month is None:
            months = olibia.balance.available_months()["months"]
            past = [m for m in months if (m["year"], m["month"]) <= (today.year, today.month)]
            latest = (past or months)[0]
            year, month = latest["year"], latest["month"]

        try:
            ctx = olibia.balance.context(year, month)
            vname = ctx["version_names"][-1] if ctx.get("version_names") else (version_name or settings.default_version_name)
        except Exception:
            vname = version_name or settings.default_version_name

        days_in_month = calendar.monthrange(year, month)[1]

        print(f"  Cargando mes actual {year}-{month:02d} ({vname})…")
        dashboard = olibia.balance.dashboard(year, month, vname)
        analysis = olibia.balance.analysis(year, month, vname)
        bolsa_summary = olibia.balance.bolsa_summary(year, month, vname)
        income_stmt = olibia.balance.income_statement(year, month, vname)

        propio = bolsa_summary.get("propio", {})
        bolsa_price = propio.get("buy_price", 0)
        bolsa_sell_price = propio.get("sell_price", 0)

        scatter = analysis.get("scatter_contracts", [])
        nr_contracts = [c for c in scatter if "NO" in c.get("market", "").upper()]
        total_qty_nr = sum(c.get("qty", 0) for c in nr_contracts)
        avg_nr_buy_price = (
            sum(c.get("price", 0) * c.get("qty", 0) for c in nr_contracts) / total_qty_nr
            if total_qty_nr > 0 else bolsa_sell_price
        )

        # Bilaterales NR reales desde income_statement (VENTA NR, excluye Demanda y Bolsa)
        bilateral_nr_kwh = 0.0
        bilateral_nr_cop = 0.0
        for section in income_stmt.get("sections", []):
            if section.get("id") == "venta":
                for sub in section.get("sub_items", []):
                    if "No Regulado" in sub.get("label", ""):
                        for item in sub.get("items", []):
                            if item.get("agente") not in ("Demanda", "Bolsa"):
                                bilateral_nr_kwh += item.get("cantidad_kwh", 0)
                                bilateral_nr_cop += item.get("total_cop", 0)
        bilateral_nr_mwh = bilateral_nr_kwh / 1_000
        bilateral_nr_avg_price = bilateral_nr_cop / bilateral_nr_kwh if bilateral_nr_kwh > 0 else 0

        kpis = dashboard.get("kpis", {})
        reg = kpis.get("regulado", {})
        nr = kpis.get("no_regulado", {})
        total = kpis.get("total", {})

        reg_demand_val = reg.get("demand_mwh", 0)
        reg_contracts_val = reg.get("contracts_mwh", 0)
        nr_demand_val = nr.get("demand_mwh", 0)
        nr_contracts_val = nr.get("contracts_mwh", 0)

        reg_cov = reg_contracts_val / reg_demand_val * 100 if reg_demand_val else 0
        nr_cov = nr_contracts_val / nr_demand_val * 100 if nr_demand_val else 0

        daily_balance = dashboard.get("daily_balance") or []
        day_diff = _compute_day_diff(daily_balance, bolsa_sell_price=bolsa_sell_price)

        print(f"  Analizando horizonte {horizon_months} meses…")
        all_months = olibia.balance.available_months()["months"]
        future_raw = sorted(
            [m for m in all_months if (m["year"], m["month"]) > (today.year, today.month)],
            key=lambda m: (m["year"], m["month"]),
        )[:horizon_months]

        snapshots = load_latest_snapshots(n=2)
        prev_snap = snapshots[1] if len(snapshots) >= 2 else None
        prev_by_key = {(md.year, md.month): md for md in prev_snap.months} if prev_snap else {}

        future_months = []
        snap_month_datas = []

        for m in future_raw:
            y, mo = m["year"], m["month"]
            try:
                ctx2 = olibia.balance.context(y, mo)
                v2 = ctx2["version_names"][-1] if ctx2.get("version_names") else vname
                d2 = olibia.balance.dashboard(y, mo, v2, with_projected_contracts=True)
                k2 = d2.get("kpis", {})
                reg2 = k2.get("regulado", {})
                nr2 = k2.get("no_regulado", {})
                total2 = k2.get("total", {})

                demand_reg2 = reg2.get("demand_mwh", 0)
                contracts_reg2 = reg2.get("contracts_mwh", 0)
                demand_nr2 = nr2.get("demand_mwh", 0)
                contracts_nr2 = nr2.get("contracts_mwh", 0)
                balance_mwh2 = total2.get("balance_mwh", 0)

                cov_reg2 = contracts_reg2 / demand_reg2 * 100 if demand_reg2 > 0 else 0
                cov_nr2 = contracts_nr2 / demand_nr2 * 100 if demand_nr2 > 0 else 0

                sig_reg = _signal_reg(cov_reg2)
                sig_nr = _signal_nr(cov_nr2)

                prev_md = prev_by_key.get((y, mo))
                if prev_md:
                    reg_delta = cov_reg2 - prev_md.coverage_reg_pct
                    nr_delta = cov_nr2 - prev_md.coverage_nr_pct
                    change_type, change_text = _explain_change(reg_delta, nr_delta, prev_md.coverage_reg_pct, cov_reg2)
                    prev_sig_reg = _signal_reg(prev_md.coverage_reg_pct)
                    if prev_sig_reg == "—" and sig_reg == "COMPRA" and reg_delta <= -15:
                        change_type = "warning"
                        change_text = (
                            f"Señal cambió a compra urgente: cobertura regulada cayó "
                            f"{abs(reg_delta):.0f} pp (de {prev_md.coverage_reg_pct:.0f}% a "
                            f"{cov_reg2:.0f}%) — vencimiento de contratos"
                        )
                else:
                    change_type, change_text = "none", ""

                future_months.append({
                    "year": y, "month": mo,
                    "label": date(y, mo, 1).strftime("%b %Y"),
                    "reg_cov": round(cov_reg2, 1),
                    "nr_cov": round(cov_nr2, 1),
                    "balance_gwh": round(balance_mwh2 / 1_000, 1),
                    "signal_reg": sig_reg,
                    "signal_nr": sig_nr,
                    "change_type": change_type,
                    "change_text": change_text,
                    "reg_buy_mwh": round(max(0.0, 0.80 * demand_reg2 - contracts_reg2)) if cov_reg2 < 80 else 0,
                    "reg_sell_mwh": round(max(0.0, contracts_reg2 - demand_reg2)) if cov_reg2 > 100 else 0,
                    "nr_buy_mwh": round(max(0.0, 0.80 * demand_nr2 - contracts_nr2)) if cov_nr2 < 80 else 0,
                    "nr_sell_mwh": round(max(0.0, contracts_nr2 - demand_nr2)) if cov_nr2 > 100 else 0,
                })
                snap_month_datas.append(MonthData(
                    year=y, month=mo, balance_mwh=balance_mwh2,
                    coverage_reg_pct=cov_reg2, coverage_nr_pct=cov_nr2,
                    bolsa_buy_mwh=0, is_current=False,
                ))
            except Exception as e:
                print(f"  [skip] {y}-{mo:02d}: {e}")

    if save_snap and snap_month_datas:
        snap = DailySnapshot(
            snapshot_date=str(today),
            current_year=year, current_month=month, version_name=vname,
            months=snap_month_datas,
        )
        save_snapshot(snap)

    flip_months = [m for m in future_months if m["change_type"] == "warning"]

    nr_net_val = nr_contracts_val - bilateral_nr_mwh
    nr_cov_net_val = nr_net_val / nr_demand_val * 100 if nr_demand_val > 0 else 0

    data = {
        "meta": {
            "year": year, "month": month, "version_name": vname,
            "generated_date": str(today),
            "month_label": date(year, month, 1).strftime("%B %Y").upper(),
            "month_label_short": date(year, month, 1).strftime("%b %Y"),
            "day_of_month": today.day if (today.year, today.month) == (year, month) else days_in_month,
            "last_data_day": day_diff["day_curr"] if day_diff else (today.day if (today.year, today.month) == (year, month) else days_in_month),
            "last_data_day_plus1": (day_diff["day_curr"] + 1) if day_diff else (today.day + 1),
            "days_in_month": days_in_month,
        },
        "prices": {
            "bolsa_price": bolsa_price,
            "bolsa_sell_price": bolsa_sell_price,
            "avg_nr_buy_price": avg_nr_buy_price,
        },
        "regulado": {
            **reg,
            "coverage_pct": round(reg_cov, 1),
            "buy_suggestion_mwh": round(max(0.0, 0.80 * reg_demand_val - reg_contracts_val)) if reg_cov < 80 else 0,
            "sell_suggestion_mwh": round(max(0.0, reg_contracts_val - reg_demand_val)) if reg_cov > 100 else 0,
        },
        "no_regulado": {
            **nr,
            "coverage_pct": round(nr_cov, 1),
            "bilateral_mwh": bilateral_nr_mwh,
            "bilateral_cop": bilateral_nr_cop,
            "bilateral_avg_price": bilateral_nr_avg_price,
            "buy_suggestion_mwh": round(max(0.0, 0.80 * nr_demand_val - nr_net_val)) if nr_cov_net_val < 80 else 0,
            "sell_suggestion_mwh": round(max(0.0, nr_net_val - nr_demand_val)) if nr_cov_net_val > 100 else 0,
        },
        "total": total,
        "day_diff": day_diff,
        "future_months": future_months,
        "flip_months": flip_months,
    }

    print("  Generando HTML…")
    return build_html_report(data), data
