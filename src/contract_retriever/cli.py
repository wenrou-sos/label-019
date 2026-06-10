import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import click
    from rich.traceback import install as install_rich_traceback
except ImportError as e:
    print(f"Missing dependencies: {e}")
    sys.exit(1)

install_rich_traceback(show_locals=False)

from .extractor import DocumentScanner, extract_contract_clauses
from .indexer import ContractIndex
from .comparator import ClauseComparator
from .formatter import OutputFormatter, FormatterConfig
from .stats import (
    get_global_stats, reset_global_stats, save_global_stats, load_global_stats,
    FileStats, ContentStats, PerformanceStats,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)


def _get_index_dir(ctx) -> str:
    return ctx.obj.get('index_dir', './contract_index')


def _get_formatter(ctx) -> OutputFormatter:
    return ctx.obj['formatter']


def _check_index_exists(index_dir: str) -> bool:
    return os.path.exists(index_dir) and len(os.listdir(index_dir)) > 0


@click.group(
    help="合同条款快速检索与比对工具\n\n"
         "支持PDF和Word格式合同文件的全文检索和条款比对功能。",
    context_settings={'help_option_names': ['-h', '--help']},
)
@click.version_option(version='1.0.0', prog_name='contract-retriever')
@click.option('--index-dir', default='./contract_index',
              help='索引存储目录', show_default=True)
@click.option('--no-color', is_flag=True, help='禁用彩色输出')
@click.option('--json-output', is_flag=True, help='仅输出JSON格式')
@click.option('--verbose', '-v', is_flag=True, help='显示详细日志')
@click.pass_context
def main(ctx, index_dir: str, no_color: bool, json_output: bool, verbose: bool):
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    ctx.ensure_object(dict)
    ctx.obj['index_dir'] = index_dir
    ctx.obj['json_output'] = json_output
    ctx.obj['verbose'] = verbose

    formatter_config = FormatterConfig(
        use_colors=not no_color,
        show_full_content=False,
    )
    ctx.obj['formatter'] = OutputFormatter(formatter_config)

    stats_file = os.path.join(index_dir, 'stats.json')
    if not load_global_stats(stats_file):
        reset_global_stats()


@main.result_callback()
def save_stats(result, **kwargs):
    ctx = click.get_current_context()
    index_dir = _get_index_dir(ctx)
    stats_file = os.path.join(index_dir, 'stats.json')
    save_global_stats(stats_file)


@main.command('scan', help='扫描目录并提取合同内容')
@click.argument('directory', type=click.Path(exists=True, file_okay=False))
@click.option('--show-progress/--no-progress', default=True,
              help='显示进度条', show_default=True)
@click.option('--output-json', type=click.Path(), help='将结果保存为JSON文件')
@click.pass_context
def scan_command(ctx, directory: str, show_progress: bool, output_json: Optional[str]):
    formatter = _get_formatter(ctx)
    stats = get_global_stats()
    op_stats = stats.start_operation('scan')

    try:
        scanner = DocumentScanner(directory)
        documents, scan_stats = scanner.scan(show_progress=show_progress)

        file_stats = FileStats(
            total_files=scan_stats['total_files'],
            pdf_count=scan_stats['pdf_count'],
            docx_count=scan_stats['docx_count'],
            doc_count=scan_stats['doc_count'],
            success_count=scan_stats['success_count'],
            failed_files=scan_stats['failed_files'],
        )
        stats.file_stats = file_stats

        content_stats = ContentStats()
        for doc in documents:
            if doc.error:
                continue
            content_stats.add_file_pages(doc.total_pages)
            for seg in doc.segments:
                content_stats.add_segment(len(seg.text))
            clauses = extract_contract_clauses(doc)
            for clause in clauses:
                content_stats.add_clause(len(clause['content']))
        stats.content_stats = content_stats

        perf_stats = PerformanceStats(
            extraction_time_ms=scan_stats['extraction_time_ms'],
        )
        stats.performance_stats = perf_stats

        op_stats.finish(
            success=True,
            total_files=len(documents),
            success_count=file_stats.success_count,
            failed_count=file_stats.failed_count,
        )

        if ctx.obj.get('json_output'):
            result = {
                'operation': 'scan',
                'success': True,
                'file_stats': file_stats.to_dict(),
                'content_stats': content_stats.to_dict(),
                'performance': perf_stats.to_dict(),
                'documents': [
                    {
                        'file_path': doc.file_path,
                        'file_type': doc.file_type,
                        'total_pages': doc.total_pages,
                        'total_paragraphs': doc.total_paragraphs,
                        'error': doc.error,
                    }
                    for doc in documents
                ],
            }
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            formatter.format_file_stats(file_stats)
            formatter.format_content_stats(content_stats)
            formatter.format_performance_stats(perf_stats)

            if output_json:
                result = {
                    'file_stats': file_stats.to_dict(),
                    'content_stats': content_stats.to_dict(),
                    'performance': perf_stats.to_dict(),
                }
                formatter.format_json(result, output_json)

        if file_stats.failed_files:
            formatter.format_warning(
                f"有 {file_stats.failed_count} 个文件解析失败"
            )

        formatter.format_success(
            f"成功扫描 {file_stats.success_count} 个文件，提取 "
            f"{content_stats.total_clauses} 个条款，"
            f"{content_stats.total_segments} 个段落"
        )

    except Exception as e:
        op_stats.finish(success=False, error_message=str(e))
        formatter.format_error("扫描失败", str(e))
        raise click.ClickException(str(e))


@main.command('build-index', help='构建全文检索索引')
@click.argument('directory', type=click.Path(exists=True, file_okay=False))
@click.option('--show-progress/--no-progress', default=True,
              help='显示进度条', show_default=True)
@click.option('--clear-existing', is_flag=True, help='清除现有索引')
@click.option('--output-json', type=click.Path(), help='将结果保存为JSON文件')
@click.pass_context
def build_index_command(ctx, directory: str, show_progress: bool,
                        clear_existing: bool, output_json: Optional[str]):
    formatter = _get_formatter(ctx)
    index_dir = _get_index_dir(ctx)
    stats = get_global_stats()
    op_stats = stats.start_operation('build-index')

    try:
        if clear_existing:
            index = ContractIndex(index_dir)
            index.clear()
            formatter.format_info("已清除现有索引")

        formatter.format_info(f"开始扫描目录: {directory}")
        scanner = DocumentScanner(directory)
        documents, scan_stats = scanner.scan(show_progress=show_progress)

        file_stats = FileStats(
            total_files=scan_stats['total_files'],
            pdf_count=scan_stats['pdf_count'],
            docx_count=scan_stats['docx_count'],
            doc_count=scan_stats['doc_count'],
            success_count=scan_stats['success_count'],
            failed_files=scan_stats['failed_files'],
        )
        stats.file_stats = file_stats

        formatter.format_info(f"开始构建索引: {index_dir}")
        index = ContractIndex(index_dir)
        index_stats = index.build_index(documents, show_progress=show_progress)

        content_stats = ContentStats(
            total_clauses=index_stats.total_clauses,
            total_segments=index_stats.total_segments,
        )
        stats.content_stats = content_stats

        total_docs = index_stats.total_documents
        perf_stats = PerformanceStats(
            indexing_time_ms=index_stats.build_time_ms,
            extraction_time_ms=scan_stats['extraction_time_ms'],
            docs_per_second=total_docs / (index_stats.build_time_ms / 1000) if index_stats.build_time_ms > 0 else 0,
            segments_per_second=index_stats.total_segments / (index_stats.build_time_ms / 1000) if index_stats.build_time_ms > 0 else 0,
        )
        stats.performance_stats = perf_stats

        if os.path.exists(index_dir):
            import shutil
            total_size = 0
            for dirpath, dirnames, filenames in os.walk(index_dir):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
            perf_stats.index_size_mb = total_size / (1024 * 1024)

        op_stats.finish(
            success=True,
            index_dir=index_dir,
            total_documents=index_stats.total_documents,
            total_segments=index_stats.total_segments,
            total_clauses=index_stats.total_clauses,
            build_time_ms=index_stats.build_time_ms,
        )

        if ctx.obj.get('json_output'):
            result = {
                'operation': 'build-index',
                'success': True,
                'index_dir': index_dir,
                'index_stats': index_stats.__dict__,
                'file_stats': file_stats.to_dict(),
                'content_stats': content_stats.to_dict(),
                'performance': perf_stats.to_dict(),
            }
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            formatter.format_file_stats(file_stats)
            formatter.format_content_stats(content_stats)
            formatter.format_performance_stats(perf_stats)

            if output_json:
                result = {
                    'index_dir': index_dir,
                    'index_stats': index_stats.__dict__,
                    'file_stats': file_stats.to_dict(),
                    'content_stats': content_stats.to_dict(),
                    'performance': perf_stats.to_dict(),
                }
                formatter.format_json(result, output_json)

        if file_stats.failed_files:
            formatter.format_warning(
                f"有 {file_stats.failed_count} 个文件解析失败"
            )

        formatter.format_success(
            f"索引构建完成！共索引 {index_stats.total_documents} 个文档，"
            f"{index_stats.total_clauses} 个条款，"
            f"耗时 {index_stats.build_time_ms}ms"
        )

    except Exception as e:
        op_stats.finish(success=False, error_message=str(e))
        formatter.format_error("索引构建失败", str(e))
        raise click.ClickException(str(e))


@main.command('search', help='关键字检索条款')
@click.argument('keywords', nargs=-1, required=True)
@click.option('--mode', '-m', type=click.Choice(['AND', 'OR']), default='AND',
              help='搜索模式', show_default=True)
@click.option('--limit', '-l', type=int, default=50,
              help='最大结果数', show_default=True)
@click.option('--min-score', type=float, default=0.0,
              help='最小相关度分数', show_default=True)
@click.option('--show-content', is_flag=True, help='显示完整内容')
@click.option('--output-json', type=click.Path(), help='将结果保存为JSON文件')
@click.pass_context
def search_command(ctx, keywords: Tuple[str, ...], mode: str, limit: int,
                   min_score: float, show_content: bool,
                   output_json: Optional[str]):
    formatter = _get_formatter(ctx)
    index_dir = _get_index_dir(ctx)
    stats = get_global_stats()
    op_stats = stats.start_operation('search')

    if not _check_index_exists(index_dir):
        formatter.format_error(
            "索引不存在",
            f"请先运行 'build-index' 命令构建索引，或指定正确的索引目录"
        )
        raise click.ClickException("索引不存在")

    try:
        keyword_list = list(keywords)
        formatter.format_info(
            f"搜索关键词: {' AND '.join(keyword_list) if mode == 'AND' else ' OR '.join(keyword_list)}"
        )

        index = ContractIndex(index_dir)
        results = index.search(
            keywords=keyword_list,
            mode=mode,
            limit=limit,
            min_score=min_score,
        )

        search_time_ms = results[0].get('search_time_ms', 0) if results else 0
        stats.search_stats.record_query(
            keyword_count=len(keyword_list),
            mode=mode,
            result_count=len(results),
            search_time_ms=search_time_ms,
        )

        op_stats.finish(
            success=True,
            keywords=keyword_list,
            mode=mode,
            result_count=len(results),
            search_time_ms=search_time_ms,
        )

        if ctx.obj.get('json_output'):
            result = {
                'operation': 'search',
                'success': True,
                'keywords': keyword_list,
                'mode': mode,
                'result_count': len(results),
                'search_time_ms': search_time_ms,
                'results': results,
            }
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            json_output_str = formatter.format_search_results(results, keyword_list, mode)

            if show_content and results:
                for idx, result in enumerate(results, 1):
                    click.echo(f"\n{'='*60}")
                    click.echo(f"#{idx} - {result['file_name']} (第{result['page']}页)")
                    click.echo(f"相关度: {result['score']:.4f}")
                    if result.get('clause_title'):
                        click.echo(f"标题: {result['clause_title']}")
                    click.echo(f"内容:\n{result['full_content']}")

            if output_json:
                formatter.format_json(json.loads(json_output_str), output_json)

            if results:
                formatter.format_success(
                    f"找到 {len(results)} 条匹配结果，耗时 {search_time_ms}ms"
                )
            else:
                formatter.format_warning("未找到匹配的条款")

    except Exception as e:
        op_stats.finish(success=False, error_message=str(e))
        formatter.format_error("搜索失败", str(e))
        raise click.ClickException(str(e))


@main.command('compare', help='比对标准条款与合同条款')
@click.option('--clause', '-c', help='标准条款文本')
@click.option('--clause-file', type=click.Path(exists=True, dir_okay=False),
              help='从文件读取标准条款')
@click.option('--threshold', '-t', type=float, default=0.3,
              help='相似度阈值 (0-1)', show_default=True)
@click.option('--limit', '-l', type=int, default=20,
              help='最大结果数', show_default=True)
@click.option('--show-content', is_flag=True, help='显示完整内容')
@click.option('--output-json', type=click.Path(), help='将结果保存为JSON文件')
@click.pass_context
def compare_command(ctx, clause: Optional[str], clause_file: Optional[str],
                    threshold: float, limit: int, show_content: bool,
                    output_json: Optional[str]):
    formatter = _get_formatter(ctx)
    index_dir = _get_index_dir(ctx)
    stats = get_global_stats()
    op_stats = stats.start_operation('compare')

    if not _check_index_exists(index_dir):
        formatter.format_error(
            "索引不存在",
            f"请先运行 'build-index' 命令构建索引，或指定正确的索引目录"
        )
        raise click.ClickException("索引不存在")

    if not clause and not clause_file:
        formatter.format_error("请提供标准条款文本 (--clause) 或文件 (--clause-file)")
        raise click.UsageError("请提供标准条款文本或文件")

    if clause_file:
        try:
            with open(clause_file, 'r', encoding='utf-8') as f:
                clause = f.read()
        except Exception as e:
            formatter.format_error("读取条款文件失败", str(e))
            raise click.ClickException(f"读取条款文件失败: {e}")

    if not clause or not clause.strip():
        formatter.format_error("标准条款不能为空")
        raise click.UsageError("标准条款不能为空")

    try:
        threshold = max(0.0, min(1.0, threshold))

        formatter.format_info("加载索引数据...")
        index = ContractIndex(index_dir)
        clauses = index.get_all_clauses()
        all_segments = []

        formatter.format_info(f"待比对条款数: {len(clauses)}")

        comparator = ClauseComparator()
        result = comparator.compare(
            standard_clause=clause,
            clauses=clauses,
            threshold=threshold,
            limit=limit,
            show_progress=not ctx.obj.get('json_output'),
        )

        scores = [sc.similarity_score for sc in result.similar_clauses]
        stats.comparison_stats.record_comparison(
            threshold=threshold,
            match_count=len(result.similar_clauses),
            compare_time_ms=result.total_time_ms,
            scores=scores,
        )

        op_stats.finish(
            success=True,
            standard_clause_length=len(clause),
            total_compared=result.total_compared,
            match_count=len(result.similar_clauses),
            threshold=threshold,
            compare_time_ms=result.total_time_ms,
            avg_similarity=result.avg_similarity,
            max_similarity=result.max_similarity,
        )

        if ctx.obj.get('json_output'):
            result_dict = {
                'operation': 'compare',
                'success': True,
                'standard_clause': result.standard_clause,
                'threshold': threshold,
                'total_compared': result.total_compared,
                'match_count': len(result.similar_clauses),
                'total_time_ms': result.total_time_ms,
                'avg_similarity': result.avg_similarity,
                'max_similarity': result.max_similarity,
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
                    }
                    for sc in result.similar_clauses
                ],
            }
            click.echo(json.dumps(result_dict, ensure_ascii=False, indent=2))
        else:
            json_output_str = formatter.format_compare_results(
                result, show_content=show_content
            )

            if output_json:
                formatter.format_json(json.loads(json_output_str), output_json)

            if result.similar_clauses:
                formatter.format_success(
                    f"找到 {len(result.similar_clauses)} 条相似条款，"
                    f"最高相似度 {result.max_similarity:.2f}，"
                    f"耗时 {result.total_time_ms}ms"
                )
            else:
                formatter.format_warning(
                    f"未找到相似度 >= {threshold * 100:.0f}% 的条款"
                )

    except Exception as e:
        op_stats.finish(success=False, error_message=str(e))
        formatter.format_error("条款比对失败", str(e))
        raise click.ClickException(str(e))


@main.command('stats', help='显示统计信息')
@click.option('--type', '-t',
              type=click.Choice(['all', 'file', 'content', 'search', 'compare', 'perf']),
              default='all', help='统计类型', show_default=True)
@click.option('--output-json', type=click.Path(), help='将结果保存为JSON文件')
@click.pass_context
def stats_command(ctx, type: str, output_json: Optional[str]):
    formatter = _get_formatter(ctx)
    stats = get_global_stats()

    try:
        if ctx.obj.get('json_output'):
            if type == 'all':
                result = stats.to_dict()
            elif type == 'file':
                result = stats.file_stats.to_dict()
            elif type == 'content':
                result = stats.content_stats.to_dict()
            elif type == 'search':
                result = stats.search_stats.to_dict()
            elif type == 'compare':
                result = stats.comparison_stats.to_dict()
            elif type == 'perf':
                result = stats.performance_stats.to_dict()
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if type == 'all':
                json_output_str = formatter.format_global_stats(stats)
            elif type == 'file':
                json_output_str = formatter.format_file_stats(stats.file_stats)
            elif type == 'content':
                json_output_str = formatter.format_content_stats(stats.content_stats)
            elif type == 'search':
                json_output_str = formatter.format_search_stats(stats.search_stats)
            elif type == 'compare':
                json_output_str = formatter.format_comparison_stats(stats.comparison_stats)
            elif type == 'perf':
                json_output_str = formatter.format_performance_stats(stats.performance_stats)

            if output_json:
                formatter.format_json(json.loads(json_output_str), output_json)

    except Exception as e:
        formatter.format_error("显示统计信息失败", str(e))
        raise click.ClickException(str(e))


@main.command('list-docs', help='列出已索引的文档')
@click.option('--output-json', type=click.Path(), help='将结果保存为JSON文件')
@click.pass_context
def list_docs_command(ctx, output_json: Optional[str]):
    formatter = _get_formatter(ctx)
    index_dir = _get_index_dir(ctx)

    if not _check_index_exists(index_dir):
        formatter.format_error(
            "索引不存在",
            f"请先运行 'build-index' 命令构建索引"
        )
        raise click.ClickException("索引不存在")

    try:
        index = ContractIndex(index_dir)
        documents = index.get_all_documents()

        if ctx.obj.get('json_output'):
            result = {
                'operation': 'list-docs',
                'success': True,
                'count': len(documents),
                'documents': documents,
            }
            click.echo(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            from rich.table import Table
            from rich import box

            table = Table(
                title=f"已索引文档 (共 {len(documents)} 个)",
                box=box.ROUNDED,
                expand=True,
            )
            table.add_column("#", style="dim", width=4, justify="center")
            table.add_column("文件名", style="cyan")
            table.add_column("类型", style="magenta")
            table.add_column("路径", style="dim")

            for idx, doc in enumerate(documents, 1):
                table.add_row(
                    str(idx),
                    doc['file_name'],
                    doc['file_type'].upper(),
                    doc['file_path'],
                )

            formatter.console.print(table)

            if output_json:
                result = {
                    'count': len(documents),
                    'documents': documents,
                }
                formatter.format_json(result, output_json)

    except Exception as e:
        formatter.format_error("列出文档失败", str(e))
        raise click.ClickException(str(e))


@main.command('clear-index', help='清除索引')
@click.option('--force', '-f', is_flag=True, help='不提示确认')
@click.pass_context
def clear_index_command(ctx, force: bool):
    formatter = _get_formatter(ctx)
    index_dir = _get_index_dir(ctx)

    if not _check_index_exists(index_dir):
        formatter.format_info("索引目录不存在或为空")
        return

    if not force:
        click.confirm(f"确定要清除索引目录 {index_dir} 吗？", abort=True)

    try:
        index = ContractIndex(index_dir)
        index.clear()
        formatter.format_success(f"索引已清除: {index_dir}")
    except Exception as e:
        formatter.format_error("清除索引失败", str(e))
        raise click.ClickException(str(e))


if __name__ == '__main__':
    main()
