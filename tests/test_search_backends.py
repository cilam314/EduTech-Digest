import json
import os
from pathlib import Path
import sys
import unittest
import tempfile
from unittest.mock import patch
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_digest as d
from search_backends import SearchRouter, SPARK_MODELS, citation_results


def cited(url='https://mp.weixin.qq.com/s/new'):
    return {'status': 'completed', 'output': [
        {'type': 'tool_search_call', 'arguments': {'query': 'test'}},
        {'type': 'message', 'content': [{'type': 'output_text', 'text': '不要把这段模型生成文字当作原文正文',
                                       'annotations': [{'type': 'url_citation', 'url': url, 'title': '检索信源'}]}]}]}


class SearchTests(unittest.TestCase):
    @patch.dict(os.environ, {'SEARCH_TEST_PROVIDER': 'auto'})
    def test_tavily_success_never_calls_spark_even_empty(self):
        calls = []
        def post(url, key, payload):
            calls.append(url)
            return {'results': []}
        router = SearchRouter(post, d.ServiceError, 'tavily-dummy', 'spark-dummy')
        self.assertEqual(router.search({'query': 'test'})['results'], [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(router.counts[SPARK_MODELS[0]], 0)

    @patch.dict(os.environ, {'SEARCH_TEST_PROVIDER': 'auto'})
    def test_priority_fallback_and_disable_failed_providers(self):
        calls = []
        def post(url, key, payload):
            provider = payload.get('model', 'Tavily')
            calls.append(provider)
            if provider in ('Tavily', SPARK_MODELS[0]):
                raise d.ServiceError('quota exhausted')
            return cited()
        router = SearchRouter(post, d.ServiceError, 'tavily-dummy', 'spark-dummy')
        result = router.search({'query': 'test', 'include_domains': ['mp.weixin.qq.com']})
        self.assertEqual(calls, ['Tavily', *SPARK_MODELS])
        self.assertEqual(result['results'][0]['search_provider'], SPARK_MODELS[1])
        self.assertEqual(result['results'][0]['raw_content'], '')
        router.search({'query': 'another'})
        self.assertEqual(calls, ['Tavily', *SPARK_MODELS, SPARK_MODELS[1]])

    def test_model_generated_links_are_not_search_citations(self):
        data = {'status': 'completed', 'output': [{'type': 'message', 'content': [{
            'type': 'output_text', 'text': '{"url":"https://mp.weixin.qq.com/s/madeup"}', 'annotations': []}]}]}
        with self.assertRaises(d.ServiceError):
            citation_results(data, d.ServiceError)

    @patch.dict(os.environ, {'SEARCH_TEST_PROVIDER': 'auto'})
    def test_quota_in_http200_response_falls_back(self):
        def post(url, key, payload):
            return {'error': 'quota'} if 'tavily' in url else cited()
        router = SearchRouter(post, d.ServiceError, 'tavily-dummy', 'spark-dummy')
        self.assertEqual(router.search({'query': 'q'})['results'][0]['search_provider'], SPARK_MODELS[0])

    @patch.dict(os.environ, {'SEARCH_TEST_PROVIDER': 'auto'})
    def test_ungrounded_4b_falls_back_to_17b(self):
        def post(url, key, payload):
            if payload['model'] == SPARK_MODELS[0]:
                return {'status': 'completed', 'output': []}
            return cited()
        router = SearchRouter(post, d.ServiceError, '', 'spark-dummy')
        self.assertEqual(router.search({'query': 'q'})['results'][0]['search_provider'], SPARK_MODELS[1])

    def test_expansion_requires_real_body_identity_date_and_topic(self):
        now = datetime(2026, 11, 3, 18, tzinfo=d.CN)
        source = {'id': 1, 'url': 'https://mp.weixin.qq.com/s/a', 'title': '游戏化教学实证',
                  'body': '本研究讨论游戏化教学的课堂应用。', 'publisher': '游戏学习研究者', 'biz': 'verified-new-biz',
                  'read_status': '微信正文读取成功', 'publication_date': now.isoformat()}
        entry = {'source_id': 1, 'topic_evidence': source['body']}
        record, _ = d.validate_entry(entry, [source], '游戏化教学', 'F', now, {})
        self.assertEqual(record['relation'], 'discovered')
        self.assertEqual(record['source_label'], '游戏学习研究者')
        self.assertNotEqual(record['account'], record['source_label'])
        for change in ({'topic_evidence': '模型编造的游戏化片段'}, {'topic_evidence': ''}):
            rejected, _ = d.validate_entry({**entry, **change}, [source], '游戏化教学', 'F', now, {})
            self.assertIsNone(rejected)
        source['publication_date'] = '2020-01-01T10:00:00+08:00'
        rejected, _ = d.validate_entry(entry, [source], '游戏化教学', 'F', now, {})
        self.assertIsNone(rejected)

    def test_expansion_saves_candidate_account_without_changing_original_list(self):
        now = datetime.now(d.CN)
        source = {'id': 1, 'url': 'https://mp.weixin.qq.com/s/new-discovered', 'title': '创客教育实践',
                  'body': '本研究讨论创客教育的课堂应用。', 'publisher': '创客课堂研究', 'biz': 'new-biz',
                  'read_status': '微信正文读取成功', 'publication_date': now.isoformat()}
        entry = {'source_id': 1, 'topic_evidence': source['body'], 'summary': '原文指出创客教育实践。'}
        def discover(group, name, now, key, router):
            return name, [{'url': source['url']}] if name == '创客教育' else []
        def prepare(result, source_id):
            return {**source, 'id': source_id}
        def analyze(name, sources, prompt, key):
            return [{**entry, 'source_id': sources[0]['id']}] if sources else []
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'prompt.md').write_text('测试', encoding='utf-8')
            with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'dummy', 'TAVILY_API_KEY': 'dummy'}), \
                    patch.object(d, 'discover', side_effect=discover), patch.object(d, 'prepare', side_effect=prepare), \
                    patch.object(d, 'analyze', side_effect=analyze), patch.object(d, 'synthesize', return_value={'overview': [], 'trends': []}):
                status = d.main(['--limit', '1'], root)
            candidates = json.loads((root/'state/candidate_accounts.json').read_text(encoding='utf-8'))
            self.assertEqual(candidates['new-biz']['name'], '创客课堂研究')
            self.assertEqual(status['expanded'], 1)
            self.assertEqual(status['confirmed'], 0)
            self.assertFalse(status['failed'])
            self.assertEqual(sum(len(names) for _, names in d.GROUPS.values()), 26)


if __name__ == '__main__':
    unittest.main()
