import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import app  # noqa: E402
import engine  # noqa: E402

TWIN = {
    "user_id": "t1", "name": "Test User",
    "monthly_income": 100000, "monthly_expenses": 55000, "monthly_sip": 15000,
    "current_savings": 300000, "current_investments": 500000,
    "loans": [{"name": "Car", "amount": 400000, "interest_rate": 9, "tenure_years": 3}],
    "goals": [{"name": "House", "target_amount": 8000000, "target_year": 2035}],
}


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.twin = engine.clean_twin(TWIN)

    def test_emi(self):
        self.assertEqual(engine.monthly_emi(100000, 12, 1), 8885)
        self.assertEqual(engine.monthly_emi(120000, 0, 1), 10000)
        self.assertEqual(self.twin["loans"][0]["monthly_payment"], engine.monthly_emi(400000, 9, 3))

    def test_budget_rule(self):
        emi = self.twin["loans"][0]["monthly_payment"]
        exact = dict(TWIN, monthly_expenses=100000 - 15000 - emi)  # outgo == income is allowed
        engine.clean_twin(exact)
        with self.assertRaises(ValueError):
            engine.clean_twin(dict(exact, monthly_expenses=exact["monthly_expenses"] + 5))
        with self.assertRaises(ValueError):
            engine.clean_twin(dict(TWIN, monthly_income=0))

    def test_percentile_order_and_shape(self):
        r = engine.simulate(self.twin, years=10, num_paths=500, seed=1)
        self.assertLessEqual(r["worst_case"], r["median_case"])
        self.assertLessEqual(r["median_case"], r["best_case"])
        self.assertEqual(len(r["yearly"]["p50"]), r["chart_years"])
        self.assertEqual(sum(r["histogram"]["counts"]), 500)
        self.assertTrue(0 <= r["goals"][0]["probability"] <= 100)

    def test_sip_increases_wealth(self):
        with_sip = engine.simulate(self.twin, 10, 400, seed=5)
        no_sip = engine.simulate(dict(self.twin, monthly_sip=0), 10, 400, seed=5)
        self.assertGreater(with_sip["median_case"], no_sip["median_case"])

    def test_stress_hurts(self):
        base = engine.simulate(self.twin, 10, 500, "baseline", seed=2)
        for s in ("market_crash", "job_loss", "inflation", "perfect_storm"):
            r = engine.simulate(self.twin, 10, 500, s, seed=2)
            self.assertLess(r["median_case"], base["median_case"], s)

    def test_no_income_means_ruin(self):
        t = dict(self.twin, monthly_income=0, monthly_expenses=0, monthly_sip=0,
                 current_investments=0, current_savings=0, goals=[])
        self.assertGreater(engine.simulate(t, 1, 100, seed=3)["ruin_probability"], 99)

    def test_dna(self):
        d = engine.financial_dna(self.twin)
        self.assertTrue(0 <= d["score"] <= 100)
        self.assertEqual(engine.financial_dna(dict(self.twin, monthly_expenses=200000))["archetype"], "The Overspender")

    def test_validation(self):
        with self.assertRaises(ValueError):
            engine.clean_twin(dict(TWIN, monthly_income="abc"))
        with self.assertRaises(ValueError):
            engine.clean_twin(dict(TWIN, user_id="bad id!"))

    def test_api_async_flow(self):
        self.assertEqual(app.route("POST", "/twin", TWIN)[0], 200)
        self.assertEqual(app.route("POST", "/twin", dict(TWIN, monthly_expenses=99000))[0], 400)
        st, out = app.route("POST", "/simulate", {"user_id": "t1", "scenario": "market_crash", "years": 5, "num_paths": 200})
        self.assertEqual(st, 202)
        for _ in range(50):
            st, job = app.route("GET", f"/result/{out['job_id']}", {})
            if job["status"] in ("DONE", "FAILED"):
                break
            time.sleep(0.1)
        self.assertEqual(job["status"], "DONE")
        self.assertEqual(job["result"]["scenario"], "market_crash")
        self.assertEqual(len(app.route("GET", "/history/t1", {})[1]["jobs"]), 1)
        self.assertEqual(app.route("POST", "/simulate", {"user_id": "nobody"})[0], 404)


if __name__ == "__main__":
    unittest.main()
