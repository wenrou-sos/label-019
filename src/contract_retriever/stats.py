import time
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class OperationStats:
    operation: str
    start_time: float
    end_time: float = 0.0
    success: bool = True
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        return int((self.end_time - self.start_time) * 1000)

    def finish(self, success: bool = True, error_message: Optional[str] = None, **details):
        self.end_time = time.time()
        self.success = success
        self.error_message = error_message
        self.details.update(details)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'operation': self.operation,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'end_time': datetime.fromtimestamp(self.end_time).isoformat(),
            'duration_ms': self.duration_ms,
            'success': self.success,
            'error_message': self.error_message,
            'details': self.details,
        }


@dataclass
class FileStats:
    total_files: int = 0
    pdf_count: int = 0
    docx_count: int = 0
    doc_count: int = 0
    success_count: int = 0
    failed_files: List[str] = field(default_factory=list)
    skipped_files: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return round(self.success_count / self.total_files * 100, 2)

    @property
    def failed_count(self) -> int:
        return len(self.failed_files)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_files': self.total_files,
            'pdf_count': self.pdf_count,
            'docx_count': self.docx_count,
            'doc_count': self.doc_count,
            'success_count': self.success_count,
            'failed_count': self.failed_count,
            'success_rate': self.success_rate,
            'failed_files': self.failed_files,
            'skipped_files': self.skipped_files,
        }


@dataclass
class ContentStats:
    total_clauses: int = 0
    total_segments: int = 0
    total_characters: int = 0
    clause_lengths: List[int] = field(default_factory=list)
    segment_lengths: List[int] = field(default_factory=list)
    files_by_page_count: Dict[int, int] = field(default_factory=dict)

    @property
    def avg_clause_length(self) -> float:
        if not self.clause_lengths:
            return 0.0
        return round(sum(self.clause_lengths) / len(self.clause_lengths), 2)

    @property
    def avg_segment_length(self) -> float:
        if not self.segment_lengths:
            return 0.0
        return round(sum(self.segment_lengths) / len(self.segment_lengths), 2)

    @property
    def min_clause_length(self) -> int:
        return min(self.clause_lengths) if self.clause_lengths else 0

    @property
    def max_clause_length(self) -> int:
        return max(self.clause_lengths) if self.clause_lengths else 0

    def add_clause(self, length: int):
        self.total_clauses += 1
        self.clause_lengths.append(length)
        self.total_characters += length

    def add_segment(self, length: int):
        self.total_segments += 1
        self.segment_lengths.append(length)
        self.total_characters += length

    def add_file_pages(self, page_count: int):
        self.files_by_page_count[page_count] = self.files_by_page_count.get(page_count, 0) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_clauses': self.total_clauses,
            'total_segments': self.total_segments,
            'total_characters': self.total_characters,
            'avg_clause_length': self.avg_clause_length,
            'avg_segment_length': self.avg_segment_length,
            'min_clause_length': self.min_clause_length,
            'max_clause_length': self.max_clause_length,
            'files_by_page_count': self.files_by_page_count,
        }


@dataclass
class SearchStats:
    total_queries: int = 0
    total_results: int = 0
    total_search_time_ms: int = 0
    queries_by_keyword_count: Dict[int, int] = field(default_factory=dict)
    queries_by_mode: Dict[str, int] = field(default_factory=dict)

    @property
    def avg_search_time_ms(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return round(self.total_search_time_ms / self.total_queries, 2)

    @property
    def avg_results_per_query(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return round(self.total_results / self.total_queries, 2)

    def record_query(self, keyword_count: int, mode: str, result_count: int, search_time_ms: int):
        self.total_queries += 1
        self.total_results += result_count
        self.total_search_time_ms += search_time_ms
        self.queries_by_keyword_count[keyword_count] = self.queries_by_keyword_count.get(keyword_count, 0) + 1
        self.queries_by_mode[mode] = self.queries_by_mode.get(mode, 0) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_queries': self.total_queries,
            'total_results': self.total_results,
            'total_search_time_ms': self.total_search_time_ms,
            'avg_search_time_ms': self.avg_search_time_ms,
            'avg_results_per_query': self.avg_results_per_query,
            'queries_by_keyword_count': self.queries_by_keyword_count,
            'queries_by_mode': self.queries_by_mode,
        }


@dataclass
class ComparisonStats:
    total_comparisons: int = 0
    total_matches: int = 0
    total_compare_time_ms: int = 0
    similarity_scores: List[float] = field(default_factory=list)
    comparisons_by_threshold: Dict[float, int] = field(default_factory=dict)

    @property
    def avg_compare_time_ms(self) -> float:
        if self.total_comparisons == 0:
            return 0.0
        return round(self.total_compare_time_ms / self.total_comparisons, 2)

    @property
    def avg_similarity(self) -> float:
        if not self.similarity_scores:
            return 0.0
        return round(sum(self.similarity_scores) / len(self.similarity_scores), 2)

    @property
    def max_similarity(self) -> float:
        return max(self.similarity_scores) if self.similarity_scores else 0.0

    @property
    def min_similarity(self) -> float:
        return min(self.similarity_scores) if self.similarity_scores else 0.0

    @property
    def match_rate(self) -> float:
        if self.total_comparisons == 0:
            return 0.0
        return round(self.total_matches / self.total_comparisons * 100, 2)

    def record_comparison(self, threshold: float, match_count: int, compare_time_ms: int, scores: List[float]):
        self.total_comparisons += 1
        self.total_matches += match_count
        self.total_compare_time_ms += compare_time_ms
        self.similarity_scores.extend(scores)
        self.comparisons_by_threshold[threshold] = self.comparisons_by_threshold.get(threshold, 0) + 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_comparisons': self.total_comparisons,
            'total_matches': self.total_matches,
            'total_compare_time_ms': self.total_compare_time_ms,
            'avg_compare_time_ms': self.avg_compare_time_ms,
            'avg_similarity': self.avg_similarity,
            'max_similarity': self.max_similarity,
            'min_similarity': self.min_similarity,
            'match_rate': self.match_rate,
            'comparisons_by_threshold': self.comparisons_by_threshold,
        }


@dataclass
class PerformanceStats:
    indexing_time_ms: int = 0
    extraction_time_ms: int = 0
    docs_per_second: float = 0.0
    segments_per_second: float = 0.0
    memory_usage_mb: float = 0.0
    index_size_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'indexing_time_ms': self.indexing_time_ms,
            'extraction_time_ms': self.extraction_time_ms,
            'docs_per_second': round(self.docs_per_second, 2),
            'segments_per_second': round(self.segments_per_second, 2),
            'memory_usage_mb': round(self.memory_usage_mb, 2),
            'index_size_mb': round(self.index_size_mb, 2),
        }


@dataclass
class GlobalStats:
    file_stats: FileStats = field(default_factory=FileStats)
    content_stats: ContentStats = field(default_factory=ContentStats)
    search_stats: SearchStats = field(default_factory=SearchStats)
    comparison_stats: ComparisonStats = field(default_factory=ComparisonStats)
    performance_stats: PerformanceStats = field(default_factory=PerformanceStats)
    operations: List[OperationStats] = field(default_factory=list)
    session_start: float = field(default_factory=time.time)

    @property
    def session_duration_ms(self) -> int:
        return int((time.time() - self.session_start) * 1000)

    def start_operation(self, operation: str) -> OperationStats:
        op = OperationStats(operation=operation, start_time=time.time())
        self.operations.append(op)
        return op

    def to_dict(self) -> Dict[str, Any]:
        return {
            'file_stats': self.file_stats.to_dict(),
            'content_stats': self.content_stats.to_dict(),
            'search_stats': self.search_stats.to_dict(),
            'comparison_stats': self.comparison_stats.to_dict(),
            'performance_stats': self.performance_stats.to_dict(),
            'operations': [op.to_dict() for op in self.operations],
            'session_start': datetime.fromtimestamp(self.session_start).isoformat(),
            'session_duration_ms': self.session_duration_ms,
            'generated_at': datetime.now().isoformat(),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


_global_stats: Optional[GlobalStats] = None


def get_global_stats() -> GlobalStats:
    global _global_stats
    if _global_stats is None:
        _global_stats = GlobalStats()
    return _global_stats


def reset_global_stats():
    global _global_stats
    _global_stats = GlobalStats()


def save_global_stats(file_path: str):
    stats = get_global_stats()
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(stats.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"统计信息已保存到: {file_path}")
    except Exception as e:
        logger.error(f"保存统计信息失败: {e}")


def load_global_stats(file_path: str) -> bool:
    global _global_stats
    if not os.path.exists(file_path):
        return False
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        file_stats = FileStats(
            total_files=data['file_stats'].get('total_files', 0),
            pdf_count=data['file_stats'].get('pdf_count', 0),
            docx_count=data['file_stats'].get('docx_count', 0),
            doc_count=data['file_stats'].get('doc_count', 0),
            success_count=data['file_stats'].get('success_count', 0),
            failed_files=data['file_stats'].get('failed_files', []),
            skipped_files=data['file_stats'].get('skipped_files', []),
        )
        
        content_stats = ContentStats(
            total_clauses=data['content_stats'].get('total_clauses', 0),
            total_segments=data['content_stats'].get('total_segments', 0),
            total_characters=data['content_stats'].get('total_characters', 0),
            clause_lengths=data['content_stats'].get('clause_lengths', []),
            segment_lengths=data['content_stats'].get('segment_lengths', []),
            files_by_page_count=data['content_stats'].get('files_by_page_count', {}),
        )
        
        search_stats = SearchStats(
            total_queries=data['search_stats'].get('total_queries', 0),
            total_results=data['search_stats'].get('total_results', 0),
            total_search_time_ms=data['search_stats'].get('total_search_time_ms', 0),
            queries_by_keyword_count=data['search_stats'].get('queries_by_keyword_count', {}),
            queries_by_mode=data['search_stats'].get('queries_by_mode', {}),
        )
        
        comparison_stats = ComparisonStats(
            total_comparisons=data['comparison_stats'].get('total_comparisons', 0),
            total_matches=data['comparison_stats'].get('total_matches', 0),
            total_compare_time_ms=data['comparison_stats'].get('total_compare_time_ms', 0),
            similarity_scores=data['comparison_stats'].get('similarity_scores', []),
            comparisons_by_threshold=data['comparison_stats'].get('comparisons_by_threshold', {}),
        )
        
        perf_stats = PerformanceStats(
            indexing_time_ms=data['performance_stats'].get('indexing_time_ms', 0),
            extraction_time_ms=data['performance_stats'].get('extraction_time_ms', 0),
            docs_per_second=data['performance_stats'].get('docs_per_second', 0.0),
            segments_per_second=data['performance_stats'].get('segments_per_second', 0.0),
            memory_usage_mb=data['performance_stats'].get('memory_usage_mb', 0.0),
            index_size_mb=data['performance_stats'].get('index_size_mb', 0.0),
        )
        
        _global_stats = GlobalStats(
            file_stats=file_stats,
            content_stats=content_stats,
            search_stats=search_stats,
            comparison_stats=comparison_stats,
            performance_stats=perf_stats,
            session_start=time.time(),
        )
        
        logger.info(f"统计信息已从 {file_path} 加载")
        return True
    except Exception as e:
        logger.error(f"加载统计信息失败: {e}")
        return False
