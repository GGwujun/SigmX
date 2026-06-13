"""Credit costs for metered operations."""

# Cost in integer credits to run each metered analysis pipeline.
# Scanning (opportunities / fund premium) and viewing reports stay free —
# only the heavy multi-agent report generation is metered.
COST_ALPHA_FORGE = 50       # 16-agent individual-stock research report
COST_FUND_ARBITRAGE = 20    # 6-agent fund arbitrage deep report

# Default redeem-code lifetime when generated via the script (days).
DEFAULT_CODE_TTL_DAYS = 90

# Transaction type labels (stored in credit_transactions.type).
TX_REDEEM = "redeem"        # redeemed a code (+)
TX_CONSUME = "consume"      # ran a metered analysis (-)
TX_REFUND = "refund"        # analysis failed, credits returned (+)
TX_ADMIN = "admin"          # manual adjustment (+/-)
