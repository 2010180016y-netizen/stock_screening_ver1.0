from __future__ import annotations

import unittest

from vcb_alt.errors import ValidationError
from vcb_alt.validation import (
    require_delete_confirmation,
    validate_percentage,
    validate_positive_number,
    validate_ticker,
    validate_tickers,
)


class ValidationTests(unittest.TestCase):
    def test_validate_ticker_normalizes_valid_symbols(self) -> None:
        self.assertEqual(validate_ticker(" pltr "), "PLTR")
        self.assertEqual(validate_ticker("brk.b"), "BRK.B")

    def test_validate_ticker_rejects_unsafe_values(self) -> None:
        for value in ("", "../AAPL", "AAPL<script>", "TOO-LONG-TICKER"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_ticker(value)

    def test_validate_tickers_deduplicates(self) -> None:
        self.assertEqual(validate_tickers(["pltr", "PLTR", "mstr"]), ["PLTR", "MSTR"])

    def test_numeric_validation(self) -> None:
        self.assertEqual(validate_positive_number("10.5", "price"), 10.5)
        self.assertEqual(validate_percentage(12, "size", maximum=25), 12)
        with self.assertRaises(ValidationError):
            validate_positive_number(0, "price")
        with self.assertRaises(ValidationError):
            validate_percentage(30, "size", maximum=25)

    def test_delete_confirmation(self) -> None:
        require_delete_confirmation("DELETE_LOCAL_DATA")
        with self.assertRaises(ValidationError):
            require_delete_confirmation("yes")


if __name__ == "__main__":
    unittest.main()

