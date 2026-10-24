"""Replace code raster embeds consistently in the full book and split notes.

Original Markdown and metadata are backed up before any in-place write. The
image files themselves are retained. Unrelated note text and navigation stay
byte-for-byte equivalent after normalizing the Windows line endings.
"""
from __future__ import annotations
import argparse,copy,hashlib,html,json,re,shutil,time,uuid
from collections import Counter
from pathlib import Path

from glm_ocr_code import ROOT,RESULTS,classify

PATTERN=re.compile(r'!\[([^\]\r\n]*)\]\(((?:\.\./)?images/([^\)\r\n]+))\)')


def sha(data):return hashlib.sha256(data).hexdigest()


def clean_code(code,fenced):
    code=re.sub(r'\A\s*```(?:cpp|c\+\+|c)?[ \t]*\n','',code)
    code=re.sub(r'\n[ \t]*```[ \t]*\s*\Z','',code)
    if not fenced:
        protected=re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')',re.S)
        parts=protected.split(code)
        for i in range(0,len(parts),2):
            parts[i]=re.sub(r'\\([*_])',r'\1',parts[i])
        code=''.join(parts)
    protected=re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/)',re.S)
    parts=protected.split(code)
    table=str.maketrans('（）［］｛｝；，：＝＋－＊／＜＞！＆｜％','()[]{};,:=+-*/<>!&|%')
    for i in range(0,len(parts),2):parts[i]=html.unescape(parts[i]).translate(table)
    return ''.join(parts).strip('\r\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    source_path=ROOT/'C++ Primer（第5版）.md'
    source_raw=source_path.read_bytes();source=source_raw.decode('utf-8').replace('\r\n','\n')
    names={m[3] for m in PATTERN.finditer(source)}
    expected={n for n in names if 18<=int(re.search(r'_page_(\d+)_',n)[1])<1274}
    override_path=Path('D:/DevCache/marker/code-ocr/manual-overrides.json')
    overrides=json.loads(override_path.read_text(encoding='utf-8')) if override_path.exists() else {}
    records={}
    absent=[];errors=[]
    for name in sorted(expected):
        path=RESULTS/(name+'.json')
        if not path.exists():absent.append(name);continue
        r=json.loads(path.read_text(encoding='utf-8'))
        if r.get('error') and overrides.get(name,{}).get('kind')!='image':errors.append(name);continue
        assert sha((ROOT/'images'/name).read_bytes())==r['image_sha256'],name
        if not r.get('error'):r.update(classify(r['raw']))
        records[name]=r
    if absent or errors:
        raise RuntimeError(f'OCR incomplete: {len(absent)} missing, {len(errors)} errors: {errors[:20]}')

    for name,r in overrides.items():
        assert name in records,name
        records[name].update(r)
    mapping={};block_counts={}
    for name,r in records.items():
        if r['kind']!='code':continue
        code=clean_code(r['code'],r.get('classification')=='fenced')
        if not code.strip():raise ValueError(f'Empty code: {name}')
        assert not re.search(r'^\s*```',code,re.M),name
        assert '\x00' not in code and '\ufffd' not in code,name
        mapping[name]=code
        block_counts[name]=records[name].get('markdown_body','```c++\n').count('```c++\n')

    def transform(text):
        def replace(m):
            name=m[3]
            if name not in mapping:return m[0]
            before=records[name].get('prose_before','')
            after=records[name].get('prose_after','')
            body=records[name].get('markdown_body','```c++\n'+mapping[name]+'\n```')
            return (before+'\n\n' if before else '')+'<!-- 代码原图: '+m[2]+' -->\n'+body+('\n\n'+after if after else '')
        return PATTERN.sub(replace,text)

    split_path=ROOT/'.marker/split-manifest.json'
    split=json.loads(split_path.read_text(encoding='utf-8'))
    assert split['source_sha256']==sha(source_raw),'Source changed since original split; regenerate source offsets before applying.'
    target_paths=[source_path]+[ROOT/r['path'] for r in split['files']]
    originals={};generated={};changed=[];occurrences=Counter()
    for path in target_paths:
        data=path.read_bytes();text=data.decode('utf-8').replace('\r\n','\n')
        originals[path]=data
        out=transform(text)
        for m in PATTERN.finditer(text):
            if m[3] in mapping:occurrences[m[3]]+=1
        assert '\x00' not in out and '\ufffd' not in out,path
        # Generated and pre-existing fenced code must remain balanced.
        assert sum(line.lstrip().startswith('```') for line in out.splitlines())%2==0,path
        if out!=text:generated[path]=out;changed.append(path)
    assert set(occurrences)==set(mapping)
    assert all(n==2 for n in occurrences.values()),dict((k,v) for k,v in occurrences.items() if v!=2)
    new_source=transform(source)
    expected_remainder=len(names)-len(mapping)
    assert len(PATTERN.findall(new_source))==expected_remainder
    # Rebuild source ranges to keep the split manifest valid after replacement.
    updated=copy.deepcopy(split)
    updated_rows=[];rebuilt=[];offset=0
    for row in split['files']:
        old_payload=source[row['offset']:row['end']]
        new_payload=transform(old_payload)
        rebuilt.append(new_payload)
        row=copy.deepcopy(row)
        row['offset']=offset;offset+=len(new_payload);row['end']=offset
        row['source_sha256']=sha(new_payload.encode('utf-8'))
        row['images']=len(PATTERN.findall(new_payload))
        note_path=ROOT/row['path']
        current=generated.get(note_path,note_path.read_text(encoding='utf-8'))
        row['output_sha256']=sha(current.encode('utf-8'))
        row['ocr_code_images']=len(re.findall(r'<!-- 代码原图:',new_payload))
        row['ocr_code_blocks']=sum(block_counts.get(m[3],0) for m in PATTERN.finditer(old_payload))
        row['relative_image_path_prefixes']=row['images']+row['ocr_code_images']
        updated_rows.append(row)
    assert ''.join(rebuilt)==new_source
    updated['files']=updated_rows
    updated['source_sha256']=sha(new_source.encode('utf-8'))
    updated['source_characters']=len(new_source)
    updated['image_references']=expected_remainder
    updated['ocr_code_blocks']=sum(block_counts.values())
    updated['ocr_code_images']=len(mapping)
    updated['relative_paths_in_hidden_comments']=True
    updated['largest_note_bytes']=max(len(generated.get(ROOT/r['path'],(ROOT/r['path']).read_text(encoding='utf-8')).encode('utf-8')) for r in updated_rows)
    updated['postprocessing']='Raster code converted to fenced c++ blocks with GLM-OCR; original images retained.'

    report={'engine':'GLM-OCR Q8_0 via local llama.cpp CUDA','date':'2026-10-23',
            'source_before_sha256':sha(source_raw),'source_after_sha256':sha(new_source.encode('utf-8')),
            'images_considered':len(expected),'converted_code_images':len(mapping),
            'code_block_insertions':sum(occurrences[n]*block_counts[n] for n in mapping),'remaining_image_references_in_full_book':expected_remainder,
            'changed_markdown_files':len(changed),'images_retained':True,
            'files':[{'path':p.relative_to(ROOT).as_posix(),'before_sha256':sha(originals[p]),
                      'after_sha256':sha(generated[p].encode('utf-8'))} for p in changed],
            'images':{name:{'code':mapping[name],'image_sha256':records[name]['image_sha256'],
                           'classification':records[name]['classification'],
                           'prose_before':records[name].get('prose_before',''),
                           'prose_after':records[name].get('prose_after',''),
                           'markdown_body':records[name].get('markdown_body')} for name in mapping}}
    print(json.dumps({k:v for k,v in report.items() if k not in ('files','images')},ensure_ascii=False,indent=2))
    if not args.write:return
    backup=ROOT/'.marker'/('code-ocr-backup-20261023-'+uuid.uuid4().hex[:6])
    backup.mkdir(parents=True,exist_ok=False)
    for path,data in originals.items():
        dest=backup/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    for relative in ['.marker/manifest.json','.marker/split-manifest.json','Marker 转换说明.md']:
        path=ROOT/relative
        if path.exists():
            dest=backup/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    for path,out in generated.items():
        assert path.read_bytes()==originals[path],f'Concurrent modification: {path}'
        path.write_bytes(out.encode('utf-8'))
        assert path.read_bytes()==out.encode('utf-8')
    report['backup']=backup.relative_to(ROOT).as_posix()
    (ROOT/'.marker/code-ocr-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    split_path.write_text(json.dumps(updated,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest_path=ROOT/'.marker/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['output_sha256']=updated['source_sha256'];manifest['output_images']=expected_remainder
    manifest['code_ocr']={k:v for k,v in report.items() if k not in ('files','images')}
    manifest['known_limitations']=[v for v in manifest.get('known_limitations',[]) if 'Raster code is preserved' not in v]
    manifest['known_limitations'].append('Image code was OCR-transcribed; original PNG assets and Markdown backups are retained for verification.')
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    notes_path=ROOT/'Marker 转换说明.md';notes=notes_path.read_text(encoding='utf-8')
    notes=re.sub(r'^- 代码示例等原本为图片的部分.*$',f'- 已将 {len(mapping):,} 张代码图片转换为 `c++` 代码块；原图仍保留在 `images/`。',notes,flags=re.M)
    notes+='\n## 图片代码 OCR\n\n'+f'- 本地 GLM-OCR 识别，{len(mapping):,} 张代码图片，完整书稿与分节笔记同步替换，共 {sum(occurrences.values()):,} 处图片引用、{report["code_block_insertions"]:,} 个代码块。\n'
    notes+='- 保留原图、图表、正文、导航与原 PDF 页码；代码原图路径记录在各代码块前的隐藏注释中。\n'
    notes+=f'- 识别前 Markdown 与转换记录备份：`{backup.relative_to(ROOT).as_posix()}/`。\n'
    notes+='- 识别记录：`.marker/code-ocr-manifest.json`；分节内容范围和文件哈希已同步更新。\n'
    notes_path.write_bytes(notes.encode('utf-8'))
    shutil.copy2(Path(__file__),ROOT/'.marker/apply_code_ocr.py')
    shutil.copy2(Path('D:/Programs/marker/glm_ocr_code.py'),ROOT/'.marker/glm_ocr_code.py')
    print('APPLIED; originals backed up at',backup,flush=True)


if __name__=='__main__':main()
