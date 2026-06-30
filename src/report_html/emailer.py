"""Sends the HTML report via Gmail SMTP with a commercial HTML email body."""

import smtplib
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import settings

_MONTH_ES = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
}
_MONTH_SHORT = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


def _badge(text: str, bg: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;font-size:9px;font-weight:600;'
        f'padding:2px 8px;border-radius:20px;background:{bg};color:{color};">'
        f'{text}</span>'
    )


def _cov_bar_row(label: str, pct: float, color: str) -> str:
    filled = min(100.0, pct)
    rest = 100.0 - filled
    return (
        f'<tr>'
        f'<td style="width:90px;font-size:11px;color:#374151;font-weight:500;'
        f'padding-right:10px;padding-bottom:6px;white-space:nowrap;">{label}</td>'
        f'<td style="padding-right:8px;padding-bottom:6px;">'
        f'<table width="100%" height="8" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:#F3F4F6;border-radius:4px;overflow:hidden;">'
        f'<tr>'
        f'<td width="{filled:.1f}%" style="background:{color};height:8px;font-size:1px;">&nbsp;</td>'
        f'<td width="{rest:.1f}%" style="height:8px;font-size:1px;">&nbsp;</td>'
        f'</tr></table></td>'
        f'<td style="width:40px;text-align:right;font-size:11px;font-weight:600;'
        f'color:{color};white-space:nowrap;padding-bottom:6px;">{pct:.0f}%</td>'
        f'</tr>'
    )


def _horizon_cell(m: dict) -> str:
    sig_reg = m.get("signal_reg", "&#8212;")
    mo = m["month"]
    yr = m["year"]
    lbl = f"{_MONTH_SHORT.get(mo, str(mo))} {yr % 100:02d}"
    reg_cov = m.get("reg_cov", 0)

    if sig_reg == "COMPRA":
        bg, border, tc, sc, sl = "#FEF3C7", "#FDE68A", "#92400E", "#B45309", "Compra"
    elif m.get("change_type") == "warning":
        bg, border, tc, sc, sl = "#FEE2E2", "#FECACA", "#991B1B", "#DC2626", "Revisar"
    else:
        bg, border, tc, sc, sl = "#D1FAE5", "#A7F3D0", "#065F46", "#059669", "Neutral"

    return (
        f'<td style="background:{bg};border:1px solid {border};border-radius:6px;'
        f'padding:8px 4px;text-align:center;vertical-align:top;">'
        f'<p style="margin:0 0 3px;font-size:10px;color:{tc};font-weight:500;">{lbl}</p>'
        f'<p style="margin:0 0 2px;font-size:9px;color:{sc};font-weight:600;">{sl}</p>'
        f'<p style="margin:0;font-size:8px;color:{sc};">Reg {reg_cov:.0f}%</p>'
        f'</td>'
    )


def _build_email_html(data: dict) -> str:
    meta = data.get("meta", {})
    prices = data.get("prices", {})
    reg = data.get("regulado", {})
    nr = data.get("no_regulado", {})
    future = data.get("future_months", [])[:6]

    today = date.today()
    day_label = f"{today.day} de {_MONTH_ES.get(today.month, '')} de {today.year}"
    version = meta.get("version_name", "Tx2")
    month_label_short = meta.get("month_label_short", "")

    reg_cov = reg.get("coverage_pct", 0.0)
    reg_dem_gwh = reg.get("demand_mwh", 0) / 1000

    nr_cov_bruto = nr.get("coverage_pct", 0.0)
    nr_contracts = nr.get("contracts_mwh", 0)
    nr_demand = nr.get("demand_mwh", 1)
    nr_bilateral = nr.get("bilateral_mwh", 0)
    nr_cov_net = (nr_contracts - nr_bilateral) / nr_demand * 100 if nr_demand > 0 else nr_cov_bruto

    bolsa_price = prices.get("bolsa_price", 0)

    has_alert = reg_cov < 80.0
    reg_color = "#D97706" if reg_cov < 80 else "#059669"
    nr_net_color = "#059669" if nr_cov_net >= 80 else "#D97706"

    header_badge = (
        '<p style="margin:14px 0 0;display:inline-block;font-size:11px;font-weight:500;'
        'padding:5px 12px;border-radius:20px;background:rgba(109,40,217,0.35);'
        'border:1px solid rgba(139,92,246,0.4);color:#C4B5FD;">'
        '&#9888; Se&#241;al activa: compra contratos regulado</p>'
        if has_alert else
        '<p style="margin:14px 0 0;display:inline-block;font-size:11px;font-weight:500;'
        'padding:5px 12px;border-radius:20px;background:rgba(5,150,105,0.2);'
        'border:1px solid rgba(5,150,105,0.3);color:#6EE7B7;">'
        '&#10003; Posici&#243;n balanceada sin se&#241;ales</p>'
    )

    reg_badge = (
        _badge("Compra recomendada", "#FEF3C7", "#92400E")
        if reg_cov < 80
        else _badge("Posici&#243;n cubierta", "#D1FAE5", "#065F46")
    )
    if nr_cov_net > 100:
        nr_badge = _badge("Vendedor en bolsa", "#EDE9FE", "#4C1D95")
    elif nr_cov_net >= 80:
        nr_badge = _badge("Posici&#243;n cubierta", "#D1FAE5", "#065F46")
    else:
        nr_badge = _badge("Compra recomendada", "#FEF3C7", "#92400E")

    if has_alert:
        deficit = 80 - reg_cov
        alert_html = (
            f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:12px;">'
            f'<tr><td style="background:#FFFBEB;border:1px solid #FDE68A;border-left:4px solid #D97706;'
            f'border-radius:8px;padding:12px 16px;">'
            f'<p style="margin:0 0 4px;font-size:12px;font-weight:600;color:#78350F;">'
            f'Acci&#243;n recomendada: comprar contratos regulado</p>'
            f'<p style="margin:0;font-size:12px;color:#92400E;line-height:1.5;">'
            f'Precio bolsa {bolsa_price:,.0f} COP/kWh. Cobertura regulado en '
            f'{reg_cov:.0f}% &mdash; d&#233;ficit del {deficit:.0f}% requiere atenci&#243;n '
            f'antes del cierre de mes.</p>'
            f'</td></tr></table>'
        )
    else:
        alert_html = ""

    cov_bars = (
        _cov_bar_row("Regulado", reg_cov, reg_color)
        + _cov_bar_row("NR bruto", nr_cov_bruto, "#6B7280")
        + _cov_bar_row("NR neto", nr_cov_net, nr_net_color)
    )

    horizon_cells = "".join(_horizon_cell(m) for m in future)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Energy Balance Advisor &mdash; {month_label_short}</title>
</head>
<body style="margin:0;padding:0;background:#F1F3F4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F1F3F4;">
<tr><td align="center" style="padding:24px 12px 40px;">

<table width="600" cellpadding="0" cellspacing="0" border="0"
  style="max-width:600px;width:100%;background:#ffffff;border-radius:8px;overflow:hidden;border:1px solid #E5E7EB;">

  <!-- HEADER -->
  <tr>
    <td style="background:#1E1033;padding:32px 36px 28px;">
      <table cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="width:36px;height:36px;background:#6D28D9;border-radius:8px;text-align:center;
            vertical-align:middle;font-size:20px;color:#ffffff;line-height:36px;">&#9889;</td>
          <td style="padding-left:10px;font-size:11px;font-weight:500;color:rgba(255,255,255,0.45);
            letter-spacing:0.06em;text-transform:uppercase;vertical-align:middle;">
            Olibia &middot; Energy Balance Advisor</td>
        </tr>
      </table>
      <p style="margin:18px 0 6px;font-size:22px;font-weight:600;color:#ffffff;line-height:1.3;">
        Reporte ejecutivo<br>de balance energ&#233;tico</p>
      <p style="margin:0;font-size:13px;color:#8B5CF6;">{day_label} &middot; Versi&#243;n {version}</p>
      {header_badge}
    </td>
  </tr>

  <!-- METRICS PREVIEW -->
  <tr>
    <td style="background:#F7F5FF;padding:24px 36px;border-bottom:1px solid #E5E7EB;">
      <p style="margin:0 0 14px;font-size:10px;font-weight:600;letter-spacing:0.1em;
        text-transform:uppercase;color:#6D28D9;">Vista previa &mdash; m&#233;tricas principales</p>

      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr valign="top">
          <td style="width:31%;background:#ffffff;border:1px solid #E5E0FF;
            border-left:3px solid {reg_color};border-radius:8px;padding:12px 14px;">
            <p style="margin:0 0 4px;font-size:10px;color:#6B7280;font-weight:500;">Cobertura regulado</p>
            <p style="margin:0;font-size:20px;font-weight:600;color:{reg_color};line-height:1;">{reg_cov:.0f}%</p>
            <p style="margin:3px 0 6px;font-size:10px;color:#9CA3AF;">{reg_dem_gwh:.1f} GWh demanda</p>
            {reg_badge}
          </td>
          <td width="3%">&nbsp;</td>
          <td style="width:31%;background:#ffffff;border:1px solid #E5E0FF;
            border-left:3px solid {nr_net_color};border-radius:8px;padding:12px 14px;">
            <p style="margin:0 0 4px;font-size:10px;color:#6B7280;font-weight:500;">Cobertura NR neta</p>
            <p style="margin:0;font-size:20px;font-weight:600;color:{nr_net_color};line-height:1;">{nr_cov_net:.0f}%</p>
            <p style="margin:3px 0 6px;font-size:10px;color:#9CA3AF;">Tras bilaterales</p>
            {nr_badge}
          </td>
          <td width="3%">&nbsp;</td>
          <td style="width:31%;background:#ffffff;border:1px solid #E5E0FF;
            border-left:3px solid #6B7280;border-radius:8px;padding:12px 14px;">
            <p style="margin:0 0 4px;font-size:10px;color:#6B7280;font-weight:500;">Precio bolsa</p>
            <p style="margin:0;font-size:20px;font-weight:600;color:#111827;line-height:1;">{bolsa_price:,.0f}</p>
            <p style="margin:3px 0 6px;font-size:10px;color:#9CA3AF;">COP/kWh &middot; {month_label_short}</p>
            <span style="display:inline-block;font-size:9px;font-weight:600;padding:2px 8px;
              border-radius:20px;background:#F3F4F6;color:#374151;">En rango normal</span>
          </td>
        </tr>
      </table>

      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:12px;">
        <tr>
          <td style="background:#ffffff;border:1px solid #E5E0FF;border-radius:8px;padding:14px 16px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              {cov_bars}
            </table>
          </td>
        </tr>
      </table>

      {alert_html}
    </td>
  </tr>

  <!-- HORIZON -->
  <tr>
    <td style="padding:20px 36px;border-bottom:1px solid #F3F4F6;">
      <p style="margin:0 0 12px;font-size:10px;font-weight:600;letter-spacing:0.1em;
        text-transform:uppercase;color:#6D28D9;">Horizonte &mdash; pr&#243;ximos meses</p>
      <table width="100%" cellpadding="0" cellspacing="4" border="0">
        <tr>{horizon_cells}</tr>
      </table>
    </td>
  </tr>

  <!-- CTA -->
  <tr>
    <td style="padding:28px 36px;text-align:center;border-bottom:1px solid #F3F4F6;">
      <p style="margin:0 0 16px;font-size:13px;color:#6B7280;line-height:1.6;">
        El reporte completo incluye an&#225;lisis de contratos bilaterales,<br>
        desglose por contraparte y proyecciones de horizonte completo.</p>
      <span style="display:inline-block;background:#6D28D9;color:#ffffff;font-size:14px;
        font-weight:600;padding:13px 32px;border-radius:8px;letter-spacing:0.01em;">
        &#128196; Abrir reporte completo</span>
      <p style="margin:10px 0 0;font-size:11px;color:#9CA3AF;">
        El archivo HTML adjunto se abre directamente en tu navegador.</p>
    </td>
  </tr>

  <!-- FOOTER -->
  <tr>
    <td style="background:#1E1033;padding:18px 36px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="font-size:12px;color:rgba(255,255,255,0.45);">
            &#9889; <span style="color:#8B5CF6;font-weight:500;">Energy Balance Advisor</span>
            &middot; Olibia</td>
          <td align="right" style="font-size:11px;color:rgba(255,255,255,0.3);">
            Generado autom&#225;ticamente &middot; {today.strftime('%d %b %Y')}</td>
        </tr>
      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>

</body>
</html>"""


def send_report(html: str, data: dict | None = None) -> None:
    gmail_user = settings.gmail_user
    gmail_password = settings.gmail_app_password
    recipients = [r.strip() for r in settings.report_recipients.split(",") if r.strip()]

    if not gmail_user or not gmail_password or not recipients:
        raise ValueError(
            "Faltan variables de correo en .env: GMAIL_USER, GMAIL_APP_PASSWORD, REPORT_RECIPIENTS"
        )

    today = date.today()
    month_es = _MONTH_ES[today.month]
    subject = f"⚡ Energy Balance Advisor — {today.day} de {month_es} de {today.year}"

    msg = MIMEMultipart("mixed")
    msg["From"] = f"Energy Balance Advisor <{gmail_user}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    body_html = _build_email_html(data) if data else (
        f"<p>Reporte Energy Balance Advisor &mdash; {today.day} de {month_es} de {today.year}.</p>"
        f"<p>Abre el archivo HTML adjunto en tu navegador para ver el reporte completo.</p>"
    )
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    attachment = MIMEApplication(html.encode("utf-8"), _subtype="octet-stream")
    attachment.add_header(
        "Content-Disposition",
        "attachment",
        filename=f"balance-advisor-{today}.html",
    )
    msg.attach(attachment)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, gmail_password)
        smtp.sendmail(gmail_user, recipients, msg.as_string())

    print(f"  Reporte enviado a: {', '.join(recipients)}")
