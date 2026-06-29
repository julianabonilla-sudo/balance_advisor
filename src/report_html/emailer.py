"""Sends the HTML report via Gmail SMTP."""

import os
import smtplib
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_report(html: str) -> None:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_password = os.environ["GMAIL_APP_PASSWORD"]
    recipients = [r.strip() for r in os.environ["REPORT_RECIPIENTS"].split(",")]

    today = date.today()
    month_es = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre",
    }[today.month]

    subject = f"⚡ Energy Balance Advisor — {today.day} de {month_es} de {today.year}"

    msg = MIMEMultipart("mixed")
    msg["From"] = f"Energy Balance Advisor <{gmail_user}>"
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    body = MIMEText(
        f"Reporte Energy Balance Advisor — {today.day} de {month_es} de {today.year}.\n\n"
        f"Abre el archivo HTML adjunto en tu navegador para ver el reporte completo.\n\n"
        f"---\nGenerado automáticamente · Energy Balance Advisor",
        "plain",
        "utf-8",
    )
    msg.attach(body)

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
