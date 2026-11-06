"""Public index pointers only. Publisher/date/body must be verified on WeChat."""
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


def download(url):
    with urlopen(Request(url, headers={'User-Agent': 'EduTech-Digest/1.0'}), timeout=25) as response:
        return response.read(4 * 1024 * 1024).decode('utf-8', 'replace')


def normalized(value):
    return ''.join(value.split()).casefold()


class Cards(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards, self.current = [], None
        self.in_header = self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'article' and attrs.get('data-item-id'):
            self.current = {'source': '', 'title': '', 'href': '', 'indexed_at': ''}
        if self.current is not None:
            if tag == 'header':
                self.in_header = True
            if tag == 'h3':
                self.in_title = True
            if tag == 'a' and self.in_title:
                self.current['href'] = attrs.get('href', '')
            if tag == 'time':
                self.current['indexed_at'] = attrs.get('datetime', '')

    def handle_data(self, value):
        if self.current is not None:
            if self.in_header:
                self.current['source'] += value
            if self.in_title:
                self.current['title'] += value

    def handle_endtag(self, tag):
        if tag == 'header':
            self.in_header = False
        if tag == 'h3':
            self.in_title = False
        if tag == 'article' and self.current is not None:
            self.current['source'] = self.current['source'].split(' · ', 1)[0].strip()
            self.cards.append(self.current)
            self.current = None


class WeChatLinks(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        url = dict(attrs).get('href', '')
        parts = urlsplit(url)
        if (tag == 'a' and parts.scheme in {'http', 'https'} and parts.hostname == 'mp.weixin.qq.com'
                and parts.path.startswith('/s') and url not in self.urls):
            self.urls.append(url)


class PublicArticleIndex:
    def __init__(self, base_url, now, start, fetch=download, max_pages=8):
        self.base_url, self.now, self.start = base_url.rstrip('/'), now, start
        self.fetch, self.max_pages = fetch, max_pages
        self.cards, self.events, self.cache = None, [], {}

    def load(self):
        self.cards = []
        for page in range(1, self.max_pages + 1):
            try:
                parser = Cards()
                parser.feed(self.fetch(f'{self.base_url}/all?page={page}'))
                if not parser.cards:
                    self.events.append({'stage': 'list', 'page': page, 'status': 'empty_or_structure_changed'})
                    break
                self.cards.extend(parser.cards)
                self.events.append({'stage': 'list', 'page': page, 'status': 'ok', 'cards': len(parser.cards)})
                days = []
                for card in parser.cards:
                    try:
                        days.append(datetime.fromisoformat(card['indexed_at'].replace('Z', '+00:00')).astimezone(self.now.tzinfo).date())
                    except ValueError:
                        pass
                # Index timestamps are hints for pagination only, never publication evidence.
                if days and max(days) < self.start - timedelta(days=1):
                    break
            except Exception:
                self.events.append({'stage': 'list', 'page': page, 'status': 'fetch_failed'})
                break
        else:
            self.events.append({'stage': 'list', 'status': 'page_limit_reached'})

    def get(self, name):
        if self.cards is None:
            self.load()
        if name in self.cache:
            return self.cache[name]
        results, visited = [], set()
        for card in self.cards:
            if normalized(card['source']) != normalized(name):
                continue
            detail = urljoin(self.base_url + '/', card['href'])
            if (urlsplit(detail).netloc != urlsplit(self.base_url).netloc
                    or not urlsplit(detail).path.startswith('/items/') or detail in visited):
                continue
            visited.add(detail)
            try:
                parser = WeChatLinks()
                parser.feed(self.fetch(detail))
                for url in parser.urls:
                    if all(r['url'] != url for r in results):
                        results.append({'url': url, 'title': card['title'], 'content': '', 'raw_content': '',
                                        'search_provider': '公开文章索引（原文待核验）', 'discovery_page': detail})
                self.events.append({'stage': 'detail', 'account': name, 'status': 'ok', 'links': len(parser.urls)})
            except Exception:
                self.events.append({'stage': 'detail', 'account': name, 'status': 'fetch_failed'})
            if len(results) >= 12:
                self.events.append({'stage': 'detail', 'account': name, 'status': 'account_limit_reached'})
                break
        self.cache[name] = results
        return results
