from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_digest as d
from collection_window import load_window, save_cursor
import report_store


class CollectionWindowTests(unittest.TestCase):
    def test_initial_backfill_and_wednesday_to_friday_gap(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            friday = datetime(2026, 11, 6, 12, tzinfo=d.CN)
            self.assertEqual(str(load_window(root, friday)[0]), '2026-11-04')
            wednesday = datetime(2026, 11, 4, 9, 49, tzinfo=d.CN)
            save_cursor(root, wednesday, wednesday.date() - timedelta(days=1))
            start, _ = load_window(root, friday)
            self.assertEqual(str(start), '2026-11-03')
            name = '教育技术学'
            source = {'id': 1, 'url': 'https://mp.weixin.qq.com/s/gap', 'title': '新研究',
                      'body': '研究正文', 'publisher': name, 'biz': d.PROFILES[name]['biz'],
                      'read_status': '微信正文读取成功', 'publication_date': '2026-11-04T20:00:00+08:00'}
            usable, _ = d.prefilter_sources([source], name, 'B', friday, start)
            self.assertEqual(len(usable), 1)
            record, _ = d.validate_entry({'source_id': 1}, [source], name, 'B', friday, {}, start)
            self.assertEqual(record['date'], '2026-11-04')

    def test_same_day_rerun_and_failure_gap_do_not_shrink_start(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            now = datetime(2026, 11, 6, 10, tzinfo=d.CN)
            start = now.date() - timedelta(days=2)
            save_cursor(root, now, start)
            self.assertEqual(load_window(root, now + timedelta(hours=3))[0], start)
            # No successful run for five days: retain all days, without a silent lookback cap.
            self.assertEqual(str(load_window(root, now + timedelta(days=5))[0]), '2026-11-05')

    def test_cursor_timezone_and_invalid_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'state').mkdir()
            path = root/'state/collection_cursor.json'
            path.write_text(json.dumps({'last_success_at': '2026-11-03T18:00:00+00:00'}))
            now = datetime(2026, 11, 6, tzinfo=d.CN)
            self.assertEqual(str(load_window(root, now)[0]), '2026-11-03')
            path.write_text(json.dumps({'last_success_at': '2026-11-10T10:00:00+08:00'}))
            with self.assertRaises(ValueError):
                load_window(root, now)

    def test_failed_initial_attempt_retains_pending_backfill(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'state').mkdir()
            (root/'state/latest_status.json').write_text(json.dumps({'failed': True, 'window_start': '2026-11-04'}))
            self.assertEqual(str(load_window(root, datetime(2026, 11, 10, tzinfo=d.CN))[0]), '2026-11-04')

    def test_display_uses_the_same_backfill_window(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            now = datetime(2026, 11, 6, 12, tzinfo=d.CN)
            start = now.date() - timedelta(days=2)
            block = '''### 教育技术学 · 四日研究
- **实际来源**：教育技术学
- **归类**：B
- **日期 / 链接**：2026-11-04 / [原文](https://mp.weixin.qq.com/s/gap)
- **可信度**：✅ 确认来源
- **简述**：原文指出研究结果
'''
            result = report_store.consolidate(root, now, block, d.article_key, window_start=start)
            text = (root/'reports'/result['report']).read_text(encoding='utf-8')
            self.assertIn('覆盖 2026-11-04 00:00', text)
            self.assertIn('### 四日研究', text)
            self.assertEqual(result['current_entries'], 1)

    def test_only_successful_full_auto_run_advances_cursor(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'prompt.md').write_text('测试', encoding='utf-8')
            with patch.dict(d.os.environ, {'DEEPSEEK_API_KEY': 'dummy', 'TAVILY_API_KEY': 'dummy', 'SEARCH_TEST_PROVIDER': 'auto'}), \
                    patch.object(d, 'discover', return_value=('测试', [])):
                trial = d.main(['--limit', '3'], root)
                self.assertFalse(trial['cursor_advanced'])
                self.assertFalse((root/'state/collection_cursor.json').exists())
                full = d.main([], root)
                self.assertTrue(full['cursor_advanced'])
                previous = (root/'state/collection_cursor.json').read_bytes()
                with patch.object(d, 'discover', side_effect=d.ServiceError('provider failure')):
                    failed = d.main([], root)
                self.assertTrue(failed['failed'])
                self.assertFalse(failed['cursor_advanced'])
                self.assertEqual((root/'state/collection_cursor.json').read_bytes(), previous)

    def test_capacity_limited_run_leaves_cursor_retryable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'prompt.md').write_text('测试', encoding='utf-8')
            def discover(group, name, now, key, router):
                return name, [{'url': 'https://mp.weixin.qq.com/s/' + d.PROFILES[name]['original_id'],
                               'name': name}] if name in d.PROFILES else []
            def prepare(result, source_id):
                profile = d.PROFILES[result['name']]
                return {'id': source_id, 'url': result['url'], 'title': '测试研究', 'body': '研究正文',
                        'publisher': profile['publisher'], 'biz': profile['biz'],
                        'read_status': '微信正文读取成功', 'publication_date': datetime.now(d.CN).isoformat()}
            with patch.dict(d.os.environ, {'DEEPSEEK_API_KEY': 'dummy', 'TAVILY_API_KEY': 'dummy', 'SEARCH_TEST_PROVIDER': 'auto'}), \
                    patch.object(d, 'discover', side_effect=discover), patch.object(d, 'prepare', side_effect=prepare), \
                    patch.object(d, 'analyze', side_effect=lambda name, sources, prompt, key: [{'source_id': s['id']} for s in sources]), \
                    patch.object(d, 'synthesize', return_value={'overview': [], 'trends': []}):
                result = d.main([], root)
                self.assertEqual(result['included'], 25)
                self.assertEqual(result['deferred_entries'], 1)
                self.assertFalse(result['cursor_advanced'])
                self.assertFalse((root/'state/collection_cursor.json').exists())
                retried = d.main([], root)
                self.assertEqual(retried['included'], 1)
                self.assertTrue(retried['cursor_advanced'])


if __name__ == '__main__':
    unittest.main()
