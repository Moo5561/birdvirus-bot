import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor


_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["BOT_DB_PATH"] = os.path.join(_TEMP_DIR.name, "transactions.db")

import bot.db as db


class DatabaseTransactionTests(unittest.TestCase):
    def setUp(self):
        conn = db._conn()
        conn.executescript(
            """
            DELETE FROM economy;
            DELETE FROM config;
            DELETE FROM user_items;
            DELETE FROM gamble_streaks;
            DELETE FROM gamble_daily;
            DELETE FROM stock_holdings;
            DELETE FROM crypto_wallets;
            DELETE FROM user_jobs;
            DELETE FROM user_cars;
            """
        )
        conn.commit()
        db._config_cache.clear()

    @classmethod
    def tearDownClass(cls):
        connection = getattr(db._local, "conn", None)
        if connection is not None:
            connection.close()
            db._local.conn = None
        _TEMP_DIR.cleanup()

    def test_concurrent_debits_never_overdraw(self):
        db.set_balance(1, 100)

        def debit_once(_):
            try:
                return db.debit_balance(1, 10)
            finally:
                connection = getattr(db._local, "conn", None)
                if connection is not None:
                    connection.close()
                    db._local.conn = None

        with ThreadPoolExecutor(max_workers=20) as pool:
            results = list(pool.map(debit_once, range(20)))

        self.assertEqual(sum(success for success, _ in results), 10)
        self.assertEqual(db.get_balance(1), 0)

    def test_concurrent_income_credits_do_not_lose_updates(self):
        db.set_balance(1, 100)

        def credit_once(_):
            try:
                return db.credit_income(1, 10, taxable=False)
            finally:
                connection = getattr(db._local, "conn", None)
                if connection is not None:
                    connection.close()
                    db._local.conn = None

        with ThreadPoolExecutor(max_workers=20) as pool:
            list(pool.map(credit_once, range(20)))

        self.assertEqual(db.get_balance(1), 300)

    def test_item_purchase_and_consumption_are_atomic(self):
        db.set_balance(1, 30)

        self.assertEqual(db.purchase_item(1, "loaded dice", 20), (True, 10))
        self.assertEqual(db.purchase_item(1, "loaded dice", 20), (False, 10))
        self.assertEqual(db.get_items(1), {"loaded dice": 1})
        self.assertTrue(db.remove_item(1, "loaded dice"))
        self.assertFalse(db.remove_item(1, "loaded dice"))
        self.assertEqual(db.get_balance(1), 10)

    def test_account_moves_loans_and_repayments_preserve_balances(self):
        db.set_balance(1, 100)

        self.assertEqual(db.move_account_funds(1, 70, to_bank=True), (True, 30, 70))
        self.assertEqual(db.move_account_funds(1, 20, to_bank=False), (True, 50, 50))
        self.assertEqual(db.take_loan(1, 100, 110), (150, 110))
        self.assertEqual(db.repay_debt(1, 200), (True, 110, 40, 0))
        self.assertEqual(db.get_balances(1), (40, 50, 0))

    def test_stock_trade_rejects_overspending_and_overselling(self):
        db.set_balance(1, 100)

        self.assertEqual(db.apply_stock_trade(1, "BIRD", 2, -80), (20, 2))
        with self.assertRaisesRegex(ValueError, "insufficient balance"):
            db.apply_stock_trade(1, "BIRD", 1, -30)
        with self.assertRaisesRegex(ValueError, "insufficient shares"):
            db.apply_stock_trade(1, "BIRD", -3, 120)

        self.assertEqual(db.get_balance(1), 20)
        self.assertEqual(db.get_stock_holdings(1), {"BIRD": 2})
        self.assertEqual(db.get_house(), 80)

    def test_streak_and_insurance_claims_credit_exactly_once(self):
        db.set_balance(1, 100)
        db.set_config("house_wallet", "1000")

        self.assertEqual(db.claim_daily_streak(1), (1, 25))
        self.assertEqual(db.claim_daily_streak(1), (1, 0))
        self.assertEqual(db.get_balance(1), 125)
        self.assertEqual(db.get_house(), 975)

        db.track_gamble_result(1, -1000)
        self.assertEqual(db.claim_insurance(1), (100, 1000, False, 225))
        self.assertEqual(db.claim_insurance(1), (0, 1000, True, 225))
        self.assertEqual(db.get_balance(1), 225)
        self.assertEqual(db.get_house(), 875)

    def test_car_and_job_purchases_do_not_split_payment_from_state(self):
        db.set_balance(1, 3000)

        self.assertEqual(
            db.purchase_car(1, "beater", "rust bucket", 1, 2500),
            ("ok", 500),
        )
        self.assertEqual(
            db.purchase_car(1, "beater", "rust bucket", 1, 2500),
            ("owned", 500),
        )
        self.assertEqual(db.accept_job(1, "janitor", 500), (True, 0))
        self.assertEqual(db.accept_job(1, "miner", 1), (False, 0))
        self.assertEqual(db.get_user_job(1)["job_name"], "janitor")


if __name__ == "__main__":
    unittest.main()
