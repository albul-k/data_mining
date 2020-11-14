import datetime as dt
import json
import scrapy
from ..items import InstagramRelations


class InstagramRelationsSpider(scrapy.Spider):
    name = 'instagram_relations'
    allowed_domains = ['www.instagram.com']
    start_urls = ['https://www.instagram.com/']
    login_url = 'https://www.instagram.com/accounts/login/ajax/'
    api_url = '/graphql/query/'
    query_hash = {
        'followings': 'd04b0a864b4b54837c0d870b0e77e076',
        'mutual': 'c76146de99bb02f6415203be841dd25a',
    }
    max_depth = 3

    def __init__(self, login, enc_password, *args, **kwargs) -> None:
        # '29336991533' -> '2990740856'
        self.id_first = '29336991533'
        self.id_last = '2990740856'
        self.user_first = 'mr_albul'
        self.login = login
        self.enc_passwd = enc_password
        super().__init__(*args, **kwargs)

    def parse(self, response, **kwargs):
        try:
            js_data = self.js_data_extract(response)
            yield scrapy.FormRequest(
                self.login_url,
                method='POST',
                callback=self.parse,
                formdata={
                    'username': self.login,
                    'enc_password': self.enc_passwd,
                },
                headers={
                    'X-CSRFToken': js_data['config']['csrf_token'],
                }
            )
        except AttributeError as e:
            if response.json().get('authenticated'):
                url = f'/{self.user_first}/'
                yield response.follow(
                    url,
                    callback=self.user_parse,
                    cb_kwargs={
                        'user_id': self.id_first,
                        'user_id_from': self.id_first,
                        'chain': list(),
                    },
                )

    def user_parse(self, response, **kwargs):
        if not kwargs['user_id_from'] in kwargs['chain']:
            kwargs['chain'].append(kwargs['user_id_from'])

        if len(kwargs['chain']) < self.max_depth:
            variables = {
                'id': kwargs['user_id'],
                'include_reel': 'true',
                'fetch_mutual': 'true',
                'first': 100,
            }

            url = f"{self.api_url}?query_hash={self.query_hash['mutual']}&variables={json.dumps(variables)}"
            yield response.follow(
                url,
                callback=self.relations_parse,
                cb_kwargs={
                    'user_id': kwargs['user_id'],
                    'user_id_from': kwargs['user_id_from'],
                    'chain': kwargs['chain'],
                },
            )
        else:
            yield None

    def relations_api_parse(self, response, **kwargs):
        yield from self.relations_parse(
            response,
            user_id=kwargs['user_id'],
            user_id_from=kwargs['user_id_from'],
            chain=kwargs['chain'],
        )

    def relations_parse(self, response, **kwargs):
        user = response.json()['data']['user']
        if user['edge_followed_by']['page_info']['has_next_page']:
            variables = {
                'id': kwargs['user_id'],
                'include_reel': 'true',
                'fetch_mutual': 'true',
                'first': 100,
                'after': user['edge_followed_by']['page_info']['end_cursor'],
            }

            url = f"{self.api_url}?query_hash={self.query_hash['mutual']}&variables={json.dumps(variables)}"
            yield response.follow(
                url,
                callback=self.relations_api_parse,
                cb_kwargs={
                    'user_id': kwargs['user_id'],
                    'user_id_from': kwargs['user_id_from'],
                    'chain': kwargs['chain'],
                },
            )

        yield from self.get_user_item(
            response,
            nodes=user['edge_followed_by']['edges'],
            user_id=kwargs['user_id'],
            user_id_from=kwargs['user_id_from'],
            chain=kwargs['chain'],
        )

    def get_user_item(self, response, nodes, **kwargs):
        for node in nodes:
            url = f"/{node['node']['username']}/"
            yield response.follow(
                url,
                callback=self.user_parse,
                cb_kwargs={
                    'user_id': node['node']['id'],
                    'user_id_from': node['node']['id'],
                    'chain': kwargs['chain'],
                },
            )

            is_found = True if self.id_last in kwargs['chain'] else False
            yield InstagramRelations(
                date_parse=dt.datetime.utcnow(),
                data={
                    'id': node['node']['id'],
                    'username': node['node']['username'],
                    'full_name': node['node']['full_name'],
                    'profile_pic_url': node['node']['profile_pic_url'],
                    'id_from': kwargs['user_id_from'],
                    'chain': str(kwargs['chain']),
                    'is_found': is_found,
                }
            )

    @staticmethod
    def js_data_extract(response):
        script = response.xpath(
            '//script[contains(text(), "window._sharedData =")]/text()').get()
        return json.loads(script.replace("window._sharedData =", '')[:-1])
