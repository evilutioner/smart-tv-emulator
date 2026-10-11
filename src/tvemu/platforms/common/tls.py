"""Mutual TLS over asyncio streams, accepting a client's self-signed certificate."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Callable

from OpenSSL import SSL, crypto
from OpenSSL._util import ffi, lib


def certificate_der(certificate) -> bytes:
    return crypto.dump_certificate(crypto.FILETYPE_ASN1, certificate)


def certificate_fingerprint(certificate_or_der) -> str:
    data = (certificate_or_der if isinstance(certificate_or_der, bytes)
            else certificate_der(certificate_or_der))
    digest = hashlib.sha256(data).hexdigest().upper()
    return ":".join(digest[index:index + 2] for index in range(0, len(digest), 2))


# OpenSSL has no call that chooses the alert a failed verification sends; it derives the alert
# from the X509 error left on the store. Each value here is an error its table maps to that alert.
_REJECTION_ERRORS = {
    "certificate_unknown": lib.X509_V_ERR_SUBJECT_ISSUER_MISMATCH,
}


def server_context(root: Path, authorize: Callable[[bytes], bool],
                   *, require_client_certificate: bool = True,
                   rejection_alert: str | None = None,
                   names: tuple[str, str] = ("cert.pem", "key.pem")) -> SSL.Context:
    """A server context that asks the platform whether one client certificate is acceptable.

    `require_client_certificate` is a wire fact, not a policy knob: a device whose firmware
    demands a certificate refuses the handshake outright, while one that merely offers the
    request lets an unauthenticated client through and decides later.

    `rejection_alert` is a wire fact too: the TLS alert the device sends a certificate it
    refuses. Clients branch on it, so a set measured to send one must not get OpenSSL's own
    choice (`unknown_ca` for a self-signed client). None keeps OpenSSL's.
    """
    context = SSL.Context(SSL.TLS_SERVER_METHOD)
    context.set_min_proto_version(SSL.TLS1_2_VERSION)
    context.use_certificate_chain_file(str(root / names[0]))
    context.use_privatekey_file(str(root / names[1]))
    context.check_privatekey()

    def verify(_connection, certificate, _error, depth, _preverified):
        return True if depth else authorize(certificate_der(certificate))

    mode = SSL.VERIFY_PEER
    if require_client_certificate:
        mode |= SSL.VERIFY_FAIL_IF_NO_PEER_CERT
    if rejection_alert is None:
        context.set_verify(mode, verify)
        return context
    error = _REJECTION_ERRORS[rejection_alert]

    # pyOpenSSL's own wrapper hides the store, so the error cannot be set through it.
    @ffi.callback("int (*)(int, X509_STORE_CTX *)")
    def verify_store(_preverified, store):
        if lib.X509_STORE_CTX_get_error_depth(store):
            return 1
        der = certificate_der(crypto.X509._from_raw_x509_ptr(
            lib.X509_dup(lib.X509_STORE_CTX_get_current_cert(store))))
        if authorize(der):
            lib.X509_STORE_CTX_set_error(store, lib.X509_V_OK)
            return 1
        lib.X509_STORE_CTX_set_error(store, error)
        return 0

    lib.SSL_CTX_set_verify(context._context, mode, verify_store)
    context._rejection_verify = verify_store     # the callback lives as long as the context
    return context


class TLSStream:
    """Drive a pyOpenSSL memory BIO without taking ownership of asyncio's TCP socket."""

    def __init__(self, context: SSL.Context, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter, *, require_certificate: bool = True):
        self.reader, self.writer = reader, writer
        self.connection = SSL.Connection(context, None)
        self.connection.set_accept_state()
        self.require_certificate = require_certificate
        self.closed = False

    async def handshake(self) -> bytes:
        """Complete the handshake, returning the client certificate, or b"" when it sent none."""
        while True:
            try:
                self.connection.do_handshake()
                await self._flush()
                certificate = self.connection.get_peer_certificate()
                if certificate is None:
                    if self.require_certificate:
                        raise SSL.Error("client certificate required")
                    return b""
                return certificate_der(certificate)
            except SSL.WantReadError:
                await self._flush()
                if not await self._feed():
                    raise ConnectionError("connection closed during TLS handshake")
            except SSL.WantWriteError:
                await self._flush()
            except SSL.Error:
                # A failed verification leaves the TLS alert in the memory BIO. Send it before
                # closing so clients can distinguish invalid authorization from a bare EOF.
                await self._flush()
                raise

    async def receive(self, size: int = 65536) -> bytes:
        while not self.closed:
            try:
                data = self.connection.recv(size)
                await self._flush()
                return data
            except SSL.WantReadError:
                await self._flush()
                if not await self._feed():
                    return b""
            except SSL.WantWriteError:
                await self._flush()
            except SSL.ZeroReturnError:
                return b""
        return b""

    async def send(self, data: bytes) -> None:
        offset = 0
        while offset < len(data) and not self.closed:
            try:
                offset += self.connection.send(data[offset:])
            except SSL.WantReadError:
                await self._flush()
                if not await self._feed():
                    raise ConnectionError("connection closed during TLS write")
            except SSL.WantWriteError:
                pass
            await self._flush()

    async def _feed(self) -> bool:
        data = await self.reader.read(65536)
        if not data:
            self.connection.bio_shutdown()
            return False
        self.connection.bio_write(data)
        return True

    async def _flush(self) -> None:
        wrote = False
        while True:
            try:
                data = self.connection.bio_read(65536)
            except SSL.WantReadError:
                break
            if not data:
                break
            self.writer.write(data)
            wrote = True
        if wrote:
            await self.writer.drain()

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.connection.shutdown()
            await self._flush()
        except (SSL.Error, ConnectionError, OSError):
            pass
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (ConnectionError, OSError):
            pass
