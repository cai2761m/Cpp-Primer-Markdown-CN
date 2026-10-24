"""Assemble, normalize, and validate the completed Marker batches for Obsidian."""
from datetime import date
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

WORK = Path('D:/DevCache/marker/cpp-primer-final')
DEST = Path('D:/Obsidian/✨技术/计算机/C++/C++ Primer')
SOURCE_AUDIT = Path('D:/DevCache/marker/qa/source-audit.json')
BOOK_NAME = 'C++ Primer（第5版）.md'


def normalize_chinese_spacing(text):
    # Remove only extraction spaces between Han characters, outside code fences.
    inside_code = False
    result = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith('```'):
            inside_code = not inside_code
        if not inside_code:
            line = re.sub(r'(?<=[\u3400-\u9fff]) +(?=[\u3400-\u9fff])', '', line)
        result.append(line)
    return ''.join(result)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--update-created-output',action='store_true')
    args=parser.parse_args()
    validation = json.loads((WORK/'validation.json').read_text(encoding='utf-8'))
    source = json.loads(SOURCE_AUDIT.read_text(encoding='utf-8'))
    assert validation['converted_pages'] == validation['expected_pages'] == 1384
    assert not validation['missing_pages']
    assert not validation['broken_image_links']
    assert not validation['required_images_missing']
    assert not validation['pages_requiring_review'], 'Resolve text coverage outliers first'

    raw = '\n\n'.join(f.read_text(encoding='utf-8').strip() for f in sorted(WORK.glob('pages-*.md')))
    markers = [int(x) for x in re.findall(r'\{(\d+)\}-{48}', raw)]
    assert markers == list(range(1384))
    body = re.sub(r'\{(\d+)\}-{48}', lambda m: f'<!-- PDF 第 {int(m[1])+1} 页 -->', raw)
    body = normalize_chinese_spacing(body)
    book = '# C++ Primer（第5版）\n\n' + body.strip() + '\n'
    assert '\x00' not in book and '\ufffd' not in book
    assert sum(line.lstrip().startswith('```') for line in book.splitlines()) % 2 == 0
    refs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', book)
    assert all((WORK/ref).is_file() for ref in refs)

    target = DEST / BOOK_NAME
    if target.exists():
        previous_manifest=DEST/'.marker'/'manifest.json'
        previous=json.loads(previous_manifest.read_text(encoding='utf-8')) if previous_manifest.exists() else {}
        if not args.update_created_output or previous.get('output_sha256')!=hashlib.sha256(target.read_bytes()).hexdigest():
            raise FileExistsError(f'Refusing to overwrite existing or externally modified note: {target}')
    image_dir = DEST / 'images'
    image_dir.mkdir(exist_ok=True)
    for ref in sorted(set(refs)):
        src = WORK/ref
        dst = DEST/ref
        if dst.exists() and dst.read_bytes() != src.read_bytes():
            raise FileExistsError(f'Refusing to overwrite existing image: {dst}')
        if not dst.exists():
            shutil.copy2(src,dst)
    target.write_text(book,encoding='utf-8')
    assert target.read_text(encoding='utf-8') == book
    assert all((DEST/ref).is_file() for ref in refs)

    records = DEST / '.marker'
    records.mkdir(exist_ok=True)
    shutil.copy2(WORK/'validation.json',records/'validation.json')
    for filename in ('convert_cpp_primer.py','validate_cpp_primer.py','publish_cpp_primer.py','restore_image_captions.py','repair_toc_pages.py','prune_blank_page_images.py','requirements.txt'):
        shutil.copy2(Path('D:/Programs/marker')/filename,records/filename)
    all_meta = [json.loads(f.read_text(encoding='utf-8')) for f in sorted(WORK.glob('pages-*.json'))]
    if (WORK/'image-alt-text.json').exists():
        shutil.copy2(WORK/'image-alt-text.json',records/'image-alt-text.json')
    if (WORK/'toc-repairs.json').exists():
        shutil.copy2(WORK/'toc-repairs.json',records/'toc-repairs.json')
    if (WORK/'blank-page-images.json').exists():
        shutil.copy2(WORK/'blank-page-images.json',records/'blank-page-images.json')
    manifest = {
        'source_pdf':source['source'], 'source_sha256':source['source_sha256'],
        'source_pages':1384, 'output':BOOK_NAME,
        'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'marker_version':'2.0.0', 'surya_version':'0.22.1',
        'mode':'fast', 'disable_ocr':True,
        'keep_pageheader_in_output':True,'keep_pagefooter_in_output':True,
        'embedded_image_preservation':True,'image_dpi':240,'image_format':'PNG',
        'batch_size':24,'output_images':len(set(refs)),
        'source_embedded_images':validation['embedded_source_images'],
        'elapsed_conversion_seconds':round(sum(x['seconds'] for x in all_meta),2),
        'date':'2026-10-23',
        'known_limitations':[
            'Raster code is preserved as images; no OCR was performed on raster code.',
            'PDF font and pagination layout is not preserved by Markdown.',
            'Validation compares page coverage, image coverage, and Han character counts; visual review is sampled.'
        ]}
    (records/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    chapters = [r for r in source['outline'] if re.match(r'第\d+章',r['title'])]
    notes = [
        '# Marker 转换说明','',
        f'- 正文：[[{BOOK_NAME[:-3]}]]。',
        '- 转换日期：2026-10-23。',
        '- 工具：[Marker 2.0.0](https://github.com/datalab-to/marker)，Surya 0.22.1。',
        '- 模式：fast；正文使用 PDF 文字层；保留页眉、页脚，避免误删页末正文。',
        '- 原文件共 1,384 页，已按页序合并；每页保留隐藏的 PDF 页码注释。',
        f'- 图片：保留 {validation["embedded_source_images"]:,} 个嵌入图片对象；正文共引用 {len(set(refs)):,} 张本地 PNG。',
        '- 代码示例等原本为图片的部分仍保留为图片，没有进行 OCR，因此这些图片中的文字不可直接复制为文本。',
        '- 对默认流程补充了嵌入图片保留、图注替代文字，并修正两处目录页的正文识别结果。',
        '- 已核对页数、图片引用、补回图片的覆盖情况和逐页汉字覆盖统计，并抽查代码图片。',
        '- 原 PDF 索引区存在空白页；空白页保留页码注释，不显示纯白图片占位。',
        '- Markdown 不保留 PDF 的字体和分页排版；标题级别和表格由 Marker 自动识别，可能需要按学习用途调整。',
        f'- 逐页汉字统计：原文字层 {validation["source_han_chars_processed"]:,} 字，Markdown（含图片替代文字）{validation["output_han_chars"]:,} 字，按字频核对少 {validation["missing_han_chars"]:,} 字。该统计不等同于逐字校对。',
        '- 本地环境：`D:\\Programs\\marker\\.venv-cpu`。转换脚本及记录在本目录的 `.marker/` 中，分批原始结果在 `D:\\DevCache\\marker\\cpp-primer-final`。',
        '', '## 原 PDF 章节位置', '', '| 章节 | PDF 页码（从 1 开始） |','| --- | ---: |',
    ]
    notes.extend(f'| {r["title"].replace(chr(0x3000)," ")} | {r["page_id"]+1} |' for r in chapters)
    (DEST/'Marker 转换说明.md').write_text('\n'.join(notes)+'\n',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
