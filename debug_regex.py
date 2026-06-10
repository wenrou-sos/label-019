import re
import sys
sys.path.insert(0, 'src')

from contract_retriever.extractor import extract_contract_clauses, DocumentContent, TextSegment

# 测试正则表达式
test_texts = [
    "1. 服务内容",
    "第一条 定义",
    "第二条 合同期限",
    "1、服务内容",
    "一、服务内容",
]

patterns = [
    r'^第[一二三四五六七八九十百千\d]+[章节条款条]',
    r'^[一二三四五六七八九十百千]+[、\.]\s*',
    r'^\d+[、\.]\s*',
    r'^(甲方|乙方|丙方|双方|各方)',
    r'^(定义|释义|总则|目的|范围)',
]

print("测试正则表达式匹配:")
for text in test_texts:
    print(f"\n文本: '{text}'")
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            print(f"  匹配: {pattern} -> {match.group()}")
        else:
            print(f"  不匹配: {pattern}")

# 测试完整的函数
print("\n\n测试 extract_contract_clauses 函数:")
doc = DocumentContent(file_path="/test.docx", file_type="docx")
doc.segments = [
    TextSegment(text="1. 服务内容", page=1, paragraph=0),
    TextSegment(text="乙方应按照甲方要求提供服务...", page=1, paragraph=1),
    TextSegment(text="2. 付款方式", page=1, paragraph=2),
    TextSegment(text="甲方应于每月5日前支付款项...", page=1, paragraph=3),
]

# 手动调试函数逻辑
clause_patterns = [
    r'^第[一二三四五六七八九十百千\d]+[章节条款条]',
    r'^[一二三四五六七八九十百千]+[、\.]\s*',
    r'^\d+[、\.]\s*',
    r'^(甲方|乙方|丙方|双方|各方)',
    r'^(定义|释义|总则|目的|范围)',
]

current_clause_title = None
current_clause_content = []
current_page = 1
current_paragraph = 0
clauses = []

for seg in doc.segments:
    text = seg.text.strip()
    print(f"\n处理段落 {seg.paragraph}: '{text}'")
    
    if not text:
        continue

    is_clause_start = False
    for pattern in clause_patterns:
        if re.search(pattern, text):
            print(f"  匹配模式: {pattern}")
            is_clause_start = True
            break
    
    print(f"  is_clause_start: {is_clause_start}, len(text): {len(text)}")
    
    if is_clause_start and len(text) < 100:
        print(f"  是条款标题")
        if current_clause_title and current_clause_content:
            print(f"  保存前一个条款: {current_clause_title}")
            clauses.append({
                'title': current_clause_title,
                'content': '\n'.join(current_clause_content),
                'page': current_page,
                'paragraph': current_paragraph,
                'file_path': doc.file_path,
            })
        current_clause_title = text
        current_clause_content = []
        current_page = seg.page
        current_paragraph = seg.paragraph
        print(f"  设置新条款标题: {current_clause_title}")
    else:
        print(f"  不是条款标题，添加到内容")
        if current_clause_title:
            current_clause_content.append(text)
            print(f"  current_clause_content: {current_clause_content}")
        current_page = seg.page

if current_clause_title and current_clause_content:
    print(f"\n循环结束，保存最后一个条款: {current_clause_title}")
    clauses.append({
        'title': current_clause_title,
        'content': '\n'.join(current_clause_content),
        'page': current_page,
        'paragraph': current_paragraph,
        'file_path': doc.file_path,
    })

print(f"\n\n最终找到 {len(clauses)} 个条款")
for i, clause in enumerate(clauses):
    print(f"\n条款 {i+1}:")
    print(f"  标题: {clause['title']}")
    print(f"  内容: {clause['content']}")
    print(f"  页码: {clause['page']}")
