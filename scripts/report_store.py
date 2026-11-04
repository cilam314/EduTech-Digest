"""One reading list, URL-level deduplication, lossless legacy report archival."""
import hashlib
import json
from pathlib import Path
import re
import shutil
from datetime import timedelta
from urllib.parse import urlsplit

LABELS = {'A': '权威学术期刊', 'B': '机构与团队', 'C': '科研方法', 'D': '政策与行业', 'E': '教学实践'}


def field(block, label):
    match = re.search(r'^- \*\*' + re.escape(label) + r'\*\*：\s*(.*?)(?=\n- \*\*|\Z)', block, re.M | re.S)
    return match[1].strip() if match else ''


def enrich(item):
    item = dict(item)
    block = item['block']
    group = re.search(r'\*\*归类\*\*：\s*([A-E])', block) or re.search(r'\*\*检索线索\*\*：[^\n]*（([A-E])类', block)
    item['group'] = group[1] if group else ''
    item['confirmed'] = field(block, '可信度').startswith('✅') and bool(field(block, '实际来源'))
    for name, label in (('summary', '简述'), ('research', '研究内容'), ('technology', '技术功能'),
                        ('applications', '怎么应用'), ('reflection', '反思与亮点')):
        item[name] = field(block, label) or '原文未说明'
    title = item['title']
    if title.startswith(item['source'] + ' · '):
        item['title'] = title[len(item['source'] + ' · '):]
    return item


def briefing_markdown(index, now, diagnostics_markdown, briefing):
    start = (now.date() - timedelta(days=1)).isoformat()
    end = now.date().isoformat()
    ordered = sorted(index.values(), key=lambda r: (r['date'], r['title']), reverse=True)
    recent = [r for r in ordered if start <= r['date'] <= end]
    verified = [r for r in recent if r['confirmed'] and r['group'] in LABELS][:25]
    supplementary = [r for r in recent if not (r['confirmed'] and r['group'] in LABELS)]
    lines = [f'# 教育技术情报简报 · {now:%Y-%m-%d}', '',
             f'> 更新于北京时间 {now:%Y-%m-%d %H:%M}；覆盖 {start} 至 {end}。',
             '> 已收录内容按原文链接合并去重。以下仅依据已获得的文章，不能代表公众号全部更新。', '',
             f'本期已确认来源 **{len(verified)}** 条；其他来源待核实 **{len(supplementary)}** 条。', '', '## 本期速览', '']
    def points(key):
        for point in briefing.get(key, []):
            refs = point.get('refs', [])
            if not refs or any(type(i) is not int or not 1 <= i <= len(verified) for i in refs):
                continue
            links = '、'.join(f"[{verified[i-1]['source']}]({verified[i-1]['url']})" for i in refs)
            yield '- ' + point['text'] + '（' + links + '）'
    overview = list(points('overview'))
    if overview:
        lines.extend(overview)
    else:
        for r in verified[:5]:
            lines.append(f"- **[{r['title']}]({r['url']})**：{r['summary']}")
        if not verified:
            lines.append('本期尚无已确认来源的条目可用于速览。')
    lines += ['', '## 重大事件 · 值得关注的变化', '']
    lines.extend(list(points('events')) or ['现有已确认资料不足以形成重大事件判断；不据此断言本期没有重大事件。'])
    lines += ['', '## 新研究与热点线索', '']
    lines += ['以下为本期文章涉及的研究问题，可能转述既有论文；公众号发布日期不等同于论文发表日期。', '']
    topics = list(points('research_topics'))
    if topics:
        lines.extend(topics)
    else:
        research_items = [r for r in verified if r['research'] != '原文未说明']
        for r in research_items[:3]:
            lines.append(f"- **研究线索：{r['title']}**。{r['research']} [查看原文]({r['url']})")
        if not research_items:
            lines.append('现有资料不足以归纳新的研究热点。单篇研究不会被自动描述为全领域趋势。')
    for group, label in LABELS.items():
        lines += ['', f'## {group} 类 · {label} · 已确认账号来源', '']
        items = [r for r in verified if r['group'] == group]
        if not items:
            lines.append('本期暂未收录已确认来源的条目。')
        for r in items:
            lines += [f"### {r['title']}", '', f"**{r['source']} · {r['date']}** · [阅读全文]({r['url']})", '',
                      '**发生了什么**：' + r['summary'], '', '**研究或事件要点**：' + r['research'], '',
                      '**为什么值得读**：' + r['reflection'], '', '**可以怎样用**：' + r['applications'], '',
                      '<details>', '<summary>技术与方法补充</summary>', '', r['technology'], '', '</details>', '']
            if r.get('legacy_import'):
                lines += ['> 此条从历史简报合并，保留原摘要；本次排版没有重新阅读全文。', '']
    lines += ['', '## 趋势观察', '']
    lines.extend(list(points('trends')) or ['证据不足以支持跨来源趋势判断，暂不归纳。'])
    lines += ['', '<details>', '<summary>补充来源、往期条目与核验说明</summary>', '']
    for r in supplementary:
        lines += [f"### {r['title']}", '', f"{r['source']} · {r['date']} · [原文]({r['url']})", '',
                  '> 未确认属于目标账号，未放入上方已确认来源分类。', '', r['summary'], '']
    past = [r for r in ordered if not start <= r['date'] <= end]
    for r in past[:50]:
        lines.append(f"- 往期：{r['date'] or '日期未知'} · [{r['title']}]({r['url']})")
    lines += ['', '往期报告保存在 reports/往期清单，条目索引保存在 state/digest_entries.json。', '', '</details>', '',
              '<details>', '<summary>本次检索与服务状态</summary>', '']
    marker = '## 本期未检索到可收录更新 / 检索记录'
    diagnostics = diagnostics_markdown.split(marker, 1)[-1] if marker in diagnostics_markdown else '本次仅调整排版，未发起新的检索。'
    lines.append(diagnostics.split('## 本期趋势小结', 1)[0].strip())
    if '## 搜索后端执行记录' in diagnostics_markdown:
        lines += ['', diagnostics_markdown.split('## 搜索后端执行记录', 1)[1].strip()]
    lines += ['', '</details>', '']
    return '\n'.join(lines), verified


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(text, encoding='utf-8')
    temporary.replace(path)


def parse_entries(markdown, key_for_url):
    entries = {}
    for block in re.split(r'(?=^### )', markdown, flags=re.M)[1:]:
        block = re.split(r'^## ', block, maxsplit=1, flags=re.M)[0].strip()
        link = re.search(r'\[原文\]\((https?://[^\s)]+)\)', block)
        # Diagnostic search candidates are not summarized articles.
        if not link or '**简述**' not in block or '**日期 / 链接**' not in block:
            continue
        url = link[1]
        date = re.search(r'\*\*日期 / 链接\*\*：\s*(\d{4}-\d{2}-\d{2})', block)
        source = re.search(r'\*\*实际来源\*\*：([^\n]+)', block)
        title = block.splitlines()[0].removeprefix('### ').strip()
        source_name = source[1].strip() if source else urlsplit(url).hostname
        if not source:
            # Early reports used the search target as the publisher. Preserve, but do not repeat that attribution.
            title = title.split(' · ', 1)[-1]
            block = '### ' + source_name + ' · ' + title + '\n' + '\n'.join(block.splitlines()[1:])
        entries[key_for_url(url)] = {'url': url, 'date': date[1] if date else '',
                                     'source': source_name, 'title': title, 'block': block}
    return entries


def archive_file(source, root):
    reports = (root / 'reports').resolve()
    if source.is_symlink() or source.resolve().parent != reports:
        raise ValueError('Report archive path is outside reports directory')
    folder = reports / '往期清单'
    folder.mkdir(parents=True, exist_ok=True)
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    target = folder / source.name
    if target.exists() and target.read_bytes() != data:
        target = folder / (source.stem + '_' + digest[:12] + source.suffix)
    if not target.exists():
        shutil.copy2(source, target)
    if target.read_bytes() != data:
        raise OSError('Archive verification failed; source retained')
    source.unlink()  # Only after an identical archive copy is verified.


def consolidate(root, now, current_markdown, key_for_url, synthesize_callback=None):
    root = Path(root)
    reports = root / 'reports'
    reports.mkdir(exist_ok=True)
    index_path = root / 'state' / 'digest_entries.json'
    index = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {}
    if not isinstance(index, dict):
        raise ValueError('state/digest_entries.json must be an object; no reports were moved')
    report_name = f'{now:%Y-%m-%d}_latest.md'
    legacy = sorted(p for p in reports.glob('*.md') if p.name != report_name and
                    (p.name == 'latest.md' or re.fullmatch(r'(?:情报简报_[\d_-]+|\d{4}-\d{2}-\d{2}_latest)\.md', p.name)))
    previously_saved = set(index)
    for source in legacy:
        for key, item in parse_entries(source.read_text(encoding='utf-8-sig'), key_for_url).items():
            item['legacy_import'] = True
            if key not in previously_saved:
                index[key] = item
    old_keys = set(index)
    latest_entries = parse_entries(current_markdown, key_for_url)
    for key, item in latest_entries.items():
        item['legacy_import'] = False
        index[key] = item
    index = {key: enrich(item) for key, item in index.items()}
    _, verified = briefing_markdown(index, now, current_markdown, {})
    evidence = [{**item, 'source_label': item['source'], 'relation': 'confirmed', 'journal_supplement': False}
                for item in verified]
    fingerprint = hashlib.sha256(json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    cache_path = root/'state/briefing.json'
    cache = json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    briefing, briefing_error = {}, ''
    if cache.get('fingerprint') == fingerprint and cache.get('mode') == 'deepseek':
        briefing = cache.get('briefing', {})
    elif evidence and synthesize_callback:
        try:
            briefing = synthesize_callback(evidence)
            atomic_write(cache_path, json.dumps({'fingerprint': fingerprint, 'mode': 'deepseek', 'briefing': briefing},
                                               ensure_ascii=False, indent=2)+'\n')
        except RuntimeError as exc:
            briefing_error = str(exc)
    markdown, verified = briefing_markdown(index, now, current_markdown, briefing)
    # Both durable data and the reading list are saved before any old report is moved.
    atomic_write(index_path, json.dumps(index, ensure_ascii=False, indent=2)+'\n')
    atomic_write(reports/report_name, markdown)
    assert json.loads(index_path.read_text(encoding='utf-8')) == index
    for source in legacy:
        archive_file(source, root)
    old_status = reports/'latest_status.json'
    if old_status.exists():
        archive_file(old_status, root)
    return {'report': report_name, 'merged_entries': len(index), 'current_entries': len(verified),
            'new_entries': len(set(latest_entries)-old_keys), 'archived_reports': len(legacy),
            'briefing_error': briefing_error}
