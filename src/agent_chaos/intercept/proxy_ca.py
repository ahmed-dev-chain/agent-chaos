"""Local certificate authority for the transparent proxy's HTTPS MITM.

Needs the ``cryptography`` package (the ``proxy`` extra): Python's stdlib can generate TLS
*contexts* but not certificates. Everything else in agent-chaos stays zero-dependency; only
``intercept/proxy.py`` and this module need it.
"""
from __future__ import annotations

import datetime
import ipaddress
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CA_VALID_DAYS = 3650
LEAF_VALID_DAYS = 825  # under the ~2-year max most clients still accept for leaf certs


class CA:
    """A root CA key pair, plus on-demand leaf certificates signed by it."""

    def __init__(self, cert: x509.Certificate, key: rsa.RSAPrivateKey, cert_path: Path):
        self.cert = cert
        self.key = key
        self.cert_path = cert_path
        self._leaf_cache: dict[str, tuple[bytes, bytes]] = {}

    def leaf_for(self, host: str) -> tuple[bytes, bytes]:
        """Return ``(cert_pem, key_pem)`` for ``host``, generating and caching it on first use."""
        if host not in self._leaf_cache:
            self._leaf_cache[host] = _make_leaf(host, self.cert, self.key)
        return self._leaf_cache[host]


def ensure_ca(directory: str | Path | None = None) -> CA:
    """Load the cached root CA from ``directory``, generating one on first use.

    Defaults to ``~/.agent_chaos/proxy``. The private key is written with user-only permissions
    (``0o600``): anyone who obtains it can mint certificates this CA's trusters will accept for
    any host, so it must never be shared or committed.
    """
    directory = Path(directory) if directory else Path.home() / ".agent_chaos" / "proxy"
    directory.mkdir(parents=True, exist_ok=True)
    cert_path = directory / "ca.pem"
    key_path = directory / "ca-key.pem"

    if cert_path.exists() and key_path.exists():
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        return CA(cert, key, cert_path)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "agent-chaos local proxy CA")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=CA_VALID_DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )

    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass  # best-effort: not all filesystems (e.g. some Windows setups) honor POSIX bits

    return CA(cert, key, cert_path)


def _make_leaf(host: str, ca_cert: x509.Certificate, ca_key: rsa.RSAPrivateKey) -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.datetime.now(datetime.timezone.utc)

    try:
        san: x509.GeneralName = x509.IPAddress(ipaddress.ip_address(host))
    except ValueError:
        san = x509.DNSName(host)

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=LEAF_VALID_DAYS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([san]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return cert_pem, key_pem
