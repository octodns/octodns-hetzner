#
#
#

from requests import Session

from octodns import __VERSION__ as octodns_version

from . import __version__ as package_version
from .exceptions import HetznerClientNotFound, HetznerClientUnauthorized


class HetznerClient(object):
    BASE_URL = 'https://dns.hetzner.com/api/v1'

    def __init__(self, token):
        session = Session()
        session.headers.update(
            {
                'Auth-API-Token': token,
                'User-Agent': f'octodns/{octodns_version} octodns-hetzner/{package_version}',
            }
        )
        self._session = session

    def _do(self, method, path, params=None, data=None):
        url = f'{self.BASE_URL}{path}'
        response = self._session.request(method, url, params=params, json=data)
        if response.status_code == 401:
            raise HetznerClientUnauthorized()
        if response.status_code == 404:
            raise HetznerClientNotFound()
        response.raise_for_status()
        return response

    def domains(self):
        path = '/zones'
        ret = []

        page = 1
        while True:

            data = self._do('GET', path, {'page': page}).json()

            ret += data.get('zones', [])
            pagination = data.get('meta', {}).get('pagination', {})

            next_page = pagination.get('next_page')
            # Hetzner returns 0/None when there is no next page
            if not next_page or (
                isinstance(next_page, int) and next_page <= page
            ):
                break

            page = next_page

        return ret

    def _do_json(self, method, path, params=None, data=None):
        return self._do(method, path, params, data).json()

    def zone_get(self, name):
        params = {'name': name}
        return self._do_json('GET', '/zones', params)['zones'][0]

    def zone_create(self, name, ttl=None):
        data = {'name': name, 'ttl': ttl}
        return self._do_json('POST', '/zones', data=data)['zone']

    def zone_records_get(self, zone_id):
        params = {'zone_id': zone_id}
        records = self._do_json('GET', '/records', params=params)['records']
        for record in records:
            if record['name'] == '@':
                record['name'] = ''
        return records

    def zone_record_create(self, zone_id, name, _type, value, ttl=None):
        data = {
            'name': name or '@',
            'ttl': ttl,
            'type': _type,
            'value': value,
            'zone_id': zone_id,
        }
        self._do('POST', '/records', data=data)

    def zone_record_delete(self, zone_id, record_id):
        self._do('DELETE', f'/records/{record_id}')
