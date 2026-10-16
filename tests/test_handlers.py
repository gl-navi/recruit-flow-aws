import importlib.util
import json
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))  # makes `shared` importable, as it is inside the deployed zip

FUNCTIONS = ["receiver", "worker", "marketo_sync", "error_notifier"]


def load_handler(function):
    spec = importlib.util.spec_from_file_location(
        f"{function}_lambda", SRC / function / "lambda_function.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.lambda_handler


class HandlerSmokeTest(unittest.TestCase):
    def test_each_handler_answers_200_with_its_name(self):
        for function in FUNCTIONS:
            with self.subTest(function=function):
                response = load_handler(function)({}, None)
                self.assertEqual(response["statusCode"], 200)
                self.assertEqual(json.loads(response["body"])["function"], function)


if __name__ == "__main__":
    unittest.main()
