"""Generates the standalone HTML executive report."""


# ── Format helpers ────────────────────────────────────────────────────────────

def _m(v: float) -> str:
    return f"{v / 1e6:,.0f} MCOP"

def _gwh(mwh: float) -> str:
    return f"{mwh / 1_000:,.1f} GWh"

def _mwh(mwh: float) -> str:
    return f"{mwh:,.1f} MWh"

def _pct(v: float) -> str:
    return f"{v:.0f}%"

def _ckwh(v: float) -> str:
    return f"{v:,.0f} COP/kWh"

def _delta_cls(v: float, positive_good: bool = True) -> str:
    if abs(v) < 0.01:
        return "nt"
    return "good" if (v > 0) == positive_good else "bad"

def _arrow(v: float) -> str:
    return "↑" if v > 0 else "↓"

def _pct_cls(pct: float) -> str:
    if pct < 70: return "cov-low"
    if pct < 80: return "cov-mid"
    return "cov-hi"

def _sign(v: float) -> str:
    return "+" if v >= 0 else ""


# ── Section builders ──────────────────────────────────────────────────────────

def _summary_text(reg: dict, nr: dict) -> str:
    reg_cov = reg.get("coverage_pct", 0)
    reg_bal = reg.get("balance_mwh", 0)
    reg_buy_cop = reg.get("bolsa_buy_cop", 0)
    nr_cov = nr.get("coverage_pct", 0)
    nr_bal = nr.get("balance_mwh", 0)
    nr_sel_cop = nr.get("bolsa_sell_cop", 0)

    reg_color = "var(--bad)" if reg_cov < 80 else "var(--good)"
    reg_part = (
        f'En <strong>regulado</strong> cubrimos el '
        f'<strong style="color:{reg_color}">{_pct(reg_cov)}</strong> '
        f'de la demanda con contratos — los {_gwh(abs(reg_bal))} faltantes '
        f'los compramos en bolsa por <strong>{_m(reg_buy_cop)}</strong> este mes.'
        if reg_cov < 100 else
        f'En <strong>regulado</strong> tenemos cobertura del <strong style="color:var(--good)">{_pct(reg_cov)}</strong> — posición superavitaria.'
    )

    nr_gross = nr.get("contracts_mwh", 0) - nr.get("demand_mwh", 0)
    nr_bilateral = max(0.0, nr_gross - nr.get("bolsa_sell_mwh", 0))
    nr_bolsa_mwh = nr.get("bolsa_sell_mwh", 0)
    nr_part = (
        f'En <strong>no regulado</strong> cubrimos el <strong style="color:var(--good)">{_pct(nr_cov)}</strong> '
        f'de la demanda <em>(proyección estimada — mes en curso)</em>. '
        f'{_gwh(nr_bilateral)} se venden en contratos bilaterales. '
        f'Los {_gwh(nr_bolsa_mwh)} vendidos en bolsa representan ingresos de <strong>{_m(nr_sel_cop)}</strong>.'
        if nr_bal > 0 else
        f'En <strong>no regulado</strong> cubrimos el {_pct(nr_cov)} de la demanda.'
    )

    return f"{reg_part} {nr_part}"


def _cov_bar(pct: float, cls: str) -> str:
    fill_w = min(100, pct)
    return (
        f'<div class="cov-bar">'
        f'<div class="cov-fill {cls}" style="width:{fill_w}%"></div>'
        f'<div class="cov-threshold"></div>'
        f'</div>'
    )


def _mkt_card(title: str, kpis: dict, prices: dict, is_reg: bool) -> str:
    cov = kpis.get("coverage_pct", 0)
    demand = kpis.get("demand_mwh", 0)
    contracts = kpis.get("contracts_mwh", 0)
    balance = kpis.get("balance_mwh", 0)
    buy_mwh = kpis.get("bolsa_buy_mwh", 0)
    buy_cop = kpis.get("bolsa_buy_cop", 0)
    sell_mwh = kpis.get("bolsa_sell_mwh", 0)
    sell_cop = kpis.get("bolsa_sell_cop", 0)

    is_deficit = balance < 0
    border_color = "var(--bad)" if is_deficit else "var(--good)"
    pill_cls = "deficit" if is_deficit else "surplus"
    pill_txt = "déficit" if is_deficit else "excedente"
    cov_fill_cls = "bad" if cov < 80 else "good"
    cov_num_cls = "bad" if cov < 80 else "good"

    if is_reg:
        body_rows = f"""
    <div class="mkt-row">
      <span class="mkt-row-l">{"Energía faltante (déficit)" if is_deficit else "Excedente sobre demanda"}</span>
      <div class="mkt-row-r">
        <div class="mkt-row-v" style="color:{"var(--bad)" if is_deficit else "var(--good)"}">{_sign(balance)}{_gwh(balance)}</div>
      </div>
    </div>
    <div class="mkt-row">
      <span class="mkt-row-l">Costo en bolsa (spot)</span>
      <div class="mkt-row-r">
        <div class="mkt-row-v">{_m(buy_cop)}</div>
        <div class="mkt-row-s">{_mwh(buy_mwh)} · {_ckwh(buy_cop / (buy_mwh * 1_000) if buy_mwh > 0 else 0)}</div>
      </div>
    </div>"""
        insight = ""
    else:
        nr_floor = prices.get("avg_nr_buy_price", 0)
        gross_surplus = contracts - demand
        bilateral_mwh = max(0.0, gross_surplus - sell_mwh)
        bilateral_cop = bilateral_mwh * nr_floor * 1_000
        bolsa_avg = sell_cop / (sell_mwh * 1_000) if sell_mwh > 0 else 0
        gain = nr_floor - bolsa_avg
        body_rows = f"""
    <div class="mkt-row">
      <span class="mkt-row-l">Excedente bruto sobre demanda</span>
      <div class="mkt-row-r">
        <div class="mkt-row-v" style="color:var(--good)">{_sign(balance)}{_gwh(balance)}</div>
      </div>
    </div>
    <div class="mkt-row">
      <span class="mkt-row-l">Venta contratos MNR (est.)</span>
      <div class="mkt-row-r">
        <div class="mkt-row-v" style="color:var(--good)">{_gwh(bilateral_mwh)}</div>
        <div class="mkt-row-s">~{_m(bilateral_cop)} · &gt;{_ckwh(nr_floor)} objetivo</div>
      </div>
    </div>
    <div class="mkt-row">
      <span class="mkt-row-l">Venta en bolsa (spot)</span>
      <div class="mkt-row-r">
        <div class="mkt-row-v">{_m(sell_cop)}</div>
        <div class="mkt-row-s">{_mwh(sell_mwh)} · {_ckwh(bolsa_avg)}</div>
      </div>
    </div>"""
        insight = (
            f'<div class="mkt-insight">💡 Negociar bilateral a &gt;{_ckwh(nr_floor)} vs vender en bolsa a {bolsa_avg:,.0f} '
            f'genera +{gain:,.0f} COP/kWh por MWh adicional.</div>'
            if sell_mwh > 0 and gain > 0 else ""
        )

    return f"""
<div class="mkt-card" style="border-left:4px solid {border_color}">
  <div class="mkt-head">
    <span class="mkt-head-lbl">{title}</span>
    <span class="pill {pill_cls}">{pill_txt}</span>
  </div>
  <div class="mkt-body">
    <div class="mkt-cov-row">
      <div class="mkt-cov-num {cov_num_cls}">{_pct(cov)}</div>
      <div class="mkt-cov-ctx">{_gwh(demand)} demanda<br>{_gwh(contracts)} contratos</div>
    </div>
    {_cov_bar(cov, cov_fill_cls)}
    <div class="mkt-rows">{body_rows}</div>
    {insight}
  </div>
</div>"""


def _diff_section(diff: dict) -> str:
    if not diff:
        return '<p class="no-diff">Sin datos de variación diaria disponibles.</p>'

    dp = diff["day_prev"]
    dc = diff["day_curr"]

    def col(lbl, cop_p, cop_c, mwh_p, mwh_c, price_p, price_c, is_sell=False):
        d_cop = cop_c - cop_p
        d_mwh = mwh_c - mwh_p
        pos_good = is_sell
        cls = _delta_cls(d_cop, positive_good=pos_good)
        arr_cop = "↑" if d_cop > 0 else "↓"
        arr_mwh = "↑" if d_mwh > 0 else "↓"
        daily_tag = "ingreso del día · no acumulado" if is_sell else "gasto del día · no acumulado"
        if is_sell:
            price_row = f'<div class="dcol-price">Precio bolsa venta (ref. mensual): {_ckwh(price_c)}</div>'
        else:
            price_row = f'<div class="dcol-price">Precio promedio pagado: {_ckwh(price_c)} (ayer: {_ckwh(price_p)})</div>'
        why = _diff_why(diff, is_sell, cls)
        return f"""
<div class="diff-col">
  <div class="dcol-lbl">{lbl}<span class="dcol-tag">{daily_tag}</span></div>
  <div class="dcol-flow">
    <span class="dcol-ayer">Ayer: <strong>{_m(cop_p)}</strong> · {_mwh(mwh_p)}</span>
    <span class="dcol-arr">→</span>
    <span class="dcol-hoy">{_m(cop_c)} · {_mwh(mwh_c)}</span>
  </div>
  <div class="dcol-delta {cls}">{arr_cop} {_sign(d_cop)}{_m(d_cop)} · {arr_mwh} {_sign(d_mwh)}{_mwh(d_mwh)}</div>
  {price_row}
  <div class="dcol-why">{why}</div>
</div>"""

    # Conclusions
    d_reg = diff["reg_cop_curr"] - diff["reg_cop_prev"]
    d_reg_price = diff["reg_price_curr"] - diff["reg_price_prev"]
    nr_net_p = diff["nr_net_cop_prev"]
    nr_net_c = diff["nr_net_cop_curr"]
    d_tot = diff["total_net_cop_curr"] - diff["total_net_cop_prev"]

    def conc_chip(cls, title, body):
        return f'<div class="conc-chip {cls}"><strong>{title}</strong>{body}</div>'

    # Regulado chip
    if abs(d_reg_price) > 10:
        dir_p = "bajó" if d_reg_price < 0 else "subió"
        chip_reg = conc_chip(
            "good" if d_reg_price < 0 else "bad",
            "Regulado",
            f"precio bolsa {dir_p} {abs(d_reg_price):,.0f} COP/kWh — "
            f'{"ahorro" if d_reg < 0 else "mayor costo"} de {_m(abs(d_reg))} vs ayer',
        )
    else:
        chip_reg = conc_chip("good" if d_reg <= 0 else "bad", "Regulado", f'{"ahorro" if d_reg <= 0 else "mayor costo"} de {_m(abs(d_reg))} vs ayer')

    # NR chip
    if nr_net_c < 0 and nr_net_p >= 0:
        chip_nr = conc_chip("good", "No regulado",
            f"de comprador a vendedor neto — ingreso {_m(abs(nr_net_c))} hoy vs costo {_m(abs(nr_net_p))} ayer")
    elif nr_net_c >= 0 and nr_net_p < 0:
        chip_nr = conc_chip("bad", "No regulado",
            f"de vendedor a comprador neto — costo {_m(nr_net_c)} hoy vs ingreso {_m(abs(nr_net_p))} ayer")
    else:
        dir_nr = "mejoró" if nr_net_c < nr_net_p else "empeoró"
        chip_nr = conc_chip("good" if nr_net_c < nr_net_p else "bad", "No regulado",
            f"posición neta {dir_nr} en {_m(abs(nr_net_c - nr_net_p))}")

    # Total chip
    chip_tot = conc_chip(
        "good" if d_tot < 0 else "bad",
        "Total neto",
        f'{"ahorro" if d_tot < 0 else "mayor costo"} de {_m(abs(d_tot))} respecto a ayer',
    )

    # Alert / OK note
    is_flip = nr_net_c >= 0 and nr_net_p < 0
    is_price_spike = d_reg_price > 150          # solo subida es crítica
    is_cost_spike = (d_tot > 0 and diff["total_net_cop_prev"] > 0
                     and d_tot / diff["total_net_cop_prev"] > 0.30)

    if is_flip or is_price_spike or is_cost_spike:
        reasons = []
        if is_flip:
            reasons.append(f"NR pasó a comprador neto el día {dc}")
        if is_price_spike:
            reasons.append(f"precio bolsa subió {abs(d_reg_price):,.0f} COP/kWh en un día")
        if is_cost_spike:
            reasons.append(f"costo neto diario aumentó más del 30% vs día {dp}")
        status_html = (
            f'<div class="diff-status alert">⚠ Cambio crítico desde el día {dc}: '
            f'{" · ".join(reasons)}. Revisar posición con prioridad.</div>'
        )
    else:
        status_html = (
            f'<div class="diff-status ok">✓ Sin cambios críticos desde el día {dp} — '
            f'posición acumulada estable. Se considera crítico si: NR vuelve a comprador neto · '
            f'pico bolsa &gt;150 COP/kWh/día · costo neto sube &gt;30%.</div>'
        )

    return f"""
<div class="diff-wrap">
  <div class="diff-hdr">
    <span class="diff-hdr-lbl">⇄ Variaciones últimas 24 h</span>
    <span class="diff-hdr-sub">día {dp} → día {dc} del mes · cifras diarias, no acumuladas</span>
  </div>
  <div class="diff-cols">
    {col("Compra bolsa<br><strong>Regulado</strong>",
         diff["reg_cop_prev"], diff["reg_cop_curr"],
         diff["reg_mwh_prev"], diff["reg_mwh_curr"],
         diff["reg_price_prev"], diff["reg_price_curr"])}
    {col("Compra bolsa<br><strong>No regulado</strong>",
         diff["nr_buy_cop_prev"], diff["nr_buy_cop_curr"],
         diff["nr_buy_mwh_prev"], diff["nr_buy_mwh_curr"],
         diff["nr_buy_price_prev"], diff["nr_buy_price_curr"])}
    {col("Venta bolsa<br><strong>No regulado</strong>",
         diff["nr_sel_cop_prev"], diff["nr_sel_cop_curr"],
         diff["nr_sel_mwh_prev"], diff["nr_sel_mwh_curr"],
         diff["nr_sel_price_prev"], diff["nr_sel_price_curr"], is_sell=True)}
  </div>
  <div class="diff-concl">
    {chip_reg}
    {chip_nr}
    {chip_tot}
  </div>
  {status_html}
</div>"""


def _diff_why(diff: dict, is_sell: bool, cls: str) -> str:
    if is_sell:
        d = diff["nr_sel_cop_curr"] - diff["nr_sel_cop_prev"]
        if d > 0:
            return "Más excedente vendido en bolsa — mejor uso del portafolio NR."
        return "Menos horas de excedente disponibles para venta en bolsa."
    d_price_reg = diff["reg_price_curr"] - diff["reg_price_prev"]
    if abs(d_price_reg) > 50:
        direction = "bajó" if d_price_reg < 0 else "subió"
        return f"Precio de bolsa {direction} {abs(d_price_reg):,.0f} COP/kWh — misma energía, distinto costo."
    return "Menos horas en déficit horario — el excedente cubrió mejor la posición."


def _future_row(m: dict) -> str:
    reg_cov = m["reg_cov"]
    nr_cov = m["nr_cov"]
    bal = m["balance_gwh"]
    sig_reg = m["signal_reg"]
    sig_nr = m["signal_nr"]
    ctype = m["change_type"]
    ctext = m["change_text"]
    is_flip = ctype == "warning"

    def badge(sig):
        if sig == "COMPRA":
            return '<span class="sbadge buy">↓ compra</span>'
        if sig == "VENTA":
            return '<span class="sbadge sell">↑ venta</span>'
        return '<span class="sbadge none">—</span>'

    def chg():
        if ctype == "none":
            return '<div class="chg-ok">Sin cambios</div>'
        if ctype == "warning":
            return f'<div class="chg-warn">⚠ {ctext}</div>'
        return f'<div class="chg-info">ℹ {ctext}</div>'

    row_cls = " flip-row" if is_flip else ""
    sign = "+" if bal >= 0 else ""
    return f"""<tr class="{row_cls}">
  <td><strong>{m["label"]}</strong>{"&nbsp;⚠" if is_flip else ""}</td>
  <td class="r {_pct_cls(reg_cov)}">{_pct(reg_cov)}</td>
  <td class="r {_pct_cls(nr_cov)}">{_pct(nr_cov)}</td>
  <td class="r">{sign}{bal} GWh</td>
  <td>{badge(sig_reg)}</td>
  <td>{badge(sig_nr)}</td>
  <td>{chg()}</td>
</tr>"""


def _flip_alert(flip_months: list) -> str:
    if not flip_months:
        return ""
    m = flip_months[0]
    return f"""
<div class="flip-alert">
  <div class="flip-alert-t">⚠ Alerta — cambio de posición: {m["label"]}</div>
  <div class="flip-alert-b">{m["change_text"]}. Sin acción antes de esa fecha, se deberá comprar energía en bolsa a precio de mercado.</div>
</div>"""


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --brand:#6D28D9;--brand-deep:#1E1033;--brand-tint:#EDE9FE;
  --good:#059669;--good-bg:#ECFDF5;
  --bad:#DC2626;--bad-bg:#FEF2F2;
  --warn:#D97706;--warn-bg:#FFFBEB;--warn-bd:#FDE68A;
  --text:#111827;--sec:#6B7280;--muted:#9CA3AF;
  --border:#E4E4F0;--surface:#F7F5FF;--card:#fff;
}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;background:var(--surface);color:var(--text);font-size:14px;line-height:1.5;font-variant-numeric:tabular-nums}
.hdr{background:var(--brand-deep);height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 24px}
.hdr-left{display:flex;align-items:center;gap:12px}
.hdr-icon{width:30px;height:30px;background:var(--brand);border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:16px}
.hdr-name{font-size:14px;font-weight:600;color:#fff}
.hdr-period{font-size:11px;color:#A78BFA;padding:2px 10px;border:1px solid #4C1D95;border-radius:20px}
.hdr-right{font-size:11px;color:#7C3AED}
.wrap{max-width:960px;margin:0 auto;padding:20px 20px 48px}
.fresh{display:inline-flex;align-items:center;gap:8px;font-size:11px;padding:5px 14px;border-radius:20px;border:1px solid #DDD6FE;background:#fff;color:var(--sec);margin-bottom:18px}
.fresh .dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.real{color:var(--good);font-weight:600}.est{color:var(--warn);font-weight:600}
.tabs-nav{display:flex;border-bottom:2px solid var(--border);margin-bottom:22px;gap:2px}
.tab-btn{padding:9px 20px;font-size:13px;font-weight:500;color:var(--sec);background:transparent;border:none;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px}
.tab-btn.active{color:var(--brand);border-bottom-color:var(--brand)}
.tab-btn:hover:not(.active){color:var(--text)}
.panel{display:none}.panel.active{display:block}
.summary{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px 18px;margin-bottom:18px;font-size:13px;line-height:1.8}
.summary em{color:var(--muted);font-style:italic;font-size:12px}
.metric-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:18px}
.mtile{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px 16px;position:relative;overflow:hidden}
.mtile::before{content:'';position:absolute;left:0;top:0;bottom:0;width:3px}
.mtile.bad::before{background:var(--bad)}.mtile.good::before{background:var(--good)}.mtile.neutral::before{background:var(--brand)}
.mt-lbl{font-size:10px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--sec);margin-bottom:4px}
.mt-val{font-size:28px;font-weight:800;line-height:1;margin-bottom:2px}
.mt-val.bad{color:var(--bad)}.mt-val.good{color:var(--good)}.mt-val.neutral{color:var(--brand)}
.mt-desc{font-size:11px;color:var(--sec);margin-bottom:8px}
.cov-bar{position:relative;height:4px;background:#EDE9FE;border-radius:2px;overflow:visible;margin-top:4px}
.cov-fill{position:absolute;left:0;top:0;bottom:0;border-radius:2px}
.cov-fill.bad{background:var(--bad)}.cov-fill.good{background:var(--good)}.cov-fill.brand{background:var(--brand)}
.cov-threshold{position:absolute;left:80%;top:-4px;bottom:-4px;width:2px;background:var(--warn);border-radius:1px}
.cov-threshold::after{content:'80%';position:absolute;top:-15px;left:-6px;font-size:9px;color:var(--warn);font-weight:700;white-space:nowrap}
.prices-bar{display:grid;grid-template-columns:repeat(3,1fr);background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:18px}
.price-item{padding:12px 16px;border-right:1px solid var(--border)}
.price-item:last-child{border-right:none}
.pi-lbl{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--sec)}
.pi-sub{font-size:10px;color:var(--muted);font-style:italic;margin-bottom:5px;min-height:14px}
.pi-val{font-size:20px;font-weight:700;color:var(--text)}
.pi-unit{font-size:13px;font-weight:500;color:var(--sec)}
.mkt-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:18px}
.mkt-card{background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.mkt-head{display:flex;align-items:center;justify-content:space-between;padding:11px 16px;border-bottom:1px solid var(--border);background:#FAFAFA}
.mkt-head-lbl{font-size:10px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--sec)}
.pill{font-size:11px;font-weight:700;padding:2px 10px;border-radius:20px}
.pill.deficit{background:var(--bad-bg);color:var(--bad)}.pill.surplus{background:var(--good-bg);color:var(--good)}
.mkt-body{padding:16px}
.mkt-cov-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.mkt-cov-num{font-size:38px;font-weight:800;line-height:1}
.mkt-cov-num.bad{color:var(--bad)}.mkt-cov-num.good{color:var(--good)}
.mkt-cov-ctx{text-align:right;font-size:12px;color:var(--sec);line-height:1.6}
.mkt-rows{margin-top:14px;border-top:1px solid var(--border);padding-top:12px;display:flex;flex-direction:column;gap:7px}
.mkt-row{display:flex;justify-content:space-between;align-items:baseline;font-size:12px}
.mkt-row-l{color:var(--sec)}
.mkt-row-r{text-align:right}
.mkt-row-v{font-weight:600;font-size:13px;color:var(--text)}
.mkt-row-s{font-size:11px;color:var(--muted)}
.mkt-insight{margin-top:12px;padding:9px 12px;background:#FAFAFA;border-radius:5px;font-size:11px;color:var(--sec);line-height:1.5;border-left:3px solid var(--brand-tint)}
.diff-wrap{background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:0}
.diff-hdr{display:flex;justify-content:space-between;align-items:center;padding:11px 16px;background:var(--brand-deep)}
.diff-hdr-lbl{font-size:11px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:#C4B5FD}
.diff-hdr-sub{font-size:12px;color:#7C3AED}
.diff-cols{display:grid;grid-template-columns:repeat(3,1fr)}
.diff-col{padding:16px;border-right:1px solid var(--border)}
.diff-col:last-child{border-right:none}
.dcol-lbl{font-size:10px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--sec);margin-bottom:4px;line-height:1.4}
.dcol-tag{display:block;font-size:10px;color:var(--muted);font-style:italic;font-weight:400;text-transform:none;letter-spacing:0;margin-bottom:10px}
.dcol-flow{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-bottom:7px}
.dcol-ayer{font-size:12px;color:var(--sec)}.dcol-ayer strong{color:var(--text)}
.dcol-arr{color:#DDD6FE;font-size:14px}
.dcol-hoy{font-size:14px;font-weight:700;color:var(--text)}
.dcol-delta{display:inline-flex;align-items:center;gap:3px;font-size:12px;font-weight:600;padding:3px 9px;border-radius:4px;margin-bottom:6px}
.dcol-delta.good{background:var(--good-bg);color:var(--good)}.dcol-delta.bad{background:var(--bad-bg);color:var(--bad)}.dcol-delta.nt{background:#F3F4F6;color:var(--sec)}
.dcol-price{font-size:11px;color:var(--muted);margin-bottom:8px}
.dcol-why{font-size:11px;color:var(--sec);padding-top:8px;border-top:1px solid var(--border);line-height:1.4;font-style:italic}
.diff-concl{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:12px 16px;background:#FAFAFE;border-top:1px solid var(--border)}
.conc-chip{font-size:12px;padding:8px 11px;border-radius:5px;line-height:1.5}
.conc-chip strong{display:block;font-size:10px;letter-spacing:.05em;text-transform:uppercase;margin-bottom:2px}
.conc-chip.good{background:var(--good-bg);color:#065F46}.conc-chip.bad{background:var(--bad-bg);color:#7F1D1D}
.diff-status{padding:10px 16px;border-top:1px solid var(--border);font-size:12px;display:flex;align-items:center;gap:7px}
.diff-status.ok{background:#F0FDF4;color:#065F46}.diff-status.alert{background:var(--warn-bg);color:#78350F;font-weight:500}
.flip-alert{background:var(--warn-bg);border:1px solid var(--warn-bd);border-radius:8px;padding:14px 16px;margin-bottom:16px}
.flip-alert-t{font-size:13px;font-weight:600;color:var(--warn);margin-bottom:5px}
.flip-alert-b{font-size:13px;color:#78350F;line-height:1.55}
.t2-lbl{font-size:10px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--sec);margin-bottom:12px}
.table-wrap{overflow-x:auto;border-radius:8px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;font-size:13px;background:var(--card)}
th{padding:9px 14px;text-align:left;font-size:10px;font-weight:600;letter-spacing:.07em;text-transform:uppercase;color:var(--sec);background:#F9F8FF;border-bottom:2px solid var(--border)}
th.r{text-align:right}
td{padding:10px 14px;border-bottom:1px solid #F3F4F6;vertical-align:middle}
td.r{text-align:right;font-size:14px;font-weight:700}
tr:last-child td{border-bottom:none}
tr.flip-row{background:#FFFBEB}
.cov-low{color:var(--bad)}.cov-mid{color:var(--warn)}.cov-hi{color:var(--good)}
.sbadge{display:inline-flex;align-items:center;gap:3px;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;white-space:nowrap}
.sbadge.buy{background:var(--bad-bg);color:var(--bad)}.sbadge.sell{background:var(--good-bg);color:var(--good)}.sbadge.none{color:var(--muted)}
.chg-warn{font-size:11px;color:var(--warn);font-weight:500;line-height:1.4}
.chg-ok{font-size:11px;color:var(--muted)}
.chg-info{font-size:11px;color:#1D4ED8;line-height:1.4}
.legend{font-size:11px;color:var(--muted);margin-top:10px;line-height:1.8;padding:0 2px}
.no-diff{font-size:13px;color:var(--muted);padding:16px 0}
"""

_JS = """
<script>
document.querySelectorAll('.tab-btn').forEach(b=>{
  b.addEventListener('click',()=>{
    document.querySelectorAll('.tab-btn').forEach(x=>x.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(x=>x.classList.remove('active'));
    b.classList.add('active');
    document.getElementById(b.dataset.tab).classList.add('active');
  });
});
</script>
"""


# ── Main entry ────────────────────────────────────────────────────────────────

def build_html_report(data: dict) -> str:
    meta = data["meta"]
    reg = data["regulado"]
    nr = data["no_regulado"]
    prices = data["prices"]
    diff = data.get("day_diff")
    future = data["future_months"]
    flip_months = data.get("flip_months", [])

    reg_cov = reg.get("coverage_pct", 0)
    nr_cov = nr.get("coverage_pct", 0)
    reg_balance = reg.get("balance_mwh", 0)
    nr_balance = nr.get("balance_mwh", 0)

    reg_tile_cls = "bad" if reg_cov < 80 else "good"
    nr_tile_cls = "good" if nr_cov >= 100 else ("bad" if nr_cov < 80 else "neutral")
    reg_fill_cls = "bad" if reg_cov < 80 else "good"
    nr_fill_cls = "good" if nr_cov >= 80 else "bad"

    net_cop = reg.get("bolsa_buy_cop", 0) - nr.get("bolsa_sell_cop", 0)
    net_sign = "−" if net_cop < 0 else "+"
    net_label = "ingreso neto: ventas NR superan compras R" if net_cop < 0 else "costo neto en bolsa ambos mercados"

    tab1 = f"""
<div id="t1" class="panel active">
  <div class="summary">{_summary_text(reg, nr)}</div>

  <div class="metric-strip">
    <div class="mtile {reg_tile_cls}">
      <div class="mt-lbl">Cobertura regulado</div>
      <div class="mt-val {reg_tile_cls}">{_pct(reg_cov)}</div>
      <div class="mt-desc">umbral mínimo 80%{"  — déficit activo" if reg_cov < 80 else ""}</div>
      {_cov_bar(reg_cov, reg_fill_cls)}
    </div>
    <div class="mtile {nr_tile_cls}">
      <div class="mt-lbl">Cobertura no regulado</div>
      <div class="mt-val {nr_tile_cls}">{_pct(nr_cov)}</div>
      <div class="mt-desc">{"excedente — " + _gwh(nr_balance) + " sobre demanda" if nr_balance > 0 else "posición balanceada"}</div>
      {_cov_bar(nr_cov, nr_fill_cls)}
    </div>
    <div class="mtile neutral">
      <div class="mt-lbl">Impacto neto bolsa · mes</div>
      <div class="mt-val neutral">{net_sign}{_m(abs(net_cop))}</div>
      <div class="mt-desc">{net_label}</div>
      <div class="cov-bar" style="background:#DDD6FE"><div class="cov-fill brand" style="width:68%"></div></div>
    </div>
  </div>

  <div class="prices-bar">
    <div class="price-item">
      <div class="pi-lbl">Precio bolsa día {meta["last_data_day"]} de {meta["month_label_short"]}</div>
      <div class="pi-sub">&nbsp;</div>
      <div class="pi-val">{prices["bolsa_price"]:,.0f} <span class="pi-unit">COP/kWh</span></div>
    </div>
    <div class="price-item">
      <div class="pi-lbl">Precio venta bolsa — Techo compras</div>
      <div class="pi-sub">promedio acumulado {meta["month_label_short"]}</div>
      <div class="pi-val">{prices["bolsa_sell_price"]:,.0f} <span class="pi-unit">COP/kWh</span></div>
    </div>
    <div class="price-item">
      <div class="pi-lbl">PPP de compra MNR</div>
      <div class="pi-sub">promedio ponderado contratos {meta["month_label_short"]}</div>
      <div class="pi-val">{prices["avg_nr_buy_price"]:,.0f} <span class="pi-unit">COP/kWh</span></div>
    </div>
  </div>

  <div class="mkt-grid">
    {_mkt_card("Mercado regulado", reg, prices, is_reg=True)}
    {_mkt_card("Mercado no regulado", nr, prices, is_reg=False)}
  </div>

  {_diff_section(diff)}
</div>"""

    future_rows = "\n".join(_future_row(m) for m in future)
    tab2 = f"""
<div id="t2" class="panel">
  {_flip_alert(flip_months)}
  <div class="t2-lbl">Señales y variaciones — próximos {len(future)} meses</div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>Mes</th>
        <th class="r">Reg %</th>
        <th class="r">NR %</th>
        <th class="r">Balance</th>
        <th>Señal Reg</th>
        <th>Señal NR</th>
        <th>Variación vs ayer</th>
      </tr></thead>
      <tbody>{future_rows}</tbody>
    </table>
  </div>
  <div class="legend">
    <span style="color:var(--bad)">Compra</span> = cobertura &lt;80%, precio objetivo &lt;{_ckwh(prices["bolsa_sell_price"])} &nbsp;·&nbsp;
    <span style="color:var(--good)">Venta NR</span> = excedente &gt;100%, precio objetivo &gt;{_ckwh(prices["avg_nr_buy_price"])} &nbsp;·&nbsp;
    Fila resaltada = cambio de señal vs ayer
  </div>
</div>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Energy Balance Advisor — {meta["month_label_short"]}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="hdr">
  <div class="hdr-left">
    <div class="hdr-icon">⚡</div>
    <span class="hdr-name">Energy Balance Advisor</span>
    <span class="hdr-period">{meta["month_label_short"]} · {meta["version_name"]}</span>
  </div>
  <div class="hdr-right">Generado {meta["generated_date"]}</div>
</div>
<div class="wrap">
  <div class="fresh">
    <span class="dot" style="background:var(--good)"></span>
    {meta["month_label_short"]} · acumulado mes &nbsp;|&nbsp;
    Días 1–{meta["last_data_day"]}: <span class="real">datos reales</span> &nbsp;·&nbsp;
    Días {meta["last_data_day_plus1"]}–{meta["days_in_month"]}: <span class="est">proyección estimada</span>
  </div>
  <div class="tabs-nav">
    <button class="tab-btn active" data-tab="t1">📅 Mes actual</button>
    <button class="tab-btn" data-tab="t2">📈 Horizonte {len(future)} meses</button>
  </div>
  {tab1}
  {tab2}
</div>
{_JS}
</body>
</html>"""
