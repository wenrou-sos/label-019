import time
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from tqdm import tqdm
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import jieba
except ImportError as e:
    logger.error(f"Missing dependencies: {e}")
    raise


from .indexer import CONTRACT_TERMS, init_jieba_for_contracts

init_jieba_for_contracts()


@dataclass
class SimilarClause:
    file_path: str
    file_name: str
    page: int
    paragraph: int
    clause_title: str
    content: str
    full_content: str
    similarity_score: float
    matched_keywords: List[str]
    compare_time_ms: int


@dataclass
class CompareResult:
    standard_clause: str
    similar_clauses: List[SimilarClause]
    total_compared: int
    total_time_ms: int
    avg_similarity: float
    max_similarity: float


class ChineseTokenzier:
    def __init__(self):
        self.stop_words = {
            "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
            "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
            "会", "着", "没有", "看", "好", "自己", "这", "那", "啊", "呢",
            "哦", "嗯", "吧", "嘛", "与", "及", "等", "对", "向", "给",
            "把", "被", "让", "使", "从", "到", "在", "于", "当", "其",
            "之", "所", "以", "为", "或", "并", "而", "但", "如", "若",
        }

    def __call__(self, text: str) -> List[str]:
        if isinstance(text, bytes):
            text = text.decode('utf-8')
        tokens = jieba.lcut(text, cut_all=False)
        tokens = [t.strip() for t in tokens if t.strip()]
        tokens = [t for t in tokens if t not in self.stop_words]
        tokens = [t for t in tokens if len(t) >= 2 or re.match(r'[a-zA-Z0-9]', t)]
        return tokens


class ClauseComparator:
    def __init__(self, use_word_embedding: bool = False):
        self.tokenizer = ChineseTokenzier()
        self.use_word_embedding = use_word_embedding
        self._vectorizer = None

    def _build_vectorizer(self, corpus: List[str]):
        self._vectorizer = TfidfVectorizer(
            tokenizer=self.tokenizer,
            token_pattern=None,
            ngram_range=(1, 3),
            min_df=1,
            max_df=0.95,
            sublinear_tf=True,
            norm='l2',
        )
        self._vectorizer.fit(corpus)

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        if not text1.strip() or not text2.strip():
            return 0.0

        combined = [text1, text2]
        try:
            vectorizer = TfidfVectorizer(
                tokenizer=self.tokenizer,
                token_pattern=None,
                ngram_range=(1, 2),
                min_df=1,
                sublinear_tf=True,
            )
            tfidf_matrix = vectorizer.fit_transform(combined)
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            return float(similarity)
        except Exception as e:
            logger.error(f"Similarity calculation error: {e}")
            return 0.0

    def _calculate_jaccard_similarity(self, text1: str, text2: str) -> float:
        tokens1 = set(self.tokenizer(text1))
        tokens2 = set(self.tokenizer(text2))
        if not tokens1 or not tokens2:
            return 0.0
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        return intersection / union if union > 0 else 0.0

    def _calculate_combined_similarity(self, text1: str, text2: str) -> float:
        cosine_sim = self._calculate_similarity(text1, text2)
        jaccard_sim = self._calculate_jaccard_similarity(text1, text2)
        keyword_match_score = self._calculate_keyword_match(text1, text2)

        weights = {
            'cosine': 0.4,
            'jaccard': 0.2,
            'keyword': 0.4,
        }

        combined_score = (
            cosine_sim * weights['cosine'] +
            jaccard_sim * weights['jaccard'] +
            keyword_match_score * weights['keyword']
        )

        return min(1.0, max(0.0, combined_score))

    def _calculate_keyword_match(self, text1: str, text2: str) -> float:
        keywords1 = self._extract_keywords(text1)
        keywords2 = self._extract_keywords(text2)

        if not keywords1:
            return 0.0

        matched = sum(1 for kw in keywords1 if kw in text2)
        return matched / len(keywords1) if keywords1 else 0.0

    def _extract_keywords(self, text: str) -> List[str]:
        keywords = []
        for term in CONTRACT_TERMS:
            if term in text:
                keywords.append(term)

        tokens = self.tokenizer(text)
        token_freq = {}
        for token in tokens:
            token_freq[token] = token_freq.get(token, 0) + 1

        sorted_tokens = sorted(token_freq.items(), key=lambda x: x[1], reverse=True)
        for token, freq in sorted_tokens[:10]:
            if token not in keywords and freq >= 1:
                keywords.append(token)

        return keywords

    def _find_matched_keywords(self, standard: str, target: str) -> List[str]:
        keywords = self._extract_keywords(standard)
        matched = [kw for kw in keywords if kw in target]
        return matched

    def _get_context_window(self, target_clause: Dict[str, Any], all_clauses: List[Dict[str, Any]],
                           window_size: int = 2) -> str:
        if not all_clauses:
            return target_clause.get('full_content', target_clause.get('content', ''))

        file_path = target_clause.get('file_path', '')
        paragraph = target_clause.get('paragraph', 0)

        file_clauses = [c for c in all_clauses if c.get('file_path') == file_path]
        file_clauses.sort(key=lambda x: x.get('paragraph', 0))

        context_parts = []
        for c in file_clauses:
            para_diff = abs(c.get('paragraph', 0) - paragraph)
            if para_diff <= window_size:
                context_parts.append(c.get('full_content', c.get('content', '')))

        return '\n'.join(context_parts)

    def compare(self, standard_clause: str, clauses: List[Dict[str, Any]],
                threshold: float = 0.3, limit: int = 20,
                show_progress: bool = True) -> CompareResult:
        start_time = time.time()

        if not standard_clause.strip():
            return CompareResult(
                standard_clause=standard_clause,
                similar_clauses=[],
                total_compared=0,
                total_time_ms=0,
                avg_similarity=0.0,
                max_similarity=0.0,
            )

        results = []
        scores = []

        iterator = tqdm(clauses, desc="比对条款相似度", disable=not show_progress) if show_progress else clauses

        for clause in iterator:
            target_content = clause.get('full_content', clause.get('content', ''))
            if not target_content.strip():
                continue

            similarity = self._calculate_combined_similarity(standard_clause, target_content)
            score_100 = round(similarity * 100, 2)

            if score_100 >= threshold * 100:
                matched_keywords = self._find_matched_keywords(standard_clause, target_content)

                similar_clause = SimilarClause(
                    file_path=clause.get('file_path', ''),
                    file_name=clause.get('file_name', ''),
                    page=clause.get('page', 0),
                    paragraph=clause.get('paragraph', 0),
                    clause_title=clause.get('clause_title', ''),
                    content=clause.get('content', ''),
                    full_content=target_content,
                    similarity_score=score_100,
                    matched_keywords=matched_keywords,
                    compare_time_ms=int((time.time() - start_time) * 1000),
                )
                results.append(similar_clause)
                scores.append(score_100)

        results.sort(key=lambda x: x.similarity_score, reverse=True)
        results = results[:limit]

        total_time_ms = int((time.time() - start_time) * 1000)
        avg_similarity = round(sum(scores) / len(scores), 2) if scores else 0.0
        max_similarity = round(max(scores), 2) if scores else 0.0

        return CompareResult(
            standard_clause=standard_clause,
            similar_clauses=results,
            total_compared=len(clauses),
            total_time_ms=total_time_ms,
            avg_similarity=avg_similarity,
            max_similarity=max_similarity,
        )

    def compare_batch(self, standard_clauses: List[str], clauses: List[Dict[str, Any]],
                      threshold: float = 0.3, limit_per_standard: int = 10,
                      show_progress: bool = True) -> List[CompareResult]:
        all_results = []

        for standard in tqdm(standard_clauses, desc="批量比对条款", disable=not show_progress):
            result = self.compare(
                standard_clause=standard,
                clauses=clauses,
                threshold=threshold,
                limit=limit_per_standard,
                show_progress=False,
            )
            all_results.append(result)

        return all_results

    def compare_with_context(self, standard_clause: str, clauses: List[Dict[str, Any]],
                             all_segments: List[Dict[str, Any]],
                             threshold: float = 0.3, limit: int = 20,
                             context_window: int = 2,
                             show_progress: bool = True) -> CompareResult:
        start_time = time.time()

        if not standard_clause.strip():
            return CompareResult(
                standard_clause=standard_clause,
                similar_clauses=[],
                total_compared=0,
                total_time_ms=0,
                avg_similarity=0.0,
                max_similarity=0.0,
            )

        results = []
        scores = []

        iterator = tqdm(clauses, desc="比对条款相似度", disable=not show_progress) if show_progress else clauses

        for clause in iterator:
            context = self._get_context_window(clause, all_segments, context_window)
            target_content = f"{clause.get('clause_title', '')}\n{context}"

            if not target_content.strip():
                continue

            similarity = self._calculate_combined_similarity(standard_clause, target_content)
            score_100 = round(similarity * 100, 2)

            if score_100 >= threshold * 100:
                matched_keywords = self._find_matched_keywords(standard_clause, target_content)

                similar_clause = SimilarClause(
                    file_path=clause.get('file_path', ''),
                    file_name=clause.get('file_name', ''),
                    page=clause.get('page', 0),
                    paragraph=clause.get('paragraph', 0),
                    clause_title=clause.get('clause_title', ''),
                    content=clause.get('content', ''),
                    full_content=target_content,
                    similarity_score=score_100,
                    matched_keywords=matched_keywords,
                    compare_time_ms=int((time.time() - start_time) * 1000),
                )
                results.append(similar_clause)
                scores.append(score_100)

        results.sort(key=lambda x: x.similarity_score, reverse=True)
        results = results[:limit]

        total_time_ms = int((time.time() - start_time) * 1000)
        avg_similarity = round(sum(scores) / len(scores), 2) if scores else 0.0
        max_similarity = round(max(scores), 2) if scores else 0.0

        return CompareResult(
            standard_clause=standard_clause,
            similar_clauses=results,
            total_compared=len(clauses),
            total_time_ms=total_time_ms,
            avg_similarity=avg_similarity,
            max_similarity=max_similarity,
        )
