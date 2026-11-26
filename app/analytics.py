"""Deterministic analytics. Every intent maps to a fixed, parameterised SQL query.
The LLM never writes SQL; only whitelisted column names are interpolated."""
from datetime import datetime

DIM_COL = {"product": "product", "region": "region", "category": "category",
           "channel": "sales_channel", "month": "order_month"}
GROUPABLE = ["product", "region", "category", "channel"]


def inr(x):
    """Format with the rupee symbol and Indian digit grouping, e.g. ₹14,39,200."""
    neg = x < 0
    whole, frac = divmod(round(abs(float(x)), 2), 1)
    s = str(int(whole))
    if len(s) > 3:
        head, tail, parts = s[:-3], s[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    if frac:
        s += f".{int(round(frac * 100)):02d}"
    return f"{'-' if neg else ''}₹{s}"


def month_label(m):
    return datetime.strptime(m + "-01", "%Y-%m-%d").strftime("%B %Y")


def _where(filters, extra=None):
    clauses, args = list(extra or []), []
    for dim, val in (filters or {}).items():
        clauses.append(f"{DIM_COL[dim]} = ?")  # KeyError => unknown dim, never reaches SQL
        args.append(val)
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def _scope(filters):
    return "".join(f" [{k}: {month_label(v) if k == 'month' else v}]" for k, v in (filters or {}).items())


def _run(conn, sql, args):
    return [dict(r) for r in conn.execute(sql, args)]


def _types(d):
    return {d: "text", "revenue": "inr", "orders": "int", "units": "int"}


def total_revenue(conn, filters):
    where, args = _where(filters)
    sql = ("SELECT COALESCE(SUM(revenue),0) AS revenue, COUNT(*) AS orders, "
           "COALESCE(SUM(quantity),0) AS units, COALESCE(SUM(discount_amount),0) AS discounts "
           f"FROM sales{where}")
    rows = _run(conn, sql, args)
    r = rows[0]
    if r["orders"] == 0:
        ans = f"No matching sales found{_scope(filters)}."
    else:
        ans = f"Total revenue{_scope(filters)} is {inr(r['revenue'])} from {r['orders']} orders ({r['units']} units)."
    return dict(answer=ans, rows=rows, sql=sql, params=args,
                column_types={"revenue": "inr", "orders": "int", "units": "int", "discounts": "inr"})


def _breakdown(conn, filters, dimension):
    col = DIM_COL[dimension]
    where, args = _where(filters)
    sql = (f"SELECT {col} AS {dimension}, SUM(revenue) AS revenue, COUNT(*) AS orders, SUM(quantity) AS units "
           f"FROM sales{where} GROUP BY {col} ORDER BY revenue DESC, {col}")
    return sql, args, _run(conn, sql, args)


def revenue_breakdown(conn, filters, dimension):
    sql, args, rows = _breakdown(conn, filters, dimension)
    if not rows:
        ans = f"No matching sales found{_scope(filters)}."
    else:
        ans = f"Revenue by {dimension}{_scope(filters)}: " + ", ".join(
            f"{r[dimension]} {inr(r['revenue'])}" for r in rows) + "."
    return dict(answer=ans, rows=rows, sql=sql, params=args, column_types=_types(dimension))


def top_by(conn, filters, dimension, order="desc", limit=1):
    sql, args, rows = _breakdown(conn, filters, dimension)
    if not rows:
        return dict(answer=f"No matching sales found{_scope(filters)}.", rows=[], sql=sql, params=args,
                    column_types=_types(dimension))
    ranked = rows if order == "desc" else sorted(rows, key=lambda r: (r["revenue"], r[dimension]))
    word = "highest" if order == "desc" else "lowest"
    if limit > 1:
        pick = ranked[:limit]
        lead = "Top" if order == "desc" else "Bottom"
        ans = f"{lead} {len(pick)} {dimension}s by revenue{_scope(filters)}: " + ", ".join(
            f"{r[dimension]} ({inr(r['revenue'])})" for r in pick) + "."
    else:
        best = ranked[0]
        ans = f"{best[dimension]} has the {word} revenue{_scope(filters)} at {inr(best['revenue'])} ({best['orders']} orders)."
        ties = [r[dimension] for r in ranked[1:] if r["revenue"] == best["revenue"]]
        if ties:
            ans += f" Tied with: {', '.join(ties)}."
    return dict(answer=ans, rows=ranked, sql=sql, params=args, column_types=_types(dimension))


def monthly_trend(conn, filters):
    where, args = _where(filters)
    sql = ("SELECT order_month AS month, SUM(revenue) AS revenue, COUNT(*) AS orders "
           f"FROM sales{where} GROUP BY order_month ORDER BY order_month")
    rows = _run(conn, sql, args)
    prev = None
    for r in rows:
        r["mom_change_pct"] = round((r["revenue"] - prev) / prev * 100, 1) if prev else None
        prev = r["revenue"]
    if not rows:
        ans = f"No matching sales found{_scope(filters)}."
    else:
        hi = max(rows, key=lambda r: r["revenue"])
        lo = min(rows, key=lambda r: r["revenue"])
        ans = (f"Monthly revenue{_scope(filters)}: "
               + ", ".join(f"{month_label(r['month'])[:3]} {inr(r['revenue'])}" for r in rows)
               + f". Peak: {month_label(hi['month'])}; lowest: {month_label(lo['month'])}.")
    return dict(answer=ans, rows=rows, sql=sql, params=args,
                column_types={"month": "text", "revenue": "inr", "orders": "int", "mom_change_pct": "pct"})


def month_comparison(conn, filters, month_a, month_b):
    where, fargs = _where(filters, extra=["order_month IN (?, ?)"])
    args = [month_a, month_b] + fargs  # the IN (?, ?) placeholders come first
    sql = ("SELECT order_month AS month, SUM(revenue) AS revenue, COUNT(*) AS orders "
           f"FROM sales{where} GROUP BY order_month")
    found = {r["month"]: r for r in _run(conn, sql, args)}
    rows = [{"month": m, "revenue": found.get(m, {}).get("revenue", 0.0),
             "orders": found.get(m, {}).get("orders", 0), "change_pct": None} for m in (month_a, month_b)]
    a, b = rows[0]["revenue"], rows[1]["revenue"]
    diff = b - a
    pct = round(diff / a * 100, 1) if a else None
    rows.append({"month": "Change", "revenue": diff, "orders": rows[1]["orders"] - rows[0]["orders"],
                 "change_pct": pct})
    direction = "increased" if diff > 0 else "decreased" if diff < 0 else "did not change"
    ans = (f"Revenue{_scope(filters)} {direction} from {inr(a)} in {month_label(month_a)} "
           f"to {inr(b)} in {month_label(month_b)}")
    if diff:
        ans += f" ({'+' if diff > 0 else '-'}{inr(abs(diff))}"
        ans += f", {pct:+.1f}%)" if pct is not None else ", % undefined: base month has no revenue)"
    ans += "."
    return dict(answer=ans, rows=rows, sql=sql, params=args,
                column_types={"month": "text", "revenue": "inr", "orders": "int", "change_pct": "pct"})


def run_plan(conn, plan):
    i, f = plan["intent"], plan.get("filters", {})
    if i == "total_revenue":
        return total_revenue(conn, f)
    if i == "breakdown":
        return revenue_breakdown(conn, f, plan["dimension"])
    if i == "top_by":
        return top_by(conn, f, plan["dimension"], plan.get("order", "desc"), plan.get("limit", 1))
    if i == "monthly_trend":
        return monthly_trend(conn, f)
    if i == "month_comparison":
        return month_comparison(conn, f, plan["month_a"], plan["month_b"])
    raise ValueError(f"unknown intent {i}")
