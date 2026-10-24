from collections import Counter
import json
from pathlib import Path
import re

work = Path('D:/DevCache/marker/cpp-primer-final')
source = json.loads(Path('D:/DevCache/marker/qa/source-audit.json').read_text(encoding='utf-8'))
source_pages = {row['page_id']: row for row in source['pages']}
pages = {}
broken_images = []
image_refs = []
required = []
image_audit = []
for file in sorted(work.glob('pages-*.md')):
    meta_file = file.with_suffix('.json')
    if not meta_file.exists():
        continue
    meta = json.loads(meta_file.read_text(encoding='utf-8'))
    image_audit.extend(meta['image_audit'])
    for row in meta['image_audit']:
        required.extend(row.get('required_images', []))
    text = file.read_text(encoding='utf-8')
    for page_id, content in re.findall(r'\{(\d+)\}-{48}\s*(.*?)(?=\{\d+\}-{48}|\Z)', text, re.S):
        page_id = int(page_id)
        assert page_id not in pages, page_id
        actual = ''.join(re.findall(r'[\u3400-\u9fff]',content))
        original = source_pages[page_id]['han_text']
        missing = Counter(original) - Counter(actual)
        pages[page_id] = {'page_id':page_id, 'source_han':len(original),
                          'output_han':len(actual), 'missing_han':sum(missing.values()),
                          'missing_ratio':round(sum(missing.values())/max(1,len(original)),4)}
    for ref in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',text):
        image_refs.append(ref)
        if not (work / ref).is_file():
            broken_images.append(ref)
bad = [v for v in pages.values() if v['source_han'] > 50 and v['missing_ratio'] > .1]
report = {
    'expected_pages':len(source_pages), 'converted_pages':len(pages),
    'missing_pages':sorted(set(source_pages)-set(pages)),
    'embedded_source_images':sum(x['embedded_images'] for x in image_audit),
    'supplemented_images':sum(x['added_pictures'] for x in image_audit),
    'source_images_covered_by_existing_picture':sum(x['covered_by_picture'] for x in image_audit),
    'output_image_references':len(image_refs),
    'broken_image_links':broken_images,
    'required_images_missing':sorted(set(required)-{Path(x).name for x in image_refs}),
    'source_han_chars_processed':sum(x['source_han'] for x in pages.values()),
    'output_han_chars':sum(x['output_han'] for x in pages.values()),
    'missing_han_chars':sum(x['missing_han'] for x in pages.values()),
    'pages_requiring_review':sorted(bad,key=lambda x:x['missing_ratio'],reverse=True),
    'page_stats':list(pages.values()),
}
(work/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('page_stats','missing_pages')},ensure_ascii=False))
