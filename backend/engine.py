"""FinVerse simulation engine.

Pure Python (no numpy/pydantic) so the Lambda package stays tiny and needs no
platform-specific wheels. 1000 paths x 10 years runs in well under a second.
"""
import math
import random
import re
from datetime import date

SAVINGS_RETURN = 0.035  # annual interest on cash savings


def _sc(label, **kw):
    base = {
        "label": label,
        "market_shock": 0.0,       # one-month extra return hit on investments
        "shock_month": 0,
        "income_loss_start": 0,    # month income stops
        "income_loss_months": 0,   # how long income stays at zero
        "expense_increase": 0.0,   # fractional rise in expenses
        "expense_months": 0,       # how long the rise lasts
    }
    base.update(kw)
    return base


SCENARIOS = {
    "baseline": _sc("Baseline"),
    "market_crash": _sc("Market crash (-35%)", market_shock=-0.35, shock_month=6),
    "job_loss": _sc("Job loss (8 months)", income_loss_start=6, income_loss_months=8),
    "inflation": _sc("Inflation spike (+25% expenses, 3 yrs)", expense_increase=0.25, expense_months=36),
    "perfect_storm": _sc(
        "Perfect storm (crash + job loss + inflation)",
        market_shock=-0.30, shock_month=6,
        income_loss_start=6, income_loss_months=6,
        expense_increase=0.15, expense_months=24,
    ),
}


# -------------------------------------------------------------------- EMI
def monthly_emi(amount, annual_rate_pct, tenure_years):
    """Standard reducing-balance EMI, rounded to the nearest rupee
    (the frontend uses the same formula so budget totals always match)."""
    n = int(round(tenure_years * 12))
    if amount <= 0 or n <= 0:
        return 0
    r = annual_rate_pct / 100 / 12
    if r == 0:
        return int(amount / n + 0.5)
    f = (1 + r) ** n
    return int(amount * r * f / (f - 1) + 0.5)


# ---------------------------------------------------------------- validation
def clean_twin(raw):
    if not isinstance(raw, dict):
        raise ValueError("Body must be a JSON object")
    uid = str(raw.get("user_id", "")).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", uid):
        raise ValueError("user_id must be 1-40 letters, digits, - or _")

    def num(src, key, default=None, lo=0.0, hi=1e12):
        v = src.get(key, default)
        try:
            v = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number")
        if math.isnan(v) or not (lo <= v <= hi):
            raise ValueError(f"{key} must be between {lo:g} and {hi:g}")
        return v

    twin = {
        "user_id": uid,
        "name": (str(raw.get("name") or uid).strip() or uid)[:40],
        "monthly_income": num(raw, "monthly_income"),
        "monthly_expenses": num(raw, "monthly_expenses"),
        "monthly_sip": num(raw, "monthly_sip", 0),
        "current_savings": num(raw, "current_savings"),
        "current_investments": num(raw, "current_investments", 0),  # SIP corpus built so far
        "investment_return_mean": num(raw, "investment_return_mean", 0.10, -0.5, 0.5),
        "investment_return_std": num(raw, "investment_return_std", 0.15, 0.0, 1.0),
        "income_growth": num(raw, "income_growth", 0.06, -0.5, 0.5),
        "expense_growth": num(raw, "expense_growth", 0.05, -0.5, 0.5),
        "loans": [],
        "goals": [],
    }
    this_year = date.today().year
    for l in (raw.get("loans") or [])[:10]:
        amount = num(l, "amount")
        rate = num(l, "interest_rate", 0, 0, 100)
        years = num(l, "tenure_years", 5, 0.25, 40)
        twin["loans"].append({
            "name": str(l.get("name") or "Loan")[:40],
            "amount": amount,
            "interest_rate": rate,
            "tenure_years": years,
            "monthly_payment": monthly_emi(amount, rate, years),  # auto-calculated EMI
        })
    for g in (raw.get("goals") or [])[:10]:
        twin["goals"].append({
            "name": str(g.get("name") or "Goal")[:40],
            "target_amount": num(g, "target_amount", None, 1, 1e13),
            "target_year": int(num(g, "target_year", None, this_year, this_year + 40)),
        })

    # Requirement: monthly outgo must fit within monthly income
    if twin["monthly_income"] <= 0:
        raise ValueError("Monthly income must be greater than zero")
    emi_total = sum(l["monthly_payment"] for l in twin["loans"])
    outgo = twin["monthly_expenses"] + twin["monthly_sip"] + emi_total
    if outgo > twin["monthly_income"] + 0.5:
        raise ValueError(
            f"Expenses + SIP + EMIs (₹{outgo:,.0f}) exceed monthly income (₹{twin['monthly_income']:,.0f})"
        )
    return twin


# ----------------------------------------------------------------- DNA label
def financial_dna(twin):
    inc, exp = twin["monthly_income"], twin["monthly_expenses"]
    loan_pay = sum(l["monthly_payment"] for l in twin["loans"])
    sip = twin.get("monthly_sip", 0)
    sav = twin["current_savings"]
    savings_rate = (inc - exp - loan_pay) / inc * 100 if inc > 0 else -100.0  # saved + invested share
    debt_ratio = loan_pay / inc * 100 if inc > 0 else 100.0
    runway = sav / exp if exp > 0 else 0.0
    sip_rate = sip / inc * 100 if inc > 0 else 0.0

    score = (
        min(40, max(0, savings_rate) * 1.33)
        + 25 * (1 - min(1, debt_ratio / 50))
        + min(20, runway / 6 * 20)
        + min(15, sip_rate / 20 * 15)
    )
    if debt_ratio >= 40:
        name, tag = "The Debt Juggler", "A big slice of income goes to EMIs. Freeing it up is the fastest win."
    elif savings_rate < 0:
        name, tag = "The Overspender", "Spending more than you earn. Fix this before anything else."
    elif savings_rate < 10:
        name, tag = "The Tightrope Walker", "Balanced, but one shock away from trouble."
    elif savings_rate < 25:
        name, tag = "The Steady Saver", "Healthy habits. Consistency will do the heavy lifting."
    elif sip_rate >= 15:
        name, tag = "The Wealth Builder", "High savings and a strong SIP habit working for you."
    else:
        name, tag = "The Safe Saver", "Great savings rate. Consider putting more into SIPs."
    return {
        "archetype": name,
        "tagline": tag,
        "score": round(max(0, min(100, score))),
        "savings_rate": round(savings_rate, 1),
        "debt_ratio": round(debt_ratio, 1),
        "runway_months": round(runway, 1),
        "sip_rate": round(sip_rate, 1),
    }


# ---------------------------------------------------------------- simulation
def _pct(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p / 100
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def simulate(twin, years=10, num_paths=1000, scenario="baseline", seed=None):
    sc = SCENARIOS[scenario]
    rng = random.Random(seed)
    y0 = date.today().year
    goals = twin.get("goals", [])
    ytg = [max(1, g["target_year"] - y0) for g in goals]
    horizon = min(40, max([years] + ytg))
    months = horizon * 12

    mu_m = twin["investment_return_mean"] / 12
    sd_m = twin["investment_return_std"] / math.sqrt(12)
    sav_m = SAVINGS_RETURN / 12
    sip = twin.get("monthly_sip", 0.0)
    loans = [(l["amount"], l["interest_rate"] / 100 / 12, l["monthly_payment"]) for l in twin["loans"]]
    start_nw = twin["current_savings"] + twin["current_investments"] - sum(l[0] for l in loans)

    yearly = [[] for _ in range(horizon)]
    ruined = 0
    for _ in range(num_paths):
        sav, inv = twin["current_savings"], twin["current_investments"]
        bal = [l[0] for l in loans]
        inc, exp = twin["monthly_income"], twin["monthly_expenses"]
        ran_out = False
        for m in range(months):
            if m and m % 12 == 0:
                inc *= 1 + twin["income_growth"] + rng.gauss(0, 0.02)
                exp *= 1 + twin["expense_growth"]
            r = rng.gauss(mu_m, sd_m)
            if sc["market_shock"] and m == sc["shock_month"]:
                r += sc["market_shock"]
            inv *= max(0.05, 1 + r)
            if sav > 0:
                sav *= 1 + sav_m

            lost = sc["income_loss_start"] <= m < sc["income_loss_start"] + sc["income_loss_months"]
            i_m = 0.0 if lost else inc
            e_m = exp * (1 + sc["expense_increase"]) if m < sc["expense_months"] else exp

            pay = 0.0
            for k, (_, rate, emi) in enumerate(loans):
                b = bal[k]
                if b > 0:
                    b += b * rate
                    p = min(emi, b)
                    bal[k] = b - p
                    pay += p

            net = i_m - e_m - pay
            if net >= 0:
                s = min(sip, net)      # SIP is paid first, the rest becomes cash savings
                inv += s
                sav += net - s
            else:
                d = -net               # shortfall: SIP pauses, draw cash then investments
                t = min(max(sav, 0.0), d)
                sav -= t
                d -= t
                if d > 0:
                    t = min(inv, d)
                    inv -= t
                    d -= t
                if d > 0:
                    sav -= d           # forced borrowing
                    ran_out = True
            if (m + 1) % 12 == 0:
                yearly[m // 12].append(sav + inv - sum(bal))
        if ran_out:
            ruined += 1

    n = num_paths
    sorted_years = [sorted(y) for y in yearly]
    series = {
        "years": [y0 + i + 1 for i in range(horizon)],
        "p10": [round(_pct(s, 10)) for s in sorted_years],
        "p50": [round(_pct(s, 50)) for s in sorted_years],
        "p90": [round(_pct(s, 90)) for s in sorted_years],
    }
    final = sorted_years[years - 1]
    lo, hi = final[0], final[-1]
    bins = 20
    width = (hi - lo) / bins or 1.0
    counts = [0] * bins
    for v in final:
        counts[min(bins - 1, int((v - lo) / width))] += 1
    hist = {"centers": [round(lo + width * (i + 0.5)) for i in range(bins)], "counts": counts}

    goal_out = []
    for g, k in zip(goals, ytg):
        hit = sum(1 for v in yearly[k - 1] if v >= g["target_amount"])
        goal_out.append({
            "name": g["name"], "target_amount": g["target_amount"],
            "target_year": g["target_year"], "probability": round(hit / n * 100, 1),
        })

    p5, p50 = _pct(final, 5), _pct(final, 50)
    return {
        "scenario": scenario,
        "scenario_label": sc["label"],
        "years": years,
        "chart_years": horizon,
        "num_paths": n,
        "start_net_worth": round(start_nw),
        "best_case": round(_pct(final, 90)),
        "median_case": round(p50),
        "worst_case": round(_pct(final, 10)),
        "mean": round(sum(final) / n),
        "var_95": round(p50 - p5),
        "ruin_probability": round(ruined / n * 100, 1),
        "goal_probability": round(sum(x["probability"] for x in goal_out) / len(goal_out), 1) if goal_out else None,
        "goals": goal_out,
        "yearly": series,
        "histogram": hist,
    }
