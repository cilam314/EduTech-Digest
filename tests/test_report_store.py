from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import report_store as store
from run_digest import article_key, CN


def entry(url, summary='原文指出研究结果', title='测试文章'):
    return f'''### 已核实账号 · {title}
- **实际来源**：已核实账号
- **日期 / 链接**：2026-11-03 / [原文]({url})
- **可信度**：✅ 确认来源
- **简述**：{summary}

'''


class ReportStoreTests(unittest.TestCase):
    def test_merge_deduplicate_archive_and_empty_run_preserves_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'reports').mkdir()
            first = entry('https://mp.weixin.qq.com/s/one?scene=1')
            second = entry('https://mp.weixin.qq.com/s/one?scene=2', '更新后的简述')
            (root/'reports/情报简报_2026_1.md').write_text(first, encoding='utf-8')
            (root/'reports/情报简报_2026_2.md').write_text(second, encoding='utf-8')
            (root/'reports/latest_status.json').write_text('{"failed":false}', encoding='utf-8')
            now = datetime(2026, 11, 3, 23, tzinfo=CN)
            result = store.consolidate(root, now, entry('https://mp.weixin.qq.com/s/two', title='另一篇'), article_key)
            self.assertEqual(result['merged_entries'], 2)
            self.assertEqual(result['archived_reports'], 2)
            self.assertEqual([p.name for p in (root/'reports').iterdir()], ['latest.md'])
            self.assertEqual((root/'archive/reports/情报简报_2026_1.md').read_text(encoding='utf-8'), first)
            self.assertEqual((root/'archive/reports/情报简报_2026_2.md').read_text(encoding='utf-8'), second)
            latest = (root/'reports/latest.md').read_text(encoding='utf-8')
            self.assertEqual(latest.count('### 已核实账号'), 2)
            self.assertIn('更新后的简述', latest)
            result = store.consolidate(root, now, '## 本期未检索到可收录更新 / 检索记录\n没有新增', article_key)
            self.assertEqual(result['merged_entries'], 2)
            self.assertEqual(result['new_entries'], 0)
            self.assertIn('另一篇', (root/'reports/latest.md').read_text(encoding='utf-8'))

    def test_write_failure_never_moves_old_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'reports').mkdir()
            source = root/'reports/情报简报_2026_1.md'
            source.write_text(entry('https://example.org/a'), encoding='utf-8')
            with patch.object(store, 'atomic_write', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    store.consolidate(root, datetime(2026, 11, 3, tzinfo=CN), '', article_key)
            self.assertTrue(source.exists())

    def test_search_candidates_are_not_imported(self):
        text = '### 检索账号\n- [搜索候选](https://example.org/a)：正文读取成功\n'
        self.assertEqual(store.parse_entries(text, article_key), {})


if __name__ == '__main__':
    unittest.main()
