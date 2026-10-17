"""Socket-free exercise tests; starter fails only test_team_orders_are_independent."""

import tempfile
import unittest
from pathlib import Path

import app


class DrinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="drink-exercise-")
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)

    def test_initial_defaults_do_not_write(self):
        for team in app.DEFAULTS:
            self.assertEqual(app.read_order(self.output, team), app.DEFAULTS[team])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_save_and_read_same_team(self):
        for team in app.DEFAULTS:
            for temperature in ("iced", "hot"):
                for sweetness in (0, 25, 50, 75, 100):
                    with self.subTest(team=team, temperature=temperature, sweetness=sweetness):
                        selection = {"temperature": temperature, "sweetness": sweetness}
                        expected = app.DEFAULTS[team] | selection
                        self.assertEqual(app.save_order(self.output, team, selection), expected)
                        self.assertEqual(app.read_order(self.output, team), expected)

    def test_team_orders_are_independent(self):
        original_coffee = app.read_order(self.output, "coffee")
        tea = {"temperature": "iced", "sweetness": 0}
        app.save_order(self.output, "tea", tea)
        self.assertEqual(app.read_order(self.output, "coffee"), original_coffee,
                         "Saving Team Tea must not turn Team Coffee's cup into matcha")
        self.assertEqual(app.read_order(self.output, "tea"), app.DEFAULTS["tea"] | tea)
        tea_path = app.order_path(self.output, "tea")
        tea_bytes = tea_path.read_bytes()

        coffee = {"temperature": "hot", "sweetness": 25}
        app.save_order(self.output, "coffee", coffee)
        self.assertEqual(app.read_order(self.output, "coffee"), app.DEFAULTS["coffee"] | coffee)
        self.assertEqual(tea_path.read_bytes(), tea_bytes,
                         "Saving Coffee must preserve Tea's saved artifact")
        coffee_path = app.order_path(self.output, "coffee")
        self.assertNotEqual(tea_path, coffee_path)
        coffee_bytes = coffee_path.read_bytes()
        app.save_order(self.output, "tea", {"temperature": "hot", "sweetness": 75})
        self.assertEqual(coffee_path.read_bytes(), coffee_bytes)
        self.assertEqual(app.read_order(self.output, "coffee"), app.DEFAULTS["coffee"] | coffee)

    def test_unknown_team_and_invalid_selection_do_not_write(self):
        selection = {"temperature": "iced", "sweetness": 25}
        for team in ("../outside", "", "/tmp/order", "coffee/extra", "juice"):
            with self.subTest(team=team):
                with self.assertRaises(ValueError):
                    app.save_order(self.output, team, selection)
                with self.assertRaises(ValueError):
                    app.read_order(self.output, team)
        for invalid in (None, [], {}, {"temperature": "warm", "sweetness": 25},
                        {"temperature": "iced", "sweetness": True},
                        {"temperature": "iced", "sweetness": 26},
                        {"temperature": "iced", "sweetness": "25"},
                        selection | {"team_id": "tea"}, selection | {"drink": "matcha"}):
            with self.subTest(selection=invalid), self.assertRaises(ValueError):
                app.save_order(self.output, "coffee", invalid)
        self.assertEqual(list(self.output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
