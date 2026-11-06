from datetime import datetime, timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from public_article_index import PublicArticleIndex, WeChatLinks
import run_digest as d


def card(source='教育技术学自留地', path='/items/one', day='2026-11-05'):
    return f'<article data-item-id="one"><header><span>{source} · 微信公众号</span><time datetime="{day}T00:00:00Z">08:00</time></header><h3><a href="{path}">索引标题</a></h3></article>'


class PublicIndexTests(unittest.TestCase):
    def test_pagination_caching_and_only_original_links_returned(self):
        now = datetime(2026, 11, 6, tzinfo=d.CN)
        pages = {'https://index.test/all?page=1': card(),
                 'https://index.test/all?page=2': card(path='/items/two', day='2026-11-02'),
                 'https://index.test/items/one': '<a href="https://mp.weixin.qq.com/s/new">原文</a><a href="https://mp.weixin.qq.com/s/new">重复</a>',
                 'https://index.test/items/two': '<a href="https://example.org/fake">不可当作公众号原文</a>'}
        calls = []
        def fetch(url):
            calls.append(url)
            return pages[url]
        index = PublicArticleIndex('https://index.test', now, now.date()-timedelta(days=2), fetch)
        result = index.get('教育技术学自留地')
        self.assertEqual([r['url'] for r in result], ['https://mp.weixin.qq.com/s/new'])
        self.assertEqual(result[0]['raw_content'], '')
        self.assertNotIn('published_date', result[0])
        self.assertEqual(index.get('教育技术学自留地'), result)
        index.get('其他账号')
        self.assertEqual(len(calls), 4)

    def test_offsite_detail_and_wechat_lookalike_are_not_followed(self):
        now = datetime(2026, 11, 6, tzinfo=d.CN)
        index = PublicArticleIndex('https://index.test', now, now.date(),
                                   lambda url: card(path='https://attacker.test/items/x', day='2026-11-01'))
        self.assertEqual(index.get('教育技术学自留地'), [])
        parser = WeChatLinks()
        parser.feed('<a href="https://mp.weixin.qq.com.attacker.test/s/x">fake</a><a href="javascript:bad">fake</a>')
        self.assertEqual(parser.urls, [])

    def test_failure_is_visible_and_search_can_still_proceed(self):
        now = datetime(2026, 11, 6, tzinfo=d.CN)
        def fail(url):
            raise TimeoutError('private response')
        index = PublicArticleIndex('https://index.test', now, now.date(), fail)
        self.assertEqual(index.get('教育技术学自留地'), [])
        self.assertEqual(index.events[0]['status'], 'fetch_failed')
        self.assertNotIn('private response', str(index.events))

    def test_index_pointer_is_not_publisher_or_date_evidence(self):
        name = '教育技术学自留地'
        now = datetime(2026, 11, 6, tzinfo=d.CN)
        source = {'id': 1, 'url': 'https://mp.weixin.qq.com/s/new', 'title': '索引标题', 'body': '索引摘要',
                  'publisher': name, 'biz': 'wrong-biz', 'read_status': '仅搜索摘要',
                  'publication_date': '2026-11-05T08:00:00+08:00'}
        record, reason = d.validate_entry({'source_id': 1}, [source], name, 'D', now, {})
        self.assertIsNone(record)
        self.assertIn('账号标识', reason)

    def test_discovery_combines_exact_search_and_live_index(self):
        from search_backends import SearchRouter
        calls = []
        def post(url, key, payload):
            calls.append(dict(payload))
            return {'results': []}
        class Index:
            def get(self, name):
                return [{'url': 'https://mp.weixin.qq.com/s/new', 'search_provider': '公开文章索引'}]
        router = SearchRouter(post, d.ServiceError, 'dummy', '')
        router.article_index = Index()
        query, results = d.discover('D', '教育技术学自留地', datetime(2026, 11, 6, tzinfo=d.CN), 'dummy', router)
        self.assertEqual(results[0]['url'], 'https://mp.weixin.qq.com/s/new')
        self.assertTrue(all(p['exact_match'] for p in calls))
        self.assertIn('公开索引原文入口 1 条', query)

    def test_valid_public_pointer_survives_search_backend_failure(self):
        from search_backends import SearchRouter
        def post(*args):
            raise d.ServiceError('quota')
        class Index:
            def get(self, name):
                return [{'url': 'https://mp.weixin.qq.com/s/new'}]
        router = SearchRouter(post, d.ServiceError, 'dummy', '')
        router.article_index = Index()
        query, results = d.discover('D', '教育技术学自留地', datetime(2026, 11, 6, tzinfo=d.CN), 'dummy', router)
        self.assertEqual(len(results), 1)
        self.assertIn('搜索服务失败', query)

    def test_transient_article_read_failure_is_retried(self):
        html = '<meta property="og:title" content="新研究"><a id="js_name">教育技术学自留地</a><div id="js_content"><p>研究正文</p></div><script>var biz="MzUxMjA0NTU4Mw=="; var ct="1793923200";</script>'
        with patch.object(d.read_article, 'download', side_effect=[TimeoutError(), html]) as download, \
                patch.object(d.time, 'sleep'):
            source = d.prepare({'url': 'https://mp.weixin.qq.com/s/new'}, 1)
        self.assertEqual(download.call_count, 2)
        self.assertEqual(source['publisher'], '教育技术学自留地')
        self.assertEqual(source['read_status'], '微信正文读取成功')

    def test_report_limits_each_account_but_not_total_entries(self):
        from report_store import briefing_markdown
        now = datetime(2026, 11, 6, tzinfo=d.CN)
        index = {}
        for number in range(30):
            source = '同一账号' if number < 4 else f'账号{number}'
            index[str(number)] = {'date': '2026-11-05', 'title': f'文章{number}', 'source': source,
                                  'url': f'https://mp.weixin.qq.com/s/{number}', 'confirmed': True, 'group': 'D',
                                  **{field: '原文未说明' for field in ('summary','research','technology','applications','reflection')}}
        output, verified = briefing_markdown(index, now, '', {})
        self.assertEqual(len(verified), 29)
        self.assertEqual(sum(r['source'] == '同一账号' for r in verified), 3)
        self.assertEqual(output.count('[阅读全文]'), 29)


if __name__ == '__main__':
    unittest.main()
