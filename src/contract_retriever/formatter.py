import json
import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.syntax import Syntax
    from rich import box
    from rich.align import Align
    from colorama import init as colorama_init
except ImportError as e:
    logger.error(f"Missing dependencies: {e}")
    raise


colorama_init(autoreset=True)


@dataclass
class FormatterConfig:
    use_colors: bool = True
    max_content_width: int = 80
    show_full_content: bool = False
    highlight_matches: bool = True


class OutputFormatter:
    def __init__(self, config: Optional[FormatterConfig] = None):
        self.config = config or FormatterConfig()
        self.console = Console(
            force_terminal=self.config.use_colors,
            color_system="auto" if self.config.use_colors else None,
            width=self.config.max_content_width + 20,
        )

    def _truncate_text(self, text: str, max_len: int = 100) -> str:
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        return text[:max_len] + "..."

    def _parse_highlights(self, html_text: str) -> Text:
        text = Text()
        pattern = re.compile(r'<b class="match term\d+">(.*?)</b>', re.DOTALL)
        last_end = 0
        for match in pattern.finditer(html_text):
            if match.start() > last_end:
                text.append(html_text[last_end:match.start()])
            text.append(match.group(1), style="bold yellow on blue")
            last_end = match.end()
        if last_end < len(html_text):
            text.append(html_text[last_end:])
        return text

    def _format_score(self, score: float) -> Text:
        if score >= 80:
            color = "bright_green"
        elif score >= 60:
            color = "yellow"
        elif score >= 40:
            color = "orange1"
        else:
            color = "red"
        return Text(f"{score:.2f}", style=f"bold {color}")

    def format_search_results(self, results: List[Dict[str, Any]],
                              keywords: List[str], mode: str) -> str:
        if not results:
            panel = Panel(
                Text("未找到匹配的条款", style="italic dim"),
                title=f"搜索结果: {' AND '.join(keywords)} [{mode}]",
                border_style="yellow",
            )
            self.console.print(panel)
            return ""

        table = Table(
            title=f"搜索结果: {' AND '.join(keywords) if mode.upper() == 'AND' else ' OR '.join(keywords)}",
            box=box.ROUNDED,
            show_lines=True,
            expand=True,
        )

        table.add_column("#", style="dim", width=4, justify="center")
        table.add_column("文件名", style="cyan", no_wrap=True)
        table.add_column("页码", style="magenta", justify="center", width=6)
        table.add_column("条款标题", style="bold cyan")
        table.add_column("相关度", style="bold", justify="right", width=10)
        table.add_column("内容摘要", style="white")

        for idx, result in enumerate(results, 1):
            content = result.get('content', '')
            highlights = result.get('highlights', '')

            if highlights and self.config.highlight_matches:
                content_text = self._parse_highlights(highlights)
            else:
                content_text = Text(self._truncate_text(content, 150))

            file_name = os.path.basename(result.get('file_path', ''))
            clause_title = result.get('clause_title', '')

            table.add_row(
                str(idx),
                file_name,
                str(result.get('page', '-')),
                self._truncate_text(clause_title, 30),
                self._format_score(result.get('score', 0)),
                content_text,
            )

        self.console.print(table)

        if results:
            search_time = results[0].get('search_time_ms', 0)
            self.console.print(
                Text(f"\n共找到 {len(results)} 条匹配结果，耗时 {search_time}ms",
                     style="dim italic")
            )

        return json.dumps([self._clean_dict(r) for r in results],
                         ensure_ascii=False, indent=2)

    def format_compare_results(self, result: Any,
                               show_content: bool = False) -> str:
        from .comparator import CompareResult, SimilarClause

        if not isinstance(result, CompareResult):
            raise ValueError("Invalid compare result type")

        similar_clauses = result.similar_clauses

        if not similar_clauses:
            panel = Panel(
                Text("未找到相似条款", style="italic dim"),
                title=f"条款比对结果",
                border_style="yellow",
            )
            self.console.print(panel)
            return json.dumps(self._compare_result_to_dict(result), ensure_ascii=False, indent=2)

        self.console.print(Panel(
            Text(result.standard_clause, style="white"),
            title="[bold cyan]标准条款[/bold cyan]",
            border_style="cyan",
            padding=(1, 2),
        ))

        self.console.print()

        stats_table = Table(box=box.SIMPLE, show_header=False, expand=True)
        stats_table.add_column("指标", style="bold")
        stats_table.add_column("数值", style="cyan")
        stats_table.add_row("比对条款总数", str(result.total_compared))
        stats_table.add_row("匹配条款数", str(len(similar_clauses)))
        stats_table.add_row("平均相似度", f"{result.avg_similarity:.2f}")
        stats_table.add_row("最高相似度", f"{result.max_similarity:.2f}")
        stats_table.add_row("总耗时", f"{result.total_time_ms}ms")

        self.console.print(stats_table)
        self.console.print()

        table = Table(
            title="相似条款列表",
            box=box.ROUNDED,
            show_lines=True,
            expand=True,
        )

        table.add_column("#", style="dim", width=4, justify="center")
        table.add_column("相似度", style="bold", justify="center", width=10)
        table.add_column("文件名", style="cyan", no_wrap=True)
        table.add_column("页码", style="magenta", justify="center", width=6)
        table.add_column("段落", style="magenta", justify="center", width=6)
        table.add_column("条款标题", style="bold yellow")
        table.add_column("匹配关键词", style="green")

        for idx, clause in enumerate(similar_clauses, 1):
            matched_keywords = ", ".join(clause.matched_keywords[:5]) if clause.matched_keywords else "-"
            if len(clause.matched_keywords) > 5:
                matched_keywords += f" (+{len(clause.matched_keywords) - 5})"

            table.add_row(
                str(idx),
                self._format_score(clause.similarity_score),
                os.path.basename(clause.file_path),
                str(clause.page),
                str(clause.paragraph),
                self._truncate_text(clause.clause_title, 40),
                matched_keywords,
            )

        self.console.print(table)

        if show_content or self.config.show_full_content:
            self.console.print("\n[bold underline cyan]详细内容:[/bold underline cyan]\n")
            for idx, clause in enumerate(similar_clauses, 1):
                panel = Panel(
                    Text(clause.full_content, style="white"),
                    title=f"[bold]#{idx}[/bold] [cyan]{os.path.basename(clause.file_path)}[/cyan] "
                          f"[magenta]第{clause.page}页[/magenta] "
                          f"[green]{clause.similarity_score:.2f}%[/green]",
                    border_style="blue",
                    padding=(1, 2),
                )
                self.console.print(panel)
                self.console.print()

        return json.dumps(self._compare_result_to_dict(result), ensure_ascii=False, indent=2)

    def format_stats(self, stats: Any) -> str:
        from .stats import GlobalStats, FileStats, ContentStats, SearchStats, ComparisonStats, PerformanceStats

        if isinstance(stats, GlobalStats):
            return self.format_global_stats(stats)
        elif isinstance(stats, FileStats):
            return self.format_file_stats(stats)
        elif isinstance(stats, ContentStats):
            return self.format_content_stats(stats)
        elif isinstance(stats, SearchStats):
            return self.format_search_stats(stats)
        elif isinstance(stats, ComparisonStats):
            return self.format_comparison_stats(stats)
        elif isinstance(stats, PerformanceStats):
            return self.format_performance_stats(stats)
        else:
            return json.dumps(asdict(stats), ensure_ascii=False, indent=2)

    def format_global_stats(self, stats: Any) -> str:
        self.console.print(Panel(
            "[bold]=== 系统统计报告 ===[/bold]",
            border_style="cyan",
            padding=(1, 2),
        ))
        self.console.print()

        self.format_file_stats(stats.file_stats)
        self.console.print()
        self.format_content_stats(stats.content_stats)
        self.console.print()
        self.format_search_stats(stats.search_stats)
        self.console.print()
        self.format_comparison_stats(stats.comparison_stats)
        self.console.print()
        self.format_performance_stats(stats.performance_stats)

        if stats.operations:
            self.console.print("\n[bold underline]操作记录:[/bold underline]")
            for op in stats.operations:
                status = "[green][v][/green]" if op.success else "[red][x][/red]"
                self.console.print(
                    f"  {status} {op.operation} - 耗时: {op.duration_ms}ms"
                )

        return stats.to_json()

    def format_file_stats(self, stats: Any) -> str:
        table = Table(title="=== 文件统计 ===", box=box.ROUNDED, expand=True)
        table.add_column("指标", style="bold")
        table.add_column("数值", style="cyan", justify="right")

        table.add_row("总文件数", str(stats.total_files))
        table.add_row("PDF 文件", f"[blue]{stats.pdf_count}[/blue]")
        table.add_row("Word (docx)", f"[green]{stats.docx_count}[/green]")
        table.add_row("Word (doc)", f"[yellow]{stats.doc_count}[/yellow]")
        table.add_row("成功提取", f"[bold green]{stats.success_count}[/bold green]")
        table.add_row("失败", f"[bold red]{stats.failed_count}[/bold red]")
        table.add_row("成功率", f"[bold]{stats.success_rate:.2f}%[/bold]")

        if stats.failed_files:
            table.add_row("失败文件列表", "\n".join(stats.failed_files))

        self.console.print(table)
        return json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)

    def format_content_stats(self, stats: Any) -> str:
        table = Table(title="=== 内容统计 ===", box=box.ROUNDED, expand=True)
        table.add_column("指标", style="bold")
        table.add_column("数值", style="cyan", justify="right")

        table.add_row("条款总数", str(stats.total_clauses))
        table.add_row("段落总数", str(stats.total_segments))
        table.add_row("总字符数", f"{stats.total_characters:,}")
        table.add_row("平均条款长度", f"{stats.avg_clause_length:.2f}")
        table.add_row("平均段落长度", f"{stats.avg_segment_length:.2f}")
        table.add_row("最短条款长度", str(stats.min_clause_length))
        table.add_row("最长条款长度", str(stats.max_clause_length))

        self.console.print(table)
        return json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)

    def format_search_stats(self, stats: Any) -> str:
        if stats.total_queries == 0:
            self.console.print("[dim]暂无搜索统计数据[/dim]")
            return json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)

        table = Table(title="=== 搜索统计 ===", box=box.ROUNDED, expand=True)
        table.add_column("指标", style="bold")
        table.add_column("数值", style="cyan", justify="right")

        table.add_row("搜索总次数", str(stats.total_queries))
        table.add_row("返回结果总数", str(stats.total_results))
        table.add_row("总搜索时间", f"{stats.total_search_time_ms}ms")
        table.add_row("平均搜索时间", f"{stats.avg_search_time_ms:.2f}ms")
        table.add_row("平均结果数", f"{stats.avg_results_per_query:.2f}")

        if stats.queries_by_mode:
            mode_str = ", ".join([f"{k}: {v}" for k, v in stats.queries_by_mode.items()])
            table.add_row("搜索模式分布", mode_str)

        self.console.print(table)
        return json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)

    def format_comparison_stats(self, stats: Any) -> str:
        if stats.total_comparisons == 0:
            self.console.print("[dim]暂无比对统计数据[/dim]")
            return json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)

        table = Table(title="=== 比对统计 ===", box=box.ROUNDED, expand=True)
        table.add_column("指标", style="bold")
        table.add_column("数值", style="cyan", justify="right")

        table.add_row("比对总次数", str(stats.total_comparisons))
        table.add_row("匹配结果总数", str(stats.total_matches))
        table.add_row("总比对时间", f"{stats.total_compare_time_ms}ms")
        table.add_row("平均比对时间", f"{stats.avg_compare_time_ms:.2f}ms")
        table.add_row("平均相似度", f"{stats.avg_similarity:.2f}")
        table.add_row("最高相似度", f"{stats.max_similarity:.2f}")
        table.add_row("最低相似度", f"{stats.min_similarity:.2f}")
        table.add_row("匹配率", f"{stats.match_rate:.2f}%")

        self.console.print(table)
        return json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)

    def format_performance_stats(self, stats: Any) -> str:
        table = Table(title="=== 性能统计 ===", box=box.ROUNDED, expand=True)
        table.add_column("指标", style="bold")
        table.add_column("数值", style="cyan", justify="right")

        table.add_row("索引构建时间", f"{stats.indexing_time_ms}ms")
        table.add_row("内容提取时间", f"{stats.extraction_time_ms}ms")
        table.add_row("文档处理速度", f"{stats.docs_per_second:.2f} docs/s")
        table.add_row("段落处理速度", f"{stats.segments_per_second:.2f} segs/s")
        if stats.memory_usage_mb > 0:
            table.add_row("内存使用", f"{stats.memory_usage_mb:.2f} MB")
        if stats.index_size_mb > 0:
            table.add_row("索引大小", f"{stats.index_size_mb:.2f} MB")

        self.console.print(table)
        return json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)

    def format_error(self, message: str, details: Optional[str] = None):
        error_text = Text()
        error_text.append("[x] ", style="bold red")
        error_text.append(message, style="red")
        if details:
            error_text.append(f"\n详情: {details}", style="dim red")

        self.console.print(Panel(error_text, border_style="red"))

    def format_warning(self, message: str):
        warning_text = Text()
        warning_text.append("[!] ", style="bold yellow")
        warning_text.append(message, style="yellow")
        self.console.print(Panel(warning_text, border_style="yellow"))

    def format_success(self, message: str):
        success_text = Text()
        success_text.append("[v] ", style="bold green")
        success_text.append(message, style="green")
        self.console.print(Panel(success_text, border_style="green"))

    def format_info(self, message: str):
        info_text = Text()
        info_text.append("[i] ", style="bold blue")
        info_text.append(message, style="blue")
        self.console.print(Panel(info_text, border_style="blue"))

    def format_json(self, data: Any, output_file: Optional[str] = None) -> str:
        json_str = json.dumps(data, ensure_ascii=False, indent=2)

        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(json_str)
            self.format_success(f"JSON数据已保存到: {output_file}")

        return json_str

    def _clean_dict(self, d: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = {}
        for k, v in d.items():
            if k == 'highlights':
                continue
            cleaned[k] = v
        return cleaned

    def _compare_result_to_dict(self, result: Any) -> Dict[str, Any]:
        from .comparator import CompareResult, SimilarClause
        return {
            'standard_clause': result.standard_clause,
            'similar_clauses': [
                {
                    'file_path': sc.file_path,
                    'file_name': sc.file_name,
                    'page': sc.page,
                    'paragraph': sc.paragraph,
                    'clause_title': sc.clause_title,
                    'content': sc.content,
                    'full_content': sc.full_content,
                    'similarity_score': sc.similarity_score,
                    'matched_keywords': sc.matched_keywords,
                    'compare_time_ms': sc.compare_time_ms,
                }
                for sc in result.similar_clauses
            ],
            'total_compared': result.total_compared,
            'total_time_ms': result.total_time_ms,
            'avg_similarity': result.avg_similarity,
            'max_similarity': result.max_similarity,
        }
