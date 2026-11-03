import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_digest as d


class DigestTests(unittest.TestCase):
    def test_wechat_identity_and_tracking(self):
        base = 'https://mp.weixin.qq.com/s?__biz=abc&mid=10&idx=1&sn=xyz'
        self.assertEqual(d.article_key(base), d.article_key(base + '&scene=27&from=abc'))
        self.assertNotEqual(d.article_key(base), d.article_key(base.replace('idx=1', 'idx=2')))

    def test_estimated_date_does_not_prove_publication(self):
        source = {'body': '研究采用2026年数据。', 'publication_date': None,
                  'search_estimated_date': '2026-11-03'}
        self.assertIsNone(d.get_date(source, {'publication_date': '2026-11-03', 'date_evidence': ''})[0])
        self.assertIsNone(d.get_date(source, {'publication_date': '2026-11-03', 'date_evidence': '发布时间：2026-11-03'})[0])
        source['body'] = '发布时间：2026年11月3日。研究结果如下'
        day, _ = d.get_date(source, {'publication_date': '2026-11-03', 'date_evidence': '发布时间：2026年11月3日'})
        self.assertEqual(str(day), '2026-11-03')

    def test_wechat_epoch_and_verification_page(self):
        html = '<meta property="og:title" content="测试"><meta name="author" content="撰稿人"><a id="js_name">教育技术学</a><div id="js_content"><p>研究正文</p></div><script>var ct = "1793664000";</script>'
        article = d.extract_wechat(html, 'https://mp.weixin.qq.com/s/test')
        self.assertIn('+08:00', article['published_at'])
        self.assertEqual(article['publisher'], '教育技术学')
        self.assertEqual(article['author'], '撰稿人')
        with self.assertRaises(ValueError):
            d.extract_wechat('<html>请完成验证</html>', 'https://mp.weixin.qq.com/s/test')

    def test_503_retries_and_safe_diagnostic(self):
        error = HTTPError('https://api.deepseek.com/chat/completions', 503, 'private body', {}, None)
        with patch.object(d, 'urlopen', side_effect=error) as opened, patch.object(d.time, 'sleep') as slept:
            with self.assertRaises(d.ServiceError) as caught:
                d.post_json('https://api.deepseek.com/chat/completions', 'secret-do-not-log', {})
            self.assertEqual(opened.call_count, 4)
            self.assertEqual(slept.call_count, 3)
            self.assertIn('服务端暂不可用', str(caught.exception))
            self.assertNotIn('secret-do-not-log', str(caught.exception))
            self.assertNotIn('private body', str(caught.exception))

    def test_old_ministry_news_is_not_a_journal_supplement(self):
        source = {'id': 1, 'url': 'https://www.moe.gov.cn/news', 'title': '数字教育研究全球十大热点发布',
                  'body': '发布日期：2026-05-13 新闻正文', 'publication_date': None,
                  'author': None, 'publisher': None, 'read_status': 'Tavily正文'}
        entry = {'source_id': 1, 'publication_date': '2026-05-13', 'date_evidence': '发布日期：2026-05-13'}
        record, reason = d.validate_entry(entry, [source], '电化教育研究', 'A', datetime(2026, 11, 3, tzinfo=d.CN), {})
        self.assertIsNone(record)
        self.assertIn('超出本期', reason)

    @patch.dict(d.PROFILES, {}, clear=True)
    def test_related_news_is_not_an_account_update(self):
        source = {'id': 1, 'url': 'https://news.example.org/article', 'title': 'AI教育新课程',
                  'body': '发布日期：2026-11-02 新闻正文', 'publication_date': None,
                  'author': '教育数字化100人', 'publisher': None, 'read_status': 'Tavily正文'}
        entry = {'source_id': 1, 'publication_date': '2026-11-02', 'date_evidence': '发布日期：2026-11-02'}
        now = datetime(2026, 11, 3, tzinfo=d.CN)
        record, _ = d.validate_entry(entry, [source], '教育数字化100人', 'D', now, {})
        self.assertEqual(record['relation'], 'related')
        self.assertEqual(record['source_label'], 'news.example.org')
        report = d.render(now, [record], [], 3, 25, {'overview': [], 'trends': []})
        domain_section = report.split('## 相关领域动态')[1]
        account_section = report.split('## D 类')[1].split('## E 类')[0]
        self.assertIn('AI教育新课程', domain_section)
        self.assertNotIn('AI教育新课程', account_section)
        source.update(url='https://mp.weixin.qq.com/s/a', read_status='微信正文读取成功')
        record, _ = d.validate_entry(entry, [source], '教育数字化100人', 'D', now, {})
        self.assertEqual(record['relation'], 'related')  # author credit alone is insufficient
        source['publisher'] = '教育数字化100人'
        record, _ = d.validate_entry(entry, [source], '教育数字化100人', 'D', now, {})
        self.assertEqual(record['relation'], 'confirmed')

    def test_verified_profile_rejects_same_name_wrong_biz(self):
        name = '教育技术学'
        source = {'id': 1, 'url': 'https://mp.weixin.qq.com/s/example', 'title': '测试研究',
                  'body': '发布日期：2026-11-03 正文', 'publication_date': '2026-11-03T10:00:00+08:00',
                  'publisher': name, 'biz': 'wrong', 'read_status': '微信正文读取成功'}
        now = datetime(2026, 11, 3, 18, tzinfo=d.CN)
        entry = {'source_id': 1}
        rejected, _ = d.validate_entry(entry, [source], name, 'B', now, {})
        self.assertIsNone(rejected)
        usable, reasons = d.prefilter_sources([source], name, 'B', now)
        self.assertFalse(usable)
        self.assertIn('未调用模型', reasons[0])
        source['biz'] = d.PROFILES[name]['biz']
        accepted, _ = d.validate_entry(entry, [source], name, 'B', now, {})
        self.assertEqual(accepted['relation'], 'confirmed')
        source['publication_date'] = '2026-09-21T11:50:00+08:00'
        usable, reasons = d.prefilter_sources([source], name, 'B', now)
        self.assertFalse(usable)
        self.assertIn('超出本期', reasons[0])

    def test_profile_discovery_includes_id_query_and_sample(self):
        calls = []
        def fake_post(url, key, payload):
            calls.append(dict(payload))
            return {'results': []}
        with patch.object(d, 'post_json', side_effect=fake_post):
            query, results = d.discover('B', '教育技术学', datetime(2026, 11, 3, tzinfo=d.CN), 'dummy')
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]['query'], '"JYJSX2014"')
        self.assertIn('Y-v5io7KoD4sd4b8c7Llbw', results[0]['url'])
        self.assertIn('已知样例入口', query)

    @patch.dict(d.PROFILES, {}, clear=True)
    def test_end_to_end_dedup_and_retryable_failure(self):
        now = datetime.now(d.CN)
        today = now.date().isoformat()
        results = [
            {'url': 'https://example.org/new', 'title': '新研究', 'raw_content': f'发布日期：{today} 教育技术研究正文。'},
            {'url': 'https://example.org/old', 'title': '旧研究', 'raw_content': '发布日期：2020-01-01 旧正文'},
            {'url': 'https://example.org/unknown', 'title': '未知日期', 'raw_content': '正文缺少日期。'},
        ]
        def fake_post(url, key, payload):
            if 'tavily' in url:
                if '教育数字化100人' in payload['query']:
                    raise d.ServiceError('mock provider failure')
                return {'results': results}
            if 'sources' not in payload['messages'][1]['content']:
                return {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"overview":[],"trends":[]}'}}]}
            request = json.loads(payload['messages'][1]['content'])
            sources = request['sources']
            entries = []
            for s in sources:
                if request['account'] == '电化教育研究' and not s['url'].endswith('new'):
                    continue
                day = today if s['url'].endswith('new') else '2020-01-01' if s['url'].endswith('old') else None
                entries.append({'source_id': s['id'], 'publication_date': day,
                                'date_evidence': f'发布日期：{day}' if day else '', 'summary': '原文指出测试结果'})
            return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'entries': entries})}}]}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'prompt.md').write_text('测试任务书', encoding='utf-8')
            with patch.dict(os.environ, {'TAVILY_API_KEY': 'test', 'DEEPSEEK_API_KEY': 'test'}), patch.object(d, 'post_json', side_effect=fake_post):
                health = d.main(['--limit', '3'], root)
                self.assertTrue(health['failed'])
                self.assertEqual(health['included'], 1)
                state = json.loads((root / 'state/seen_articles.json').read_text(encoding='utf-8'))
                self.assertEqual(len(state), 1)
                self.assertIn(d.article_key(results[0]['url']), state)
                self.assertNotIn(d.article_key(results[1]['url']), state)
                second = d.main(['--limit', '3'], root)
                self.assertEqual(second['included'], 0)


if __name__ == '__main__':
    unittest.main()
