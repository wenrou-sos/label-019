import os
import re
import time
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from tqdm import tqdm
import logging

logger = logging.getLogger(__name__)

try:
    import jieba
    from whoosh.fields import Schema, TEXT, ID, NUMERIC, STORED
    from whoosh.index import create_in, open_dir, Index
    from whoosh.analysis import Analyzer, Token
    from whoosh.qparser import QueryParser, MultifieldParser, AndGroup, OrGroup
    from whoosh.scoring import BM25F
    from whoosh.query import Term, And, Or, Phrase, Prefix, FuzzyTerm
except ImportError as e:
    logger.error(f"Missing dependencies: {e}")
    raise


CONTRACT_TERMS = [
    "甲方", "乙方", "丙方", "违约责任", "不可抗力", "保密条款", "知识产权",
    "服务期限", "付款方式", "违约金", "赔偿金", "解除合同", "终止合同",
    "争议解决", "管辖法院", "仲裁", "定金", "订金", "质保金", "履约保证金",
    "合同生效", "合同期限", "续签", "补充协议", "附件", "不可抗力",
    "商业秘密", "竞业限制", "服务期", "试用期", "转正", "离职",
    "股权转让", "资产转让", "债权债务", "担保", "抵押", "质押", "保证",
    "连带责任", "一般保证", "先诉抗辩权", "不安抗辩权", "同时履行抗辩权",
    "要约", "承诺", "邀约邀请", "格式条款", "免责条款", "效力待定",
    "可撤销", "无效合同", "诉讼时效", "除斥期间", "代位权", "撤销权",
    "买卖合同", "借款合同", "租赁合同", "承揽合同", "建设工程合同",
    "运输合同", "技术合同", "保管合同", "仓储合同", "委托合同",
    "行纪合同", "居间合同", "物业服务合同", "合伙合同",
]


def init_jieba_for_contracts():
    for term in CONTRACT_TERMS:
        jieba.add_word(term, freq=1000)
    jieba.suggest_freq(CONTRACT_TERMS, tune=True)


init_jieba_for_contracts()


class ChineseAnalyzer(Analyzer):
    def __init__(self, stop_words: Optional[List[str]] = None):
        self.stop_words = set(stop_words or [
            "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
            "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
            "会", "着", "没有", "看", "好", "自己", "这", "那", "啊", "呢",
            "哦", "嗯", "吧", "嘛", "与", "及", "等", "对", "向", "给",
            "把", "被", "让", "使", "从", "到", "在", "于", "当",
        ])

    def __call__(self, value, positions=False, chars=False,
                 keeporiginal=False, removestops=True,
                 start_pos=0, start_char=0, mode='', **kwargs):
        if isinstance(value, bytes):
            value = value.decode('utf-8')

        tokens = jieba.lcut(value, cut_all=False)
        pos = start_pos
        char_pos = start_char

        for token in tokens:
            token = token.strip()
            if not token:
                continue
            if removestops and token in self.stop_words:
                continue
            if len(token) < 2 and not re.match(r'[a-zA-Z0-9]', token):
                continue

            t = Token(positions, chars, removestops=removestops, mode=mode, **kwargs)
            t.text = token
            t.pos = pos
            t.startchar = char_pos
            t.endchar = char_pos + len(token)
            pos += 1
            char_pos += len(token)
            yield t

    def __eq__(self, other):
        return (other is self or
                isinstance(other, ChineseAnalyzer) and
                self.stop_words == other.stop_words)


@dataclass
class IndexStats:
    index_path: str
    total_documents: int
    total_segments: int
    total_clauses: int
    build_time_ms: int
    avg_segment_length: float
    file_types: Dict[str, int]


class ContractIndex:
    SCHEMA = Schema(
        file_path=ID(stored=True, unique=True),
        file_name=ID(stored=True),
        file_type=ID(stored=True),
        page=NUMERIC(stored=True),
        paragraph=NUMERIC(stored=True),
        clause_title=TEXT(stored=True, analyzer=ChineseAnalyzer()),
        content=TEXT(stored=True, analyzer=ChineseAnalyzer()),
        full_content=STORED,
        metadata=STORED,
    )

    def __init__(self, index_dir: str = "./contract_index"):
        self.index_dir = index_dir
        self.index: Optional[Index] = None
        self._ensure_index_dir()

    def _ensure_index_dir(self):
        if not os.path.exists(self.index_dir):
            os.makedirs(self.index_dir)
            self.index = create_in(self.index_dir, self.SCHEMA)
        else:
            try:
                self.index = open_dir(self.index_dir)
            except Exception:
                shutil.rmtree(self.index_dir)
                os.makedirs(self.index_dir)
                self.index = create_in(self.index_dir, self.SCHEMA)

    def build_index(self, documents: List[Any], show_progress: bool = True) -> IndexStats:
        if not self.index:
            raise RuntimeError("Index not initialized")

        start_time = time.time()
        writer = self.index.writer(limitmb=2048, procs=4)

        total_segments = 0
        total_clauses = 0
        file_types: Dict[str, int] = {}
        segment_lengths: List[int] = []

        from .extractor import extract_contract_clauses, DocumentContent

        iterator = tqdm(documents, desc="构建索引", disable=not show_progress) if show_progress else documents

        for doc in iterator:
            if not isinstance(doc, DocumentContent) or doc.error:
                continue

            file_type = doc.file_type
            file_types[file_type] = file_types.get(file_type, 0) + 1

            clauses = extract_contract_clauses(doc)
            total_clauses += len(clauses)

            for clause in clauses:
                writer.add_document(
                    file_path=doc.file_path,
                    file_name=os.path.basename(doc.file_path),
                    file_type=file_type,
                    page=clause['page'],
                    paragraph=clause['paragraph'],
                    clause_title=clause['title'],
                    content=clause['content'],
                    full_content=f"{clause['title']}\n{clause['content']}",
                    metadata=doc.metadata,
                )
                segment_lengths.append(len(clause['content']))

            for seg in doc.segments:
                writer.add_document(
                    file_path=doc.file_path,
                    file_name=os.path.basename(doc.file_path),
                    file_type=file_type,
                    page=seg.page,
                    paragraph=seg.paragraph,
                    clause_title="",
                    content=seg.text,
                    full_content=seg.text,
                    metadata=doc.metadata,
                )
                total_segments += 1
                segment_lengths.append(len(seg.text))

        writer.commit()

        build_time_ms = int((time.time() - start_time) * 1000)
        avg_segment_length = sum(segment_lengths) / len(segment_lengths) if segment_lengths else 0

        return IndexStats(
            index_path=self.index_dir,
            total_documents=len([d for d in documents if isinstance(d, DocumentContent) and not d.error]),
            total_segments=total_segments,
            total_clauses=total_clauses,
            build_time_ms=build_time_ms,
            avg_segment_length=avg_segment_length,
            file_types=file_types,
        )

    def search(self, keywords: List[str], mode: str = "AND",
               limit: int = 50, min_score: float = 0.0) -> List[Dict[str, Any]]:
        if not self.index:
            raise RuntimeError("Index not initialized")

        results = []
        start_time = time.time()

        with self.index.searcher(weighting=BM25F(B=0.75, K1=1.5)) as searcher:
            group_cls = AndGroup if mode.upper() == "AND" else OrGroup
            parser = MultifieldParser(
                ["clause_title", "content"],
                schema=self.index.schema,
                group=group_cls
            )

            query_str = " ".join(keywords)
            try:
                query = parser.parse(query_str)
            except Exception as e:
                logger.error(f"Query parse error: {e}")
                return results

            hits = searcher.search(query, limit=limit)

            for hit in hits:
                if hit.score < min_score:
                    continue
                results.append({
                    'file_path': hit.get('file_path', ''),
                    'file_name': hit.get('file_name', ''),
                    'file_type': hit.get('file_type', ''),
                    'page': hit.get('page', 0),
                    'paragraph': hit.get('paragraph', 0),
                    'clause_title': hit.get('clause_title', ''),
                    'content': hit.get('content', ''),
                    'full_content': hit.get('full_content', ''),
                    'score': hit.score,
                    'highlights': hit.highlights("content", text=hit.get('content', ''), minscore=0.5),
                    'search_time_ms': int((time.time() - start_time) * 1000),
                })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    def get_all_documents(self) -> List[Dict[str, Any]]:
        if not self.index:
            raise RuntimeError("Index not initialized")

        documents = []
        seen_files = set()

        with self.index.searcher() as searcher:
            for doc in searcher.documents():
                file_path = doc.get('file_path', '')
                if file_path and file_path not in seen_files:
                    seen_files.add(file_path)
                    documents.append({
                        'file_path': file_path,
                        'file_name': doc.get('file_name', ''),
                        'file_type': doc.get('file_type', ''),
                        'metadata': doc.get('metadata', {}),
                    })

        return documents

    def get_all_clauses(self) -> List[Dict[str, Any]]:
        if not self.index:
            raise RuntimeError("Index not initialized")

        clauses = []

        with self.index.searcher() as searcher:
            for doc in searcher.documents():
                if doc.get('clause_title', '').strip():
                    clauses.append({
                        'file_path': doc.get('file_path', ''),
                        'file_name': doc.get('file_name', ''),
                        'page': doc.get('page', 0),
                        'paragraph': doc.get('paragraph', 0),
                        'clause_title': doc.get('clause_title', ''),
                        'content': doc.get('content', ''),
                        'full_content': doc.get('full_content', ''),
                    })

        return clauses

    def clear(self):
        if os.path.exists(self.index_dir):
            shutil.rmtree(self.index_dir)
        self._ensure_index_dir()

    def __len__(self):
        if not self.index:
            return 0
        with self.index.searcher() as searcher:
            return searcher.doc_count()
