# What is the Model Context Protocol (MCP)?

MCP (Model Context Protocol) is an open-source standard for connecting AI applications to external systems.

Using MCP, AI applications like Claude or ChatGPT can connect to data sources (e.g. local files, databases), tools (e.g. search engines, calculators) and workflows (e.g. specialized prompts)—enabling them to access key information and perform tasks.

Think of MCP like a USB-C port for AI applications. Just as USB-C provides a standardized way to connect electronic devices, MCP provides a standardized way to connect AI applications to external systems.

## What can MCP enable?

- Agents can access your Google Calendar and Notion, acting as a more personalized AI assistant.
- Claude Code can generate an entire web app using a Figma design.
- Enterprise chatbots can connect to multiple databases across an organization, empowering users to analyze data using chat.
- AI models can create 3D designs on Blender and print them out using a 3D printer.

## Why does MCP matter?

Depending on where you sit in the ecosystem, MCP can have a range of benefits.

- **Developers**: MCP reduces development time and complexity when building, or integrating with, an AI application or agent.
- **AI applications or agents**: MCP provides access to an ecosystem of data sources, tools and apps which will enhance capabilities and improve the end-user experience.
- **End-users**: MCP results in more capable AI applications or agents which can access your data and take actions on your behalf when necessary.

## Broad ecosystem support

MCP is an open protocol supported across a wide range of clients and servers. AI assistants like [Claude](https://claude.com/docs/connectors/building) and [ChatGPT](https://developers.openai.com/api/docs/mcp/), development tools like [Visual Studio Code](https://code.visualstudio.com/docs/copilot/chat/mcp-servers), [Cursor](https://cursor.com/docs/context/mcp), [MCPJam](https://docs.mcpjam.com/getting-started), and many others all support MCP — making it easy to build once and integrate everywhere.

## Start building

- **Build servers** — Create MCP servers to expose your data and tools.
- **Build clients** — Develop applications that connect to MCP servers.
- **Build MCP Apps** — Build interactive apps that run inside AI clients.

## Learn more

- **Understand concepts** — Learn the core concepts and architecture of MCP.

# nando

## Monthly drawdown guard

`nando/drawdown_guard.py` implements a capital-preservation rule: trading
halts once account equity falls 10% or more below the equity recorded at the
start of the current calendar month.

```python
from nando.drawdown_guard import MonthlyDrawdownGuard, TradingGuardrail

guard = MonthlyDrawdownGuard("state/drawdown.json", limit_pct=0.10)

# Call once per equity update (e.g. before every trade decision).
# Raises DrawdownLimitBreached if the monthly loss limit has been hit.
guard.guard(current_equity)
```

`TradingGuardrail` wraps a trade-execution callable so orders are refused
once the limit is breached:

```python
guardrail = TradingGuardrail(
    guard=guard,
    get_equity=my_broker.get_account_equity,
    place_order=my_broker.place_order,
)
guardrail.place_order_if_allowed("AAPL", 10)
```

The guard has no dependency on any specific broker - `get_equity` and
`place_order` are adapters you provide, e.g. thin wrappers around a
connected trading MCP server's tools.

The baseline (start-of-month equity) is persisted to `state_path` as JSON so
it survives process restarts, and rolls over automatically at the start of
each calendar month.

### Robinhood adapter

`nando/robinhood_adapter.py` wires the guard into Robinhood's Agentic
Trading MCP (`https://agent.robinhood.com/mcp/trading`), verified against
the live tool schema:

```python
from nando.drawdown_guard import MonthlyDrawdownGuard, TradingGuardrail
from nando.robinhood_adapter import RobinhoodAdapter

# `session` is an already-authenticated MCP client session connected to
# the Robinhood trading server. `account_number` must be an
# agentic_allowed=true account (from get_accounts) - Robinhood rejects
# orders against the main brokerage account.
adapter = RobinhoodAdapter(session, account_number="...")
guard = MonthlyDrawdownGuard("state/drawdown.json")
guardrail = TradingGuardrail(guard=guard, get_equity=adapter.get_equity, place_order=adapter.place_order)

# Real money: review first, then only pass confirm=True once the user has
# seen the estimated cost/alerts and explicitly agreed.
adapter.review_order("AAPL", side="buy", type="market", quantity=10)
guardrail.place_order_if_allowed("AAPL", side="buy", type="market", quantity=10, confirm=True)
```

`place_order` raises `OrderNotConfirmed` unless called with `confirm=True` -
this mirrors Robinhood's own tool contract, which expects `review_equity_order`
to run first and the order to be explicitly confirmed before
`place_equity_order` executes with real money. The monthly drawdown check
and the per-order confirmation gate are independent safeguards: both must
pass for an order to go through.

### Pre-market status check

`nando/premarket_check.py` provides a read-only report of drawdown status -
useful for a pre-market routine that just wants to see where things stand
before any trading decision is made. Unlike `guard.guard()`, it never
raises on a breach; it just returns a `DrawdownStatus` snapshot.

```python
from nando.drawdown_guard import MonthlyDrawdownGuard
from nando.premarket_check import premarket_check
from nando.robinhood_adapter import RobinhoodAdapter

adapter = RobinhoodAdapter(session, account_number="...")
guard = MonthlyDrawdownGuard("state/drawdown.json")

status = premarket_check(guard, adapter.get_equity)
print(status)
# [OK] 2026-08: equity 9,500.00 vs baseline 10,000.00 (-5.00%), limit -10%, headroom +5.00%

if status.breached:
    ...  # skip today's trading routine, alert, etc.
```

`MonthlyDrawdownGuard.status(equity)` returns the same `DrawdownStatus` and
can be called directly if you already have equity on hand.

Run the tests with:

```bash
pip install pytest
python3 -m pytest
```
