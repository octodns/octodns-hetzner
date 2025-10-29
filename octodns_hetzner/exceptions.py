#
#
#

from octodns.provider import ProviderException


class HetznerClientException(ProviderException):
    pass


class HetznerClientNotFound(HetznerClientException):
    def __init__(self):
        super().__init__('Not Found')


class HetznerClientUnauthorized(HetznerClientException):
    def __init__(self):
        super().__init__('Unauthorized')
