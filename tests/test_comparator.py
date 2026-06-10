import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from contract_retriever.comparator import (
    ClauseComparator, ChineseTokenzier, SimilarClause, CompareResult,
)


class TestChineseTokenizer(unittest.TestCase):
    def test_tokenize_basic(self):
        tokenizer = ChineseTokenzier()
        tokens = tokenizer("甲方和乙方签订了买卖合同")

        self.assertIn("甲方", tokens)
        self.assertIn("乙方", tokens)
        self.assertIn("签订", tokens)
        self.assertIn("买卖合同", tokens)
        self.assertNotIn("和", tokens)
        self.assertNotIn("了", tokens)

    def test_tokenize_contract_terms(self):
        tokenizer = ChineseTokenzier()
        tokens = tokenizer("违约责任和不可抗力条款")

        self.assertIn("违约责任", tokens)
        self.assertIn("不可抗力", tokens)


class TestClauseComparator(unittest.TestCase):
    def setUp(self):
        self.comparator = ClauseComparator()

    def test_calculate_similarity_identical(self):
        text1 = "甲方应于每月5日前支付款项"
        text2 = "甲方应于每月5日前支付款项"

        similarity = self.comparator._calculate_similarity(text1, text2)
        self.assertAlmostEqual(similarity, 1.0, places=1)

    def test_calculate_similarity_different(self):
        text1 = "甲方应于每月5日前支付款项"
        text2 = "乙方应提供符合要求的服务"

        similarity = self.comparator._calculate_similarity(text1, text2)
        self.assertLess(similarity, 0.5)

    def test_calculate_jaccard_similarity(self):
        text1 = "甲方 乙方 合同 款项"
        text2 = "甲方 丙方 合同 服务"

        similarity = self.comparator._calculate_jaccard_similarity(text1, text2)
        self.assertGreater(similarity, 0.0)
        self.assertLess(similarity, 1.0)

    def test_calculate_combined_similarity(self):
        text1 = "任何一方违反本合同约定，应承担违约责任，支付违约金"
        text2 = "若一方违反合同条款，需承担违约责任并支付违约金"

        similarity = self.comparator._calculate_combined_similarity(text1, text2)
        self.assertGreater(similarity, 0.35)

    def test_extract_keywords(self):
        text = "甲方和乙方签订买卖合同，约定违约责任和争议解决方式"

        keywords = self.comparator._extract_keywords(text)
        self.assertIn("甲方", keywords)
        self.assertIn("乙方", keywords)
        self.assertIn("买卖合同", keywords)
        self.assertIn("违约责任", keywords)
        self.assertIn("争议解决", keywords)

    def test_find_matched_keywords(self):
        standard = "违约责任是指当事人违反合同约定应承担的法律责任"
        target = "若一方违反合同约定，应承担相应的违约责任"

        matched = self.comparator._find_matched_keywords(standard, target)
        self.assertIn("违约责任", matched)
        self.assertIn("违反", matched)
        self.assertIn("合同", matched)

    def test_compare_clauses(self):
        standard_clause = """
        第八条 违约责任
        任何一方违反本合同约定，应承担违约责任。违约方应向守约方支付违约金，
        违约金金额为合同总金额的10%。若违约金不足以弥补守约方损失的，
        违约方还应赔偿差额部分。
        """

        clauses = [
            {
                'file_path': '/contract1.docx',
                'file_name': 'contract1.docx',
                'page': 3,
                'paragraph': 5,
                'clause_title': '第七条 违约责任',
                'content': '若一方违反本合同约定，应承担违约责任，向对方支付合同金额10%的违约金',
                'full_content': '第七条 违约责任\n若一方违反本合同约定，应承担违约责任，向对方支付合同金额10%的违约金',
            },
            {
                'file_path': '/contract2.docx',
                'file_name': 'contract2.docx',
                'page': 2,
                'paragraph': 3,
                'clause_title': '第五条 付款方式',
                'content': '甲方应于每月5日前将款项支付至乙方指定账户',
                'full_content': '第五条 付款方式\n甲方应于每月5日前将款项支付至乙方指定账户',
            },
            {
                'file_path': '/contract3.docx',
                'file_name': 'contract3.docx',
                'page': 5,
                'paragraph': 8,
                'clause_title': '第十条 违约条款',
                'content': '当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任',
                'full_content': '第十条 违约条款\n当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任',
            },
        ]

        result = self.comparator.compare(
            standard_clause=standard_clause,
            clauses=clauses,
            threshold=0.2,
            limit=10,
            show_progress=False,
        )

        self.assertIsInstance(result, CompareResult)
        self.assertEqual(result.total_compared, 3)
        self.assertGreater(len(result.similar_clauses), 0)
        self.assertGreater(result.max_similarity, 0.0)

        for sc in result.similar_clauses:
            self.assertIsInstance(sc, SimilarClause)
            self.assertGreaterEqual(sc.similarity_score, 0.0)
            self.assertLessEqual(sc.similarity_score, 100.0)

        if result.similar_clauses:
            self.assertEqual(result.similar_clauses[0].clause_title, '第七条 违约责任')

    def test_compare_empty_standard(self):
        result = self.comparator.compare(
            standard_clause="",
            clauses=[{'content': 'test'}],
            show_progress=False,
        )

        self.assertEqual(len(result.similar_clauses), 0)
        self.assertEqual(result.total_time_ms, 0)

    def test_compare_batch(self):
        standard_clauses = [
            "甲方应承担违约责任",
            "乙方应提供相关服务",
        ]

        clauses = [
            {
                'file_path': '/c1.docx',
                'file_name': 'c1.docx',
                'page': 1,
                'paragraph': 0,
                'clause_title': '违约责任',
                'content': '甲方违约应承担责任',
                'full_content': '违约责任\n甲方违约应承担责任',
            },
            {
                'file_path': '/c2.docx',
                'file_name': 'c2.docx',
                'page': 1,
                'paragraph': 1,
                'clause_title': '服务内容',
                'content': '乙方应提供服务',
                'full_content': '服务内容\n乙方应提供服务',
            },
        ]

        results = self.comparator.compare_batch(
            standard_clauses=standard_clauses,
            clauses=clauses,
            threshold=0.1,
            show_progress=False,
        )

        self.assertEqual(len(results), 2)
        self.assertIsInstance(results[0], CompareResult)
        self.assertIsInstance(results[1], CompareResult)


if __name__ == '__main__':
    unittest.main()
