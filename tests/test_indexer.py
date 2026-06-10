import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from contract_retriever.indexer import (
    ContractIndex, ChineseAnalyzer, CONTRACT_TERMS,
)
from contract_retriever.extractor import DocumentContent, TextSegment


class TestChineseAnalyzer(unittest.TestCase):
    def test_analyzer_basic(self):
        analyzer = ChineseAnalyzer()
        tokens = list(analyzer("甲方和乙方签订了合同"))
        token_texts = [t.text for t in tokens]

        self.assertIn("甲方", token_texts)
        self.assertIn("乙方", token_texts)
        self.assertIn("签订", token_texts)
        self.assertIn("合同", token_texts)
        self.assertNotIn("和", token_texts)

    def test_analyzer_stop_words(self):
        analyzer = ChineseAnalyzer()
        tokens = list(analyzer("这是一个测试的文档"))
        token_texts = [t.text for t in tokens]

        self.assertNotIn("这", token_texts)
        self.assertNotIn("是", token_texts)
        self.assertNotIn("的", token_texts)

    def test_contract_terms_recognized(self):
        analyzer = ChineseAnalyzer()
        tokens = list(analyzer("违约责任和不可抗力条款"))
        token_texts = [t.text for t in tokens]

        self.assertIn("违约责任", token_texts)
        self.assertIn("不可抗力", token_texts)


class TestContractIndex(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.index_dir = os.path.join(self.tmpdir, "test_index")

    def tearDown(self):
        import shutil
        if os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    def test_create_index(self):
        index = ContractIndex(self.index_dir)
        self.assertTrue(os.path.exists(self.index_dir))
        self.assertIsNotNone(index.index)

    def test_build_index(self):
        index = ContractIndex(self.index_dir)

        doc1 = DocumentContent(file_path="/test1.docx", file_type="docx")
        doc1.segments = [
            TextSegment(text="第一条 违约责任", page=1, paragraph=0),
            TextSegment(text="任何一方违反本合同约定，应承担违约责任", page=1, paragraph=1),
        ]

        doc2 = DocumentContent(file_path="/test2.docx", file_type="docx")
        doc2.segments = [
            TextSegment(text="第二条 付款方式", page=1, paragraph=0),
            TextSegment(text="甲方应于每月5日前支付款项给乙方", page=1, paragraph=1),
        ]

        documents = [doc1, doc2]
        stats = index.build_index(documents, show_progress=False)

        self.assertEqual(stats.total_documents, 2)
        self.assertGreater(stats.total_segments, 0)
        self.assertGreater(stats.build_time_ms, 0)

    def test_search_and_or(self):
        index = ContractIndex(self.index_dir)

        doc1 = DocumentContent(file_path="/test1.docx", file_type="docx")
        doc1.segments = [
            TextSegment(text="第一条 违约责任", page=1, paragraph=0),
            TextSegment(text="任何一方违反本合同约定，应承担违约责任，支付违约金", page=1, paragraph=1),
        ]

        doc2 = DocumentContent(file_path="/test2.docx", file_type="docx")
        doc2.segments = [
            TextSegment(text="第二条 付款方式", page=1, paragraph=0),
            TextSegment(text="甲方应于每月5日前支付款项给乙方", page=1, paragraph=1),
        ]

        index.build_index([doc1, doc2], show_progress=False)

        and_results = index.search(["违约责任", "违约金"], mode="AND", limit=10)
        self.assertGreater(len(and_results), 0)

        or_results = index.search(["违约责任", "付款"], mode="OR", limit=10)
        self.assertGreaterEqual(len(or_results), len(and_results))

    def test_search_with_page_info(self):
        index = ContractIndex(self.index_dir)

        doc = DocumentContent(file_path="/test1.docx", file_type="docx")
        doc.segments = [
            TextSegment(text="第一条 定义", page=1, paragraph=0),
            TextSegment(text="甲方是指合同的甲方", page=1, paragraph=1),
            TextSegment(text="第二条 违约责任", page=2, paragraph=2),
            TextSegment(text="违约方应承担相应责任", page=2, paragraph=3),
        ]

        index.build_index([doc], show_progress=False)

        results = index.search(["违约责任"], mode="AND", limit=10)
        self.assertGreater(len(results), 0)

        page_2_results = [r for r in results if r['page'] == 2]
        self.assertGreater(len(page_2_results), 0)

    def test_clear_index(self):
        index = ContractIndex(self.index_dir)
        doc = DocumentContent(file_path="/test1.docx", file_type="docx")
        doc.segments = [TextSegment(text="测试内容", page=1, paragraph=0)]
        index.build_index([doc], show_progress=False)

        self.assertGreater(len(index), 0)

        index.clear()

        new_index = ContractIndex(self.index_dir)
        self.assertEqual(len(new_index), 0)


if __name__ == '__main__':
    unittest.main()
