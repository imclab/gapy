from apiclient.discovery import build
import httplib2
from oauth2client.client import SignedJwtAssertionCredentials, flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import run

from gapy.response import ManagementResponse, QueryResponse
from gapy.error import GapyError

GOOGLE_API_SCOPE = "https://www.googleapis.com/auth/analytics"
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"


def _get_storage(storage, storage_path):
    if not storage:
        if not storage_path:
            raise GapyError(
                "Must provide either a storage object or a storage_path")
        storage = Storage(filename=storage_path)
    return storage


def from_private_key(account_name, private_key=None, private_key_path=None,
                     storage=None, storage_path=None, api_version="v3"):
    """Create a client for a service account.

    Create a client with an account name and a private key.

     Args:
      account_name: str, the account identifier (probably the account email).
      private_key: str, the private key as a string.
      private_key_path: str, path to a file with the private key in.
      storage: oauth2client.client.Storage, a Storage implementation to store
               credentials.
      storage_path: str, path to a file storage.
    """
    if not private_key:
        if not private_key_path:
            raise GapyError(
                "Must provide either a private_key or a private_key_file")
        if isinstance(private_key_path, basestring):
            private_key_path = open(private_key_path)
        private_key = private_key_path.read()

    storage = _get_storage(storage, storage_path)

    credentials = SignedJwtAssertionCredentials(account_name, private_key,
                                                GOOGLE_API_SCOPE)
    credentials.set_store(storage)

    return Client(_build(credentials, api_version))


def from_secrets_file(client_secrets, storage=None, storage_path=None,
                      api_version="v3"):
    """Create a client for a web or installed application.

    Create a client with a client secrets file.

    Args:
        client_secrets: str, path to the client secrets file (downloadable from
                             Google API Console)
      storage: oauth2client.client.Storage, a Storage implementation to store
               credentials.
      storage_path: str, path to a file storage.
    """
    flow = flow_from_clientsecrets(client_secrets,
                                   scope=GOOGLE_API_SCOPE)
    storage = _get_storage(storage, storage_path)
    credentials = storage.get()
    if credentials is None or credentials.invalid:
        credentials = run(flow, storage)

    return Client(_build(credentials, api_version))


def _build(credentials, api_version):
    """Build the client object."""
    http = httplib2.Http()
    http = credentials.authorize(http)

    return build("analytics", api_version, http=http)


class Client(object):
    def __init__(self, service):
        self._service = service

    @property
    def management(self):
        return ManagementClient(self._service)

    @property
    def query(self):
        return QueryClient(self._service)


class ManagementClient(object):
    def __init__(self, service):
        self._service = service

    def accounts(self):
        return self._list("accounts")

    def account(self, id):
        return self._item(self.accounts(), id)

    def webproperties(self, account):
        return self._list("webproperties", accountId=account)

    def webproperty(self, account, id):
        return self._item(self.webproperties(account), id)

    def profiles(self, account, webproperty):
        return self._list("profiles", accountId=account,
                          webPropertyId=webproperty)

    def profile(self, account, webproperty, id):
        return self._item(self.profiles(account, webproperty), id)

    def _list(self, name, **kwargs):
        return ManagementResponse(
            getattr(self._service.management(), name)().list(
                **kwargs).execute()
        )

    def _item(self, response, id):
        for item in response:
            if item["id"] == id:
                return item
        raise GapyError("Id not found")


class QueryClient(object):
    def __init__(self, service):
        self._service = service

    def _to_list(self, value):
        """Turn an argument into a list"""
        if value is None:
            return []
        elif isinstance(value, list):
            return value
        else:
            return [value]

    def _prefix_ga(self, values):
        """Prefix all items in a list with 'ga:'"""
        return ("ga:%s" % value for value in values)

    def _to_ga_param(self, values):
        """Turn a list of values into a GA list parameter"""
        return ",".join(self._prefix_ga(values))

    def get(self, ids, start_date, end_date, metrics,
            dimensions=None, filters=None):
        ids = self._to_list(ids)
        metrics = self._to_list(metrics)

        start_date = start_date.strftime("%Y-%m-%d")
        end_date = end_date.strftime("%Y-%m-%d")

        dimensions = self._to_list(dimensions)
        filters = self._to_list(filters)

        return self._get_response(
            metrics, dimensions,
            ids=self._to_ga_param(ids),
            start_date=start_date,
            end_date=end_date,
            metrics=self._to_ga_param(metrics),
            dimensions=self._to_ga_param(dimensions) or None,
            filters=self._to_ga_param(filters) or None)

    def _filter_empty(self, kwargs, key):
        if key in kwargs and kwargs[key] is None:
            del kwargs[key]
        return kwargs

    def get_raw_response(self, **kwargs):
        kwargs = self._filter_empty(kwargs, "dimensions")
        kwargs = self._filter_empty(kwargs, "filters")
        return self._service.data().ga().get(**kwargs).execute()

    def _get_response(self, m, d, **kwargs):
        return QueryResponse(
            self,
            self.get_raw_response(**kwargs),
            m, d
        )
