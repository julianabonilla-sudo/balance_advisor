"""Entry point for the Energy Balance Advisor.

Usage:
  py -3 main.py                        # interactive chat
  py -3 main.py --report               # daily variation report (diff vs yesterday)
  py -3 main.py --report --no-save     # diff only, don't persist snapshot
  py -3 main.py --advisor              # advisory: 12m coverage + buy/sell recommendations
  py -3 main.py --advisor --save       # advisor + save to reports/advisor-YYYY-MM.txt
  py -3 main.py --advisor 2026 6       # advisor for a specific year/month
  py -3 main.py --html                 # executive HTML report, opens in browser
  py -3 main.py --html --no-save       # HTML report without saving snapshot
  py -3 main.py --html 2026 6          # HTML report for a specific year/month
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def _run_report(args: list[str]) -> None:
    """Daily variation report — diff vs yesterday's snapshot."""
    from src.monitor import run_monitor

    save = "--no-save" not in args

    print("\n⚡ Energy Balance Advisor — Reporte Diario")
    print("─" * 42)

    report_text = run_monitor(save=save)
    print(report_text)


def _run_advisor(args: list[str]) -> None:
    """Advisory report — 12m coverage + buy/sell recommendations."""
    from src.advisor import run_advisor

    save = "--save" in args
    numeric = [a for a in args if a.lstrip("-").isdigit() and not a.startswith("--")]
    year = month = None
    if len(numeric) >= 2:
        year, month = int(numeric[0]), int(numeric[1])

    print("\n⚡ Energy Balance Advisor — Reporte Asesor")
    print("─" * 42)

    report_text = run_advisor(year=year, month=month)
    print(report_text)

    if save:
        from datetime import date
        out_dir = Path("reports")
        out_dir.mkdir(exist_ok=True)
        today = date.today()
        out_path = out_dir / f"advisor-{today.year}-{today.month:02d}.txt"
        out_path.write_text(report_text, encoding="utf-8")
        print(f"  Reporte guardado en: {out_path}\n")


def _run_html(args: list[str]) -> None:
    """Executive HTML report — opens in browser and/or sends by email."""
    from datetime import date
    from src.report_html import run_html_report

    save_snap = "--no-save" not in args
    send_email = "--email" in args
    numeric = [a for a in args if a.lstrip("-").isdigit() and not a.startswith("--")]
    year = month = None
    if len(numeric) >= 2:
        year, month = int(numeric[0]), int(numeric[1])

    print("\n⚡ Energy Balance Advisor — Reporte Ejecutivo HTML")
    print("─" * 46)

    html = run_html_report(year=year, month=month, save_snap=save_snap)

    out_dir = Path("reports")
    out_dir.mkdir(exist_ok=True)
    today = date.today()
    out_path = out_dir / f"advisor-{today}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"  Reporte guardado: {out_path}")

    if send_email:
        from src.report_html.emailer import send_report
        send_report(html)
    else:
        import webbrowser
        webbrowser.open(out_path.resolve().as_uri())
        print(f"  Abierto en navegador\n")


def _run_chat() -> None:
    from src.agent import EnergyBalanceAdvisor

    print("\n⚡ Energy Balance Advisor — Modo Chat")
    print("  Escribe tu consulta. Comandos: 'salir' · 'reset' · 'reporte' · 'advisor'\n")

    with EnergyBalanceAdvisor() as advisor:
        while True:
            try:
                user_input = input("Tú: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nHasta luego.")
                break

            if not user_input:
                continue

            if user_input.lower() == "salir":
                print("Hasta luego.")
                break

            if user_input.lower() == "reset":
                advisor.reset()
                print("Conversación reiniciada.\n")
                continue

            if user_input.lower() == "reporte":
                _run_report([])
                continue

            if user_input.lower() in ("monitor", "reporte"):
                _run_report([])
                continue

            if user_input.lower() == "advisor":
                _run_advisor([])
                continue

            print("\nAdvisor: ", end="", flush=True)
            response = advisor.chat(user_input)
            print(response)
            print()


def main() -> None:
    args = sys.argv[1:]

    if "--report" in args:
        _run_report(args)
    elif "--advisor" in args:
        _run_advisor(args)
    elif "--html" in args:
        _run_html(args)
    else:
        _run_chat()


if __name__ == "__main__":
    main()
