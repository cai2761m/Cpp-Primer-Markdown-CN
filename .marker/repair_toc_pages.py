"""Reconvert text-coverage outliers without table reconstruction heuristics."""
from collections import Counter
from pathlib import Path
import json
import re

from convert_cpp_primer import ImagePreservingConverter
from marker.models import create_model_dict, shutdown_models

work=Path('D:/DevCache/marker/cpp-primer-final')
audit=json.loads((work/'validation.json').read_text(encoding='utf-8'))
source=json.loads(Path('D:/DevCache/marker/qa/source-audit.json').read_text(encoding='utf-8'))
pages=[r['page_id'] for r in audit['page_stats'] if r['source_han']!=r['output_han'] or r['missing_han']]
repair_file=work/'toc-repairs.json'
repairs=json.loads(repair_file.read_text(encoding='utf-8')) if repair_file.exists() else {}
models=create_model_dict()
try:
    for page_id in pages:
        config={'mode':'fast','disable_ocr':True,'page_range':[page_id],'paginate_output':True,
                'pdftext_workers':1,'disable_tqdm':True,'highres_image_dpi':240,
                'keep_pageheader_in_output':True,'keep_pagefooter_in_output':True,
                'common_element_threshold':2.0,'max_streak':100000,
                'filter_blank_pages':False,
                'block_relabel_str':'Table:Text:1.01,TableOfContents:Text:1.01,Form:Text:1.01'}
        converter=ImagePreservingConverter(artifact_dict=models,config=config)
        rendered=converter(source['source'])
        text=re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',r'![\1](images/\2)',rendered.markdown)
        content=re.split(r'\{\d+\}-{48}',text,maxsplit=1)[1].strip()
        original=Counter(source['pages'][page_id]['han_text'])
        actual=Counter(re.findall(r'[\u3400-\u9fff]',content))
        if actual!=original:
            print(json.dumps({'page':page_id+1,'repair_skipped':True,
                              'missing_han':sum((original-actual).values()),
                              'extra_han':sum((actual-original).values())}),flush=True)
            continue
        for name,image in rendered.images.items():
            image.save(work/'images'/name,format='PNG')
        for file in sorted(work.glob('pages-*.md')):
            full=file.read_text(encoding='utf-8')
            pattern=rf'(\{{{page_id}\}}-{{48}}\s*)(.*?)(?=\{{\d+\}}-{{48}}|\Z)'
            if not re.search(pattern,full,re.S):
                continue
            full=re.sub(pattern,lambda m:m[1]+content+'\n\n',full,flags=re.S)
            file.write_text(full,encoding='utf-8')
            meta_path=file.with_suffix('.json')
            meta=json.loads(meta_path.read_text(encoding='utf-8'))
            meta.setdefault('text_coverage_repairs',[]).append({'page_id':page_id,'config':config})
            meta['image_audit']=[converter.image_audit[0] if row['page_id']==page_id else row for row in meta['image_audit']]
            meta['output_images']=[Path(ref).name for ref in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',full)]
            meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
            repairs[str(page_id)]={'source_han':sum(original.values()),'output_han':sum(actual.values()),'config':config}
            print(f'REPAIRED PDF page {page_id+1}',flush=True)
            break
finally:
    shutdown_models(models)
(work/'toc-repairs.json').write_text(json.dumps(repairs,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'repaired_pages':len(repairs)}),flush=True)
