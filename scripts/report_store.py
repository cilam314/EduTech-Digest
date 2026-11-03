"""One reading list, URL-level deduplication, lossless legacy report archival."""
import hashlib
import json
from pathlib import Path
import re
import shutil
from datetime import timedelta
from urllib.parse import urlsplit


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
    folder = root / 'archive' / 'reports'
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


def consolidate(root, now, current_markdown, key_for_url):
    root = Path(root)
    reports = root / 'reports'
    reports.mkdir(exist_ok=True)
    index_path = root / 'archive' / 'entries.json'
    index = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {}
    if not isinstance(index, dict):
        raise ValueError('archive/entries.json must be an object; no reports were moved')
    legacy = sorted(p for p in reports.glob('情报简报_*.md')
                    if re.fullmatch(r'情报简报_[\d_-]+\.md', p.name))
    for source in legacy:
        for key, item in parse_entries(source.read_text(encoding='utf-8-sig'), key_for_url).items():
            item['legacy_import'] = True
            index[key] = item
    old_keys = set(index)
    latest_entries = parse_entries(current_markdown, key_for_url)
    for key, item in latest_entries.items():
        item['legacy_import'] = False
        index[key] = item
    start = (now.date() - timedelta(days=1)).isoformat()
    end = now.date().isoformat()
    ordered = sorted(index.values(), key=lambda r: (r['date'], r['title']), reverse=True)
    recent = [item for item in ordered if start <= item['date'] <= end]
    past = [item for item in ordered if not start <= item['date'] <= end]
    lines = ['# 教育技术情报 · 更新清单', '', f'> 最近执行：北京时间 {now:%Y-%m-%d %H:%M}。',
             f'> 当前日期范围：{start} 至 {end}；历次条目按原文链接去重合并。', '',
             f'本次新增 **{len(set(latest_entries)-old_keys)}** 条；当前范围内累计 **{len(recent)}** 条；历史累计 **{len(index)}** 条。', '',
             '> 本次新增为0时，已收录条目仍保留。搜索失败或未命中不能说明公众号没有更新。', '',
             '## 当前更新清单', '']
    if not recent:
        lines.append('当前范围没有已收录条目；请查看本次检索记录。')
    for item in recent[:25]:
        lines += [item['block']]
        if item.get('legacy_import'):
            lines.append('\n> 从历史报告合并，保留原有结论；来源与内容尚未重新核验。')
        lines.append('')
    if len(recent) > 25:
        lines += [f'另有 {len(recent)-25} 条已保存在 archive/entries.json，当前清单展示最近25条。', '']
    lines += ['<details>', '<summary>往期及日期未确认的条目</summary>', '']
    for item in past[:50]:
        lines.append(f"- {item['date'] or '日期未知'} · {item['source']} · [{item['title']}]({item['url']})")
    if not past:
        lines.append('暂无往期条目。')
    lines += ['', '完整条目及旧报告保存在 archive 文件夹。', '', '</details>', '',
              '<details>', '<summary>本次检索与服务状态</summary>', '']
    marker = '## 本期未检索到可收录更新 / 检索记录'
    diagnostics = current_markdown.split(marker, 1)[-1] if marker in current_markdown else '本次没有检索诊断记录。'
    diagnostics = diagnostics.split('## 本期趋势小结', 1)[0]
    lines.append(diagnostics.strip())
    if '## 搜索后端执行记录' in current_markdown:
        lines += ['', '### 搜索后端执行记录', current_markdown.split('## 搜索后端执行记录', 1)[1].strip()]
    lines += ['', '</details>', '']
    # Both durable data and the reading list are saved before any old report is moved.
    atomic_write(index_path, json.dumps(index, ensure_ascii=False, indent=2)+'\n')
    atomic_write(reports/'latest.md', '\n'.join(lines))
    assert json.loads(index_path.read_text(encoding='utf-8')) == index
    for source in legacy:
        archive_file(source, root)
    old_status = reports/'latest_status.json'
    if old_status.exists():
        archive_file(old_status, root)
    return {'report': 'latest.md', 'merged_entries': len(index), 'current_entries': len(recent),
            'new_entries': len(set(latest_entries)-old_keys), 'archived_reports': len(legacy)}
