import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
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
        html = '<meta property="og:title" content="测试"><meta name="author" content="教育技术学"><div id="js_content"><p>研究正文</p></div><script>var ct = "1793664000";</script>'
        article = d.extract_wechat(html, 'https://mp.weixin.qq.com/s/test')
        self.assertIn('+08:00', article['published_at'])
        with self.assertRaises(ValueError):
            d.extract_wechat('<html>请完成验证</html>', 'https://mp.weixin.qq.com/s/test')

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
