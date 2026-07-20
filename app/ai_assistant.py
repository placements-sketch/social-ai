"""
Customer Profiling AI assistant — Claude tool-calling endpoint.

The AI translates natural-language questions into calls to the SAFE, vetted
tools in ai_query.py. It never sees the database or writes SQL — it only fills
in allow-listed parameters. We run the tool, feed the result back, and Claude
phrases the answer. Returns prose + raw rows (for the frontend table).
"""
import json

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required

from app import limiter
from app.auth import get_current_user
from app.ai_query import query_customers, aggregate_orders
from app.utils.logger import log_event

ai_assistant_bp = Blueprint('ai_assistant', __name__)

MODEL = 'claude-haiku-4-5'
MAX_TOOL_TURNS = 4  # safety cap on the tool-use loop

# ── Tool schemas exposed to Claude ────────────────────────────────────────
TOOLS = [
    {
        "name": "query_customers",
        "description": (
            "Filter, sort, and rank customers by their LIFETIME figures "
            "(total_spent, total_orders) from the customer cache. Use for questions "
            "about all-time spenders, customers in a city, customers by segment, "
            "who hasn't ordered recently, etc. NOT for time-windowed spend — for "
            "'this month'/'last 30 days' spend, use aggregate_orders instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filters": {
                    "type": "object",
                    "description": (
                        "Optional filters. Allowed keys: city (text), country (text), "
                        "segment (one of: vip, loyal, regular, new, never_bought, at_risk, churned), "
                        "accepts_marketing (bool), min_total_spent, max_total_spent, "
                        "min_total_orders, max_total_orders (numbers)."
                    ),
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["total_spent", "total_orders", "last_order_date", "first_order_date"],
                },
                "order": {"type": "string", "enum": ["asc", "desc"]},
                "limit": {"type": "integer", "description": "Max rows, capped at 50."},
            },
        },
    },
    {
        "name": "aggregate_orders",
        "description": (
            "Aggregate the ORDERS cache over a time window — use this for any "
            "question about spend/orders WITHIN a period ('this month', 'last 30 days'), "
            "or revenue grouped by customer, city, or segment. This is the only tool "
            "that understands time windows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "time_window": {
                    "type": "string",
                    "enum": ["this_month", "last_7_days", "last_30_days", "last_90_days", "this_year", "all_time"],
                },
                "group_by": {"type": "string", "enum": ["customer", "city", "segment"]},
                "metric": {"type": "string", "enum": ["sum_spend", "order_count", "aov"]},
                "city": {"type": "string", "description": "Optional city filter."},
                "segment": {"type": "string", "description": "Optional segment filter."},
                "limit": {"type": "integer", "description": "Max rows, capped at 50."},
            },
            "required": ["time_window"],
        },
    },
]

_TOOL_FUNCS = {
    "query_customers": query_customers,
    "aggregate_orders": aggregate_orders,
}

SYSTEM_PROMPT = (
    "You are the customer-analytics assistant for Shop Zetu, a Kenyan fashion brand. "
    "You answer staff questions about customers and orders using ONLY the provided tools. "
    "Money is in Kenyan Shillings (KES). Be concise and specific: lead with the direct "
    "answer, then a short supporting sentence if useful. When a tool returns rows, "
    "summarise the key takeaway in prose — do NOT dump every row in text (the UI shows "
    "the table). If a tool returns a 'note' about ignored filters or sparse data, mention "
    "it briefly. If a question can't be answered with the tools, say so plainly and suggest "
    "what you CAN answer. Never invent numbers."
)


@ai_assistant_bp.route('/ai/customer-query', methods=['POST'])
@jwt_required()
@limiter.limit("20 per minute")
def customer_query():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    if user.role not in ('admin', 'supervisor'):
        return jsonify({'error': 'Not authorized'}), 403

    body = request.get_json(silent=True) or {}
    question = (body.get('question') or '').strip()
    history = body.get('history') or []   # [{role, content}], prior turns for follow-ups
    if not question:
        return jsonify({'error': 'question is required'}), 400
    if len(question) > 1000:
        return jsonify({'error': 'question too long'}), 400

    try:
        import anthropic
        from flask import current_app
        client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"])
    except Exception as e:
        log_event("error", "ai_assistant.client_init", str(e))
        return jsonify({'error': 'AI is not configured'}), 503

    # Build the conversation. History is prior user/assistant TEXT only.
    messages = []
    for h in history[-6:]:
        role = h.get('role')
        content = h.get('content')
        if role in ('user', 'assistant') and content:
            messages.append({"role": role, "content": str(content)[:2000]})
    messages.append({"role": "user", "content": question})

    collected_rows = []   # raw rows from the last data-returning tool, for the UI
    last_tool = None

    try:
        for _turn in range(MAX_TOOL_TURNS):
            resp = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )

            if resp.stop_reason == 'tool_use':
                # Append the assistant's tool-use turn verbatim.
                messages.append({"role": "assistant", "content": resp.content})
                tool_results = []
                for block in resp.content:
                    if block.type != 'tool_use':
                        continue
                    fn = _TOOL_FUNCS.get(block.name)
                    if fn is None:
                        result = {"error": f"unknown tool {block.name}"}
                    else:
                        try:
                            result = fn(**(block.input or {}))
                            if isinstance(result, dict) and 'rows' in result:
                                collected_rows = result['rows']
                                last_tool = block.name
                        except Exception as e:
                            log_event("warn", "ai_assistant.tool_error", f"{block.name}: {e}")
                            result = {"error": "tool execution failed"}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })
                messages.append({"role": "user", "content": tool_results})
                continue  # loop back so Claude can read results and answer

            # Final text answer.
            answer = "".join(b.text for b in resp.content if b.type == 'text').strip()
            log_event("info", "ai_assistant.answered",
                      f"Customer query answered ({last_tool or 'no tool'})",
                      payload={"question": question[:200], "tool": last_tool, "rows": len(collected_rows)})
            return jsonify({
                'answer': answer or "I couldn't produce an answer for that.",
                'rows': collected_rows,
                'tool': last_tool,
            }), 200

        # Exhausted the loop without a final answer.
        return jsonify({
            'answer': "That question needed too many steps to resolve. Try narrowing it.",
            'rows': collected_rows,
            'tool': last_tool,
        }), 200

    except Exception as e:
        log_event("error", "ai_assistant.failure", str(e))
        return jsonify({'error': 'The assistant hit an error. Try rephrasing.'}), 500