"""Tool definitions that Claude uses to query the Olibia Energy API."""

TOOLS = [
    {
        "name": "get_available_months",
        "description": "Returns all months that have balance data loaded (all 4 files: ADEM, TRSD, DSP, contracts). Use this first to know what periods are available.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_balance_context",
        "description": "Returns available version names (e.g. Tx1, Tx2) and daily file coverage (ADEM/TRSD/DSP) for a given month. Call this before other balance endpoints to get the correct version_name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "Year (e.g. 2026)"},
                "month": {"type": "integer", "description": "Month 1-12"},
            },
            "required": ["year", "month"],
        },
    },
    {
        "name": "get_balance_dashboard",
        "description": "Returns KPIs for the month: energy position (MWh) and financial impact (COP) for regulated and unregulated markets. Includes daily breakdown. Key fields: balance_mwh (positive=long/surplus, negative=short/deficit), impact_cop, bolsa_buy/sell.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "month": {"type": "integer"},
                "version_name": {"type": "string", "description": "e.g. Tx1 or Tx2"},
                "with_projected_contracts": {"type": "boolean", "default": False},
            },
            "required": ["year", "month", "version_name"],
        },
    },
    {
        "name": "get_balance_matrix_hourly",
        "description": "Returns the 31x24 hourly matrix with energy position and financial impact per cell (day/hour). Essential for detecting which specific hours have critical long or short positions. grand_total gives the month summary.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "month": {"type": "integer"},
                "version_name": {"type": "string"},
                "with_projected_contracts": {"type": "boolean", "default": False},
            },
            "required": ["year", "month", "version_name"],
        },
    },
    {
        "name": "get_balance_analysis",
        "description": "Returns detailed analysis: waterfall chart data, daily bolsa prices and volumes, top 69 highest-impact hours, top contracts, scatter of contracts by price/qty, and market balance breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "month": {"type": "integer"},
                "version_name": {"type": "string"},
                "with_projected_contracts": {"type": "boolean", "default": False},
            },
            "required": ["year", "month", "version_name"],
        },
    },
    {
        "name": "get_income_statement",
        "description": "Returns the hierarchical income statement (3 levels: market > agent > contract) with buy/sell quantities, average prices, and totals in COP. Includes bolsa cruce and balcttos breakdown.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "month": {"type": "integer"},
                "version_name": {"type": "string"},
                "with_projected_contracts": {"type": "boolean", "default": False},
            },
            "required": ["year", "month", "version_name"],
        },
    },
    {
        "name": "get_bolsa_summary",
        "description": "Returns own bolsa trading summary: buy quantity/price/total, sell quantity/price/total, and net result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "month": {"type": "integer"},
                "version_name": {"type": "string"},
            },
            "required": ["year", "month", "version_name"],
        },
    },
    {
        "name": "get_balance_contracts",
        "description": "Returns all contracts for the month with IPP indexation applied. Shows actual COP prices after indexation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer"},
                "month": {"type": "integer"},
                "version_name": {"type": "string"},
            },
            "required": ["year", "month", "version_name"],
        },
    },
    {
        "name": "get_ipp_summary",
        "description": "Returns the current IPP index value and number of indexed contracts. IPP base is Jan 2000.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_forecast_range",
        "description": "Returns the date range for which demand forecast data is available.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_contracts",
        "description": "Lists all active contracts with their metadata: contract number, provider, market type (REGULADO/NO REGULADO), operation type (COMPRA/VENTA), dates, SIC code, and projected flag.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 100},
                "offset": {"type": "integer", "default": 0},
            },
            "required": [],
        },
    },
    {
        "name": "get_contracts_dashboard_totalizado",
        "description": "Returns Compra/Venta/Total volumes (kWh) per month for a date range. Use this to build buy/sell curves across months.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_date": {"type": "string", "description": "YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "YYYY-MM-DD"},
                "market": {"type": "string", "description": "REGULADO or NO_REGULADO (optional)"},
                "is_projected": {"type": "boolean"},
            },
            "required": ["from_date", "to_date"],
        },
    },
    {
        "name": "get_contracts_inventory_aggregated",
        "description": "Returns the hourly heatmap (24 hours) of net inventory for a period. Each cell shows total_qty and individual contract breakdown. Use to detect hour-level deficit or surplus patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_date": {"type": "string", "description": "YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "YYYY-MM-DD"},
                "market": {"type": "string"},
                "day_type": {"type": "string"},
                "is_projected": {"type": "boolean"},
            },
            "required": ["from_date", "to_date"],
        },
    },
    {
        "name": "get_contracts_inventory_total",
        "description": "Returns total inventory per individual contract for a date range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_date": {"type": "string", "description": "YYYY-MM-DD"},
                "to_date": {"type": "string", "description": "YYYY-MM-DD"},
                "market": {"type": "string"},
                "is_projected": {"type": "boolean"},
            },
            "required": ["from_date", "to_date"],
        },
    },
    {
        "name": "run_forward_trend",
        "description": "Analyzes the next N future months (default 12) to detect worsening trends: portfolio drop month-over-month (contract expiry risk) for future months without demand data, and bolsa buy increases or coverage drops for months with real demand. Use this for medium-term risk assessment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "horizon_months": {"type": "integer", "default": 12, "description": "Number of future months to analyze (default 12)"},
            },
            "required": [],
        },
    },
    {
        "name": "run_contract_expiry",
        "description": (
            "Analyzes buy contract expirations over the next N months. For each month where "
            "contracts expire, shows: which contracts, their monthly volume (MWh), price "
            "(COP/kWh), market (regulado/no_regulado), and the total MWh coverage lost. "
            "Identifies the largest 'cliff' event where the portfolio drops most sharply. "
            "Essential for planning contract renewals before coverage gaps appear."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reference_year": {"type": "integer", "description": "Reference year for the analysis base (e.g. 2026)"},
                "reference_month": {"type": "integer", "description": "Reference month 1-12"},
                "version_name": {"type": "string", "description": "e.g. Tx2"},
                "horizon_months": {"type": "integer", "default": 18, "description": "Months to scan ahead (default 18)"},
            },
            "required": ["reference_year", "reference_month", "version_name"],
        },
    },
    {
        "name": "run_curve_analysis",
        "description": (
            "Builds buy/sell curves (curvas de compra/venta) and computes the price limit "
            "(precio límite) for each market. The buy curve shows contracts sorted by price "
            "(cheapest first, merit order). The sell curve shows what clients pay (highest "
            "first). The price limit is the maximum bolsa price before incurring losses. "
            "Returns: curves, price_limit per market, gap vs current bolsa price, estimated "
            "loss in COP, sensitivity table (bolsa ±20%), and actionable recommendations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "Year (e.g. 2026)"},
                "month": {"type": "integer", "description": "Month 1-12"},
                "version_name": {"type": "string", "description": "e.g. Tx1 or Tx2"},
                "margin_pct": {
                    "type": "number",
                    "description": "Required margin above breakeven in % (default 0 = breakeven). E.g. 10 means limit = sell_price × 0.90.",
                    "default": 0.0,
                },
            },
            "required": ["year", "month", "version_name"],
        },
    },
    {
        "name": "run_alert_check",
        "description": "Runs the full alert engine for a given month: checks position exposure, financial impact, demand coverage, bolsa price spikes, and hourly matrix exposure. Returns a structured report with CRITICA/ATENCION alerts classified by category.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "Year (e.g. 2026)"},
                "month": {"type": "integer", "description": "Month 1-12"},
                "version_name": {"type": "string", "description": "e.g. Tx1 or Tx2"},
            },
            "required": ["year", "month", "version_name"],
        },
    },
]
