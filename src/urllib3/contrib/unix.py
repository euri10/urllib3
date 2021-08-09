import logging
import socket
from typing import Any, Mapping, Optional, Sequence, Tuple, Union

from ..connection import HTTPConnection
from ..connectionpool import HTTPConnectionPool
from ..poolmanager import PoolManager
from ..util.connection import SOCKET_GLOBAL_DEFAULT_TIMEOUT, _set_socket_options

log = logging.getLogger(__name__)


class UnixHTTPConnection(HTTPConnection):
    """
    An HTTP connection via a Unix domain socket.
    """

    default_socket_options: Sequence[Tuple[int, int, Union[int, bytes]]]

    def __init__(self, socket_path: str, **kwargs: Any) -> None:
        self.socket_path = socket_path
        # host needs to be sent along as a fake value in order
        # to be used as the HTTP Host header when one isn't supplied.
        # Since this is a unix socket, there's no sensible default
        # value other than 'localhost'.
        super().__init__(host="localhost", **kwargs)

    def _new_conn(self) -> socket.socket:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        # If provided, set socket level options before connecting.
        _set_socket_options(sock, self.socket_options)

        if self.timeout is not SOCKET_GLOBAL_DEFAULT_TIMEOUT:
            sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        return sock

    # Override all port stuff, since there is no port
    default_port = None


class UnixHTTPConnectionPool(HTTPConnectionPool):
    """
    A thread-safe connecton pool for one Unix domain socket.

    :param socket_path:
        Path to be used for this HTTP Connection (e.g. "/var/run/server.sock").
    """

    ConnectionCls = UnixHTTPConnection

    def __init__(self, socket_path: str, **conn_kw: Any) -> None:
        self.socket_path = socket_path
        super().__init__(host=socket_path, **conn_kw)

    def _new_conn(self) -> UnixHTTPConnection:
        """
        Return a fresh :class:`UnixHTTPConnection`.
        """
        self.num_connections += 1
        log.debug(
            "Starting new HTTP connection (%d): %s",
            self.num_connections,
            self.socket_path,
        )

        conn = self.ConnectionCls(
            socket_path=self.socket_path,
            timeout=self.timeout.connect_timeout,
            **self.conn_kw,
        )
        return conn

    def __str__(self) -> str:
        return "{}(socket_path={!r})".format(type(self).__name__, self.socket_path)


class UnixHostHTTPConnectionPool(UnixHTTPConnectionPool):
    """
    A thread-safe connection pool for one Unix socket, addressed by URI.
    :param host:
        URI quoted path to be used for this HTTP Connection (e.g. "%2Fvar%2Frun%2Fserver.sock").
    """

    scheme = "http+unix"

    # port exists for API compatibility, but is ignored
    def __init__(self, host: str, port: Optional[int] = None, **conn_kw: Any):
        super().__init__(host, **conn_kw)


class UnixHTTPPoolManager(PoolManager):
    """
    Example::

        >>> manager = UnixHTTPPoolManager()
        >>> manager.request('GET', 'http+unix://%2Fvar%2Frun%2Fserver.sock/')
    """

    def __init__(
        self,
        num_pools: int = 10,
        headers: Optional[Mapping[str, str]] = None,
        **connection_pool_kw: Any,
    ) -> None:
        super().__init__(num_pools=num_pools, headers=headers, **connection_pool_kw)
        self.pool_classes_by_scheme[
            UnixHostHTTPConnectionPool.scheme
        ] = UnixHostHTTPConnectionPool
        self.key_fn_by_scheme[
            UnixHostHTTPConnectionPool.scheme
        ] = self.key_fn_by_scheme["http"]
