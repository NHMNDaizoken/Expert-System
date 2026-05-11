import unittest

from src.legacy.cf import combine_cf


class CertaintyFactorTest(unittest.TestCase):
    def test_combine_cf_first_positive_evidence(self):
        self.assertEqual(combine_cf(0, 0.7), 0.7)

    def test_combine_cf_multiple_positive_evidence(self):
        self.assertEqual(round(combine_cf(0.85, 0.7), 3), 0.955)


if __name__ == "__main__":
    unittest.main()
