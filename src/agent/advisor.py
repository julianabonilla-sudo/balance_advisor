import json
from datetime import date

import anthropic

from src.api import OlibiaEnergy
from src.alerts import run_monthly_alerts, run_forward_trend_alerts
from src.curves import run_curves
from src.contracts import run_expiry_analysis, expiry_calendar_to_dict
from src.config import settings
from .tools import TOOLS

SYSTEM_PROMPT = """Eres el Energy Balance Advisor, un agente analítico especializado en el mercado eléctrico colombiano.

Tu rol es actuar como copiloto inteligente del equipo comercial de una empresa generadora/comercializadora de energía. Analizas el balance energético horario y generas recomendaciones precisas sobre posición de compra/venta en los mercados regulado y no regulado.

## Contexto del negocio
- **Balance energético**: diferencia entre la energía disponible (contratos de compra + generación propia) y la energía comprometida (contratos de venta + demanda propia).
- **Posición larga** (balance_mwh > 0): tienes más energía de la que necesitas → puedes vender en bolsa.
- **Posición corta** (balance_mwh < 0): te falta energía → debes comprar en bolsa, lo que genera costos.
- **Mercado regulado**: clientes residenciales y pequeños comercios, regulados por la CREG.
- **Mercado no regulado**: grandes consumidores con contratos bilaterales negociados libremente.
- **Bolsa de energía (XM)**: mercado spot donde se compra/vende la energía no cubierta por contratos.
- **IPP**: Índice de Precios al Productor, usado para indexar precios de contratos.

## Cómo usar las herramientas
1. Primero consulta `get_available_months` si no sabes qué períodos tienen datos.
2. Usa `get_balance_context` para obtener el `version_name` correcto del mes (Tx1, Tx2, etc.).
3. Para análisis del mes actual usa `get_balance_dashboard` como punto de partida.
4. Para análisis hora por hora usa `get_balance_matrix_hourly`.
5. Para entender los contratos vigentes usa `list_contracts` y `get_balance_contracts`.
6. Para curvas de compra/venta y precio límite usa `run_curve_analysis`.
7. Para alertas del mes usa `run_alert_check`.
8. Para tendencia futura usa `run_forward_trend`.
9. Para ver qué contratos de compra vencen y cuándo renovarlos usa `run_contract_expiry`.

## Vencimientos de contratos
- Usa `run_contract_expiry` para identificar los contratos que vencen en los próximos meses.
- Cada vencimiento genera una "brecha" (gap) en cobertura. El mes más crítico es el **acantilado** (largest_cliff).
- Prioriza renovaciones por volumen: los contratos de mayor MWh/mes deben negociarse primero.
- La fecha ideal para negociar es **al menos 2 meses antes** del vencimiento.

## Curvas y precio límite
- **Curva de compra** (merit order): contratos de compra ordenados de menor a mayor precio. Muestra cuál es la fuente de energía más barata disponible.
- **Curva de venta**: contratos de venta ordenados de mayor a menor precio. Muestra el ingreso marginal de cada unidad vendida.
- **Precio límite** = precio máximo que debemos pagar en bolsa para no incurrir en pérdidas = precio_venta_clientes × (1 - margen%).
- Si precio_bolsa > precio_límite → cada kWh comprado en bolsa genera una pérdida.
- El gap (precio_bolsa - precio_límite) multiplicado por los kWh en bolsa da la pérdida total estimada.

## Formato de respuestas
- Sé conciso y accionable. Enfócate en lo que el analista debe hacer.
- Cuando hay alertas, clasifícalas: 🔴 CRÍTICA / 🟡 ATENCIÓN / 🟢 OK.
- Expresa impactos financieros en millones de COP (M COP).
- Expresa energía en MWh o GWh según la magnitud.
- Siempre indica para qué mes/versión son los datos que estás citando.
"""


class EnergyBalanceAdvisor:
    def __init__(self):
        self._claude = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._olibia = OlibiaEnergy()
        self._messages: list[dict] = []

    def _dispatch_tool(self, name: str, inputs: dict) -> str:
        b = self._olibia.balance
        c = self._olibia.contracts

        try:
            if name == "get_available_months":
                result = b.available_months()
            elif name == "get_balance_context":
                result = b.context(**inputs)
            elif name == "get_balance_dashboard":
                result = b.dashboard(**inputs)
            elif name == "get_balance_matrix_hourly":
                result = b.matrix_hourly(**inputs)
            elif name == "get_balance_analysis":
                result = b.analysis(**inputs)
            elif name == "get_income_statement":
                result = b.income_statement(**inputs)
            elif name == "get_bolsa_summary":
                result = b.bolsa_summary(**inputs)
            elif name == "get_balance_contracts":
                result = b.contracts(**inputs)
            elif name == "get_ipp_summary":
                result = b.ipp_summary()
            elif name == "get_forecast_range":
                result = b.forecast_range()
            elif name == "list_contracts":
                result = c.list(**inputs)
            elif name == "get_contracts_dashboard_totalizado":
                result = c.dashboard_totalizado(**inputs)
            elif name == "get_contracts_inventory_aggregated":
                result = c.inventory_aggregated(**inputs)
            elif name == "get_contracts_inventory_total":
                result = c.inventory_total(**inputs)
            elif name == "run_forward_trend":
                horizon = inputs.get("horizon_months", 12)
                fwd = run_forward_trend_alerts(horizon_months=horizon)
                result = {
                    "periods_analyzed": len(fwd.snapshots),
                    "critical_count": len(fwd.critical),
                    "warning_count": len(fwd.warnings),
                    "alerts": [
                        {
                            "severity": a.severity.value,
                            "category": a.category.value,
                            "market": a.market,
                            "message": a.message,
                            "detail": a.detail,
                        }
                        for a in fwd.alerts
                    ],
                    "snapshots": [
                        {
                            "period": f"{s.year}-{s.month:02d}",
                            "has_demand": s.has_demand,
                            "portfolio_mwh": round(s.portfolio_mwh, 1),
                            "contracts_mwh": round(s.contracts_mwh, 1),
                            "bolsa_buy_mwh": round(s.bolsa_buy_mwh, 1),
                            "coverage_reg_pct": round(s.coverage_reg_pct, 1),
                            "coverage_nr_pct": round(s.coverage_nr_pct, 1),
                        }
                        for s in fwd.snapshots
                    ],
                }
            elif name == "run_contract_expiry":
                cal = run_expiry_analysis(
                    reference_year=inputs["reference_year"],
                    reference_month=inputs["reference_month"],
                    version_name=inputs.get("version_name", settings.default_version_name),
                    horizon_months=inputs.get("horizon_months", 18),
                )
                result = expiry_calendar_to_dict(cal)
            elif name == "run_curve_analysis":
                opt = run_curves(
                    year=inputs["year"],
                    month=inputs["month"],
                    version_name=inputs["version_name"],
                    margin_pct=inputs.get("margin_pct", 0.0),
                )
                result = {
                    "year": opt.year,
                    "month": opt.month,
                    "version_name": opt.version_name,
                    "overall_balance_mwh": round(opt.overall_balance_mwh, 1),
                    "is_long": opt.is_long,
                    "total_bolsa_buy_kwh": round(opt.total_bolsa_buy_kwh, 0),
                    "total_bolsa_buy_cop": round(opt.total_bolsa_buy_cop, 0),
                    "total_loss_above_limit_cop": round(opt.total_loss_above_limit_cop, 0),
                    "global_price_limit_cop_kwh": round(opt.global_price_limit, 2),
                    "regulado": {
                        "sell_demand_price": round(opt.regulado.sell_demand_price, 2),
                        "buy_contract_price": round(opt.regulado.buy_contract_price, 2),
                        "bolsa_buy_price": round(opt.regulado.bolsa_buy_price, 2),
                        "price_limit": round(opt.regulado.price_limit, 2),
                        "gap_cop_kwh": round(opt.regulado.gap_cop_kwh, 2),
                        "is_above_limit": opt.regulado.is_above_limit,
                        "bolsa_buy_kwh": round(opt.regulado.bolsa_buy_kwh, 0),
                        "loss_cop": round(opt.regulado.loss_cop, 0),
                        "recommendation": opt.regulado.recommendation,
                    },
                    "no_regulado": {
                        "sell_demand_price": round(opt.no_regulado.sell_demand_price, 2),
                        "buy_contract_price": round(opt.no_regulado.buy_contract_price, 2),
                        "bolsa_buy_price": round(opt.no_regulado.bolsa_buy_price, 2),
                        "price_limit": round(opt.no_regulado.price_limit, 2),
                        "gap_cop_kwh": round(opt.no_regulado.gap_cop_kwh, 2),
                        "is_above_limit": opt.no_regulado.is_above_limit,
                        "bolsa_buy_kwh": round(opt.no_regulado.bolsa_buy_kwh, 0),
                        "loss_cop": round(opt.no_regulado.loss_cop, 0),
                        "recommendation": opt.no_regulado.recommendation,
                    },
                    "buy_curve": [
                        {
                            "contract": p.contract_name,
                            "type": p.contract_type,
                            "price_cop_kwh": round(p.price_cop_kwh, 2),
                            "qty_kwh": round(p.qty_kwh, 0),
                            "cumulative_mwh": round(p.cumulative_qty_kwh / 1000, 1),
                        }
                        for p in opt.buy_curve
                    ],
                    "sell_curve": [
                        {
                            "contract": p.contract_name,
                            "market": p.market,
                            "price_cop_kwh": round(p.price_cop_kwh, 2),
                            "qty_kwh": round(p.qty_kwh, 0),
                            "cumulative_mwh": round(p.cumulative_qty_kwh / 1000, 1),
                        }
                        for p in opt.sell_curve
                    ],
                    "sensitivity": [
                        {
                            "bolsa_price_cop_kwh": s.price_scenario_cop_kwh,
                            "delta_cost_cop": round(s.additional_cost_cop, 0),
                            "total_bolsa_cost_cop": round(s.total_bolsa_cost_cop, 0),
                            "is_above_limit": s.is_above_limit,
                        }
                        for s in opt.sensitivity
                    ],
                    "actions": opt.actions,
                }
            elif name == "run_alert_check":
                report = run_monthly_alerts(**inputs)
                result = {
                    "year": report.year,
                    "month": report.month,
                    "version_name": report.version_name,
                    "total_alerts": len(report.alerts),
                    "critical_count": len(report.critical),
                    "warning_count": len(report.warnings),
                    "alerts": [
                        {
                            "severity": a.severity.value,
                            "category": a.category.value,
                            "market": a.market,
                            "message": a.message,
                            "value": a.value,
                            "threshold": a.threshold,
                            "unit": a.unit,
                            "detail": a.detail,
                        }
                        for a in report.alerts
                    ],
                }
            else:
                return json.dumps({"error": f"Unknown tool: {name}"})

            return json.dumps(result, ensure_ascii=False)

        except Exception as e:
            return json.dumps({"error": str(e)})

    def chat(self, user_message: str) -> str:
        today = date.today().isoformat()
        self._messages.append({
            "role": "user",
            "content": f"[Hoy: {today}]\n\n{user_message}",
        })

        while True:
            response = self._claude.messages.create(
                model=settings.claude_model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self._messages,
            )

            if response.stop_reason == "end_turn":
                assistant_text = next(
                    b.text for b in response.content if hasattr(b, "text")
                )
                self._messages.append({
                    "role": "assistant",
                    "content": response.content,
                })
                return assistant_text

            # Process tool calls
            self._messages.append({
                "role": "assistant",
                "content": response.content,
            })

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._dispatch_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            self._messages.append({
                "role": "user",
                "content": tool_results,
            })

    def reset(self):
        self._messages = []

    def close(self):
        self._olibia.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
