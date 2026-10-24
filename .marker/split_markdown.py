"""Split the converted book by PDF chapter/section bookmarks without losing text."""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'C++ Primer（第5版）.md'
PAGE_RE = re.compile(r'<!-- PDF 第 (\d+) 页 -->')
IMAGE_RE = re.compile(r'!\[[^\]\r\n]*\]\(([^)\r\n]+)\)')


def normalize(value):
    value = re.sub(r'<[^>]+>', '', value)
    value = unicodedata.normalize('NFKC', html.unescape(html.unescape(value)))
    return re.sub(r'[\s*_`\\#]', '', value)


def filename(value):
    value = html.unescape(html.unescape(value)).replace('\u3000', ' ')
    value = re.sub(r'\s+', ' ', value).strip()
    return value.translate(str.maketrans({'<':'＜','>':'＞',':':'：','"':'＂',
                                        '/':'／','\\':'＼','|':'｜','?':'？','*':'＊'})).rstrip(' .')


def link(label, path):
    return f'[{label}](<{path}>)'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    raw = SOURCE.read_bytes()
    text = raw.decode('utf-8').replace('\r\n','\n')
    outline_file = ROOT/'.marker/pdf-outline.json'
    if outline_file.exists():
        outline = json.loads(outline_file.read_text(encoding='utf-8'))
    else:
        audit = json.loads(Path('D:/DevCache/marker/qa/source-audit.json').read_text(encoding='utf-8'))
        outline = audit['outline']

    markers = list(PAGE_RE.finditer(text))
    assert [int(m[1]) for m in markers] == list(range(1,1385))
    page_starts = [m.start() for m in markers]
    pages = {int(m[1])-1:(m.start(),markers[i+1].start() if i+1<len(markers) else len(text))
             for i,m in enumerate(markers)}

    def page_of(offset):
        return max(1, bisect_right(page_starts,offset))

    def locate(row):
        start,end = pages[row['page_id']]
        desired = normalize(row['title'])
        numeric = re.match(r'^(?:\d+|A)\.\d+(?![\d.])',desired)
        candidates = []
        for match in re.finditer(r'^.*$', text[start:end], re.M):
            clean = normalize(match[0])
            if numeric:
                prefix = numeric[0]
                ok = clean.startswith(prefix) and (len(clean)==len(prefix) or clean[len(prefix)] not in '0123456789.')
            elif re.match(r'^第\d+章',desired):
                ok = clean.startswith(re.match(r'^第\d+章',desired)[0])
            else:
                ok = clean == desired
            if ok:
                candidates.append(start+match.start())
        if not candidates:
            raise ValueError(f'Heading not found: {row}')
        offset = candidates[0]
        # Put the leading page comment into the new note when the heading is
        # the first content on its page. Mid-page section boundaries stay exact.
        if not text[start+len(markers[row['page_id']][0]):offset].strip():
            offset = start
        return offset

    chapters = [r for r in outline if re.match(r'^第\d+章',normalize(r['title']))]
    chapter_folder = {int(re.match(r'^第(\d+)章',normalize(r['title']))[1]):filename(r['title']) for r in chapters}
    events = []

    def add(offset,title,folder,kind):
        events.append({'offset':offset,'title':filename(title),'folder':folder,'kind':kind})

    front = '前言与封面'
    add(0,'封面与扉页',front,'front')
    front_titles = [('版权信息','版权信息'),('内容简介','内容简介'),
                    ('推荐序1','推荐序1'),('推荐序2','推荐序2'),('前言','前言')]
    for target,title in front_titles:
        matches = [m for m in re.finditer(r'^#{1,3} .+$',text[:pages[18][0]],re.M)
                   if normalize(m[0]).startswith(target)]
        assert len(matches)==1,(target,len(matches))
        offset = matches[0].start()
        p = page_of(offset)-1
        start,_ = pages[p]
        if not text[start+len(markers[p][0]):offset].strip():
            offset = start
        add(offset,title,front,'front')

    owner = None
    for row in outline:
        name = normalize(row['title'])
        chapter = re.match(r'^第(\d+)章',name)
        main_section = re.match(r'^(\d+)\.(\d+)(?![\d.])',name)
        appendix_section = re.match(r'^A\.\d+(?![\d.])',name)
        if chapter:
            owner = chapter_folder[int(chapter[1])]
            add(locate(row),row['title'],owner,'chapter')
        elif re.match(r'^第[IVⅠⅡⅢⅣ]+部分',name):
            upcoming = next(r for r in chapters if r['page_id']>row['page_id'])
            num = int(re.match(r'^第(\d+)章',normalize(upcoming['title']))[1])
            add(pages[row['page_id']][0],row['title'],chapter_folder[num],'part')
        elif name.startswith('附录A'):
            owner = filename(row['title'])
            add(locate(row),row['title'],owner,'appendix')
        elif main_section and not re.match(r'^\d+\.\d+\.',name):
            assert owner==chapter_folder[int(main_section[1])],row
            add(locate(row),row['title'],owner,'section')
        elif appendix_section and not re.match(r'^A\.\d+\.',name):
            add(locate(row),row['title'],owner,'section')
        elif name in ('小结','术语表'):
            add(locate(row),row['title'],owner,'summary')
        elif name in ('索引','封底'):
            owner = '索引与封底'
            add(pages[row['page_id']][0],row['title'],owner,'back')

    events.sort(key=lambda r:r['offset'])
    assert events[0]['offset']==0
    assert len({e['offset'] for e in events})==len(events)
    groups = {}
    for i,event in enumerate(events):
        event['end'] = events[i+1]['offset'] if i+1<len(events) else len(text)
        payload = text[event['offset']:event['end']]
        assert payload
        event['payload'] = payload
        event['first_page'] = page_of(event['offset'])
        event['last_page'] = page_of(max(event['offset'],event['end']-1))
        if event['kind']=='part':
            name = '00 '+event['title']+'.md'
        elif event['kind'] in ('chapter','appendix'):
            name = '01 章节导读.md'
        elif event['kind']=='front':
            seq = len(groups.get(event['folder'],[]))+1
            name = f'{seq:02d} '+event['title']+'.md'
        else:
            name = event['title']+'.md'
        event['path'] = Path(event['folder'])/name
        groups.setdefault(event['folder'],[]).append(event)

    assert ''.join(e['payload'] for e in events)==text
    assert len({e['path'].as_posix().casefold() for e in events})==len(events)
    assert sum(len(IMAGE_RE.findall(e['payload'])) for e in events)==len(IMAGE_RE.findall(text))==2539
    entries = {folder:next((e for e in rows if e['kind'] in ('chapter','appendix')),rows[0])
               for folder,rows in groups.items()}

    generated = {}
    all_links = []
    for i,event in enumerate(events):
        folder = event['folder']
        entry = entries[folder]
        nav = [link('总目录','../目录.md')]
        all_links.append((event['path'],'../目录.md'))
        if entry is not event:
            nav.append(link('本章目录',entry['path'].name))
            all_links.append((event['path'],entry['path'].name))
        if i:
            previous = '../'+events[i-1]['path'].as_posix()
            nav.append(link('上一篇',previous))
            all_links.append((event['path'],previous))
        if i+1<len(events):
            following = '../'+events[i+1]['path'].as_posix()
            nav.append(link('下一篇',following))
            all_links.append((event['path'],following))
        preamble = ' · '.join(nav)+'\n\n'+f'> 原 PDF 第 {event["first_page"]}–{event["last_page"]} 页。\n\n'
        body = IMAGE_RE.sub(lambda m:m[0].replace(']('+m[1]+')','](../'+m[1]+')'),event['payload'])
        suffix = '\n'
        if entry is event:
            suffix += '\n---\n\n## 本章笔记\n\n'
            for child in groups[folder]:
                if child is event:
                    continue
                suffix += '- '+link(child['title'],child['path'].name)+'\n'
                all_links.append((event['path'],child['path'].name))
        result = preamble+body+suffix
        assert '\x00' not in result and '\ufffd' not in result
        assert sum(line.lstrip().startswith('```') for line in body.splitlines())%2==0,event['path']
        # Reverse the only content transformation and reconstruct verbatim.
        restored = IMAGE_RE.sub(lambda m:m[0].replace('](../images/','](images/'),body)
        assert restored==event['payload'],event['path']
        for ref in IMAGE_RE.findall(body):
            assert (ROOT/event['path'].parent/ref).is_file(),(event['path'],ref)
        generated[event['path']] = result
        event['source_sha256'] = hashlib.sha256(event['payload'].encode('utf-8')).hexdigest()
        event['output_sha256'] = hashlib.sha256(result.encode('utf-8')).hexdigest()
        event['images'] = len(IMAGE_RE.findall(body))

    lines = ['# C++ Primer（第5版）目录','',
             '按章建立文件夹，章内按节拆分；小结和术语表分别保存。图片共用根目录的 `images/`。','',
             '原始完整文件：'+link('C++ Primer（第5版）','C++ Primer（第5版）.md')+'。','',
             '| 章节 | 笔记数 | PDF 页码 |','| --- | ---: | --- |']
    all_links.append((Path('目录.md'),'C++ Primer（第5版）.md'))
    for folder,rows in groups.items():
        entry = entries[folder]
        path = entry['path'].as_posix()
        lines.append(f'| {link(folder,path)} | {len(rows)} | {rows[0]["first_page"]}–{rows[-1]["last_page"]} |')
        all_links.append((Path('目录.md'),path))
    generated[Path('目录.md')] = '\n'.join(lines)+'\n'

    for source_path,target in all_links:
        resolved = (ROOT/source_path.parent/target).resolve()
        relative = resolved.relative_to(ROOT.resolve())
        assert relative in generated or resolved.is_file(),(source_path,target)
    summary = {'source':SOURCE.name,'source_sha256':hashlib.sha256(raw).hexdigest(),
               'chapters':len(chapters),'folders':len(groups),'notes':len(events),
               'main_sections':sum(e['kind']=='section' for e in events),
               'source_characters':len(text),'image_references':2539,'pdf_pages':1384,
               'content_reconstruction':'exact after newline normalization',
               'offset_basis':'Unicode text with LF newlines',
               'images_resolve':True,'navigation_resolves':True,
               'largest_note_bytes':max(len(s.encode('utf-8')) for p,s in generated.items() if p.name!='目录.md'),
               'files':[{k:(v.as_posix() if isinstance(v,Path) else v) for k,v in e.items() if k!='payload'} for e in events]}
    print(json.dumps({k:v for k,v in summary.items() if k!='files'},ensure_ascii=False,indent=2))
    if not args.write:
        return
    for path in generated:
        if (ROOT/path).exists():
            existing = (ROOT/path).read_bytes().decode('utf-8').replace('\r\r\n','\n').replace('\r\n','\n')
            if existing!=generated[path]:
                raise FileExistsError(f'Refusing to overwrite an unrelated or modified note: {path}')
    for path,content in generated.items():
        target = ROOT/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content.encode('utf-8'))
        assert target.read_text(encoding='utf-8')==content
    assert SOURCE.read_bytes()==raw,'Original full Markdown was modified concurrently'
    outline_file.write_text(json.dumps(outline,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'.marker/split-manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    report = ROOT/'Marker 转换说明.md'
    original_report = report.read_text(encoding='utf-8')
    addition = ('\n## 章节拆分\n\n- 阅读入口：[[目录]]。\n'
                f'- 按 {len(chapters)} 章及前言、附录、索引建立 {len(groups)} 个文件夹，共 {len(events)} 篇笔记。\n'
                '- 章内按节拆分，小结、术语表分别保存；每篇提供总目录、章节目录和前后篇导航。\n'
                '- 图片沿用 `images/`，子文件中的图片链接已调整为相对路径。\n'
                '- 原始完整 Markdown 保留；统一换行符后，拆分内容按源文件顺序拼接可精确还原，图片引用共 2,539 处。\n'
                '- 拆分脚本与校验记录：`.marker/split_markdown.py`、`.marker/split-manifest.json`。\n')
    report.write_text(original_report.rstrip()+'\n'+addition,encoding='utf-8')
    print('CREATED AND VERIFIED',len(events),'notes; original source unchanged.')


if __name__=='__main__':
    main()
