import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from contract_retriever.extractor import (
    DocumentContent, TextSegment, PDFExtractor, WordExtractor,
    DocumentScanner, extract_contract_clauses
)


class TestTextSegment(unittest.TestCase):
    def test_text_segment_creation(self):
        seg = TextSegment(text="测试内容", page=1, paragraph=0)
        self.assertEqual(seg.text, "测试内容")
        self.assertEqual(seg.page, 1)
        self.assertEqual(seg.paragraph, 0)
        self.assertEqual(seg.start_pos, 0)
        self.assertEqual(seg.end_pos, 0)


class TestDocumentContent(unittest.TestCase):
    def test_empty_document(self):
        doc = DocumentContent(file_path="/test.pdf", file_type="pdf")
        self.assertEqual(doc.full_text, "")
        self.assertEqual(doc.total_pages, 0)
        self.assertEqual(doc.total_paragraphs, 0)

    def test_document_with_segments(self):
        doc = DocumentContent(file_path="/test.pdf", file_type="pdf")
        doc.segments.append(TextSegment(text="第一段", page=1, paragraph=0))
        doc.segments.append(TextSegment(text="第二段", page=2, paragraph=1))

        self.assertEqual(doc.full_text, "第一段\n第二段")
        self.assertEqual(doc.total_pages, 2)
        self.assertEqual(doc.total_paragraphs, 2)


class TestExtractContractClauses(unittest.TestCase):
    def test_extract_clauses(self):
        doc = DocumentContent(file_path="/test.docx", file_type="docx")
        doc.segments = [
            TextSegment(text="第一条 定义", page=1, paragraph=0),
            TextSegment(text="本合同中所称的甲方是指...", page=1, paragraph=1),
            TextSegment(text="第二条 合同期限", page=1, paragraph=2),
            TextSegment(text="本合同有效期为一年...", page=1, paragraph=3),
        ]

        clauses = extract_contract_clauses(doc)
        self.assertEqual(len(clauses), 2)
        self.assertEqual(clauses[0]['title'], "第一条 定义")
        self.assertIn("甲方", clauses[0]['content'])
        self.assertEqual(clauses[1]['title'], "第二条 合同期限")
        self.assertIn("有效期", clauses[1]['content'])

    def test_extract_clauses_with_numbered_patterns(self):
        doc = DocumentContent(file_path="/test.docx", file_type="docx")
        doc.segments = [
            TextSegment(text="1. 服务内容", page=1, paragraph=0),
            TextSegment(text="乙方应按照甲方要求提供服务...", page=1, paragraph=1),
            TextSegment(text="2. 付款方式", page=1, paragraph=2),
            TextSegment(text="甲方应于每月5日前支付款项...", page=1, paragraph=3),
        ]

        clauses = extract_contract_clauses(doc)
        self.assertEqual(len(clauses), 2)
        self.assertEqual(clauses[0]['title'], "1. 服务内容")
        self.assertEqual(clauses[1]['title'], "2. 付款方式")


class TestDocumentScanner(unittest.TestCase):
    def test_supported_extensions(self):
        self.assertIn('.pdf', DocumentScanner.SUPPORTED_EXTENSIONS)
        self.assertIn('.docx', DocumentScanner.SUPPORTED_EXTENSIONS)
        self.assertIn('.doc', DocumentScanner.SUPPORTED_EXTENSIONS)

    def test_find_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test1.pdf").touch()
            Path(tmpdir, "test2.docx").touch()
            Path(tmpdir, "test3.txt").touch()

            subdir = Path(tmpdir, "subdir")
            subdir.mkdir()
            Path(subdir, "test4.pdf").touch()

            scanner = DocumentScanner(tmpdir)
            files = scanner._find_files()

            self.assertEqual(len(files), 3)
            self.assertTrue(any("test1.pdf" in f for f in files))
            self.assertTrue(any("test2.docx" in f for f in files))
            self.assertTrue(any("test4.pdf" in f for f in files))


if __name__ == '__main__':
    unittest.main()
