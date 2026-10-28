"""Tests for the local CA/leaf-certificate generation that backs the transparent proxy's HTTPS
MITM. Needs the cryptography package (the ``proxy`` extra); skipped otherwise.
"""
import socket
import ssl
import threading

import pytest

cryptography = pytest.importorskip("cryptography")

from agent_chaos.intercept.proxy_ca import ensure_ca  # noqa: E402


def test_ensure_ca_generates_and_caches(tmp_path):
    ca1 = ensure_ca(tmp_path)
    assert (tmp_path / "ca.pem").exists() and (tmp_path / "ca-key.pem").exists()
    ca2 = ensure_ca(tmp_path)
    assert ca1.cert.serial_number == ca2.cert.serial_number  # reloaded, not regenerated


def test_leaf_for_is_cached_per_host(tmp_path):
    ca = ensure_ca(tmp_path)
    cert1, _ = ca.leaf_for("example.com")
    cert2, _ = ca.leaf_for("example.com")
    assert cert1 == cert2
    cert3, _ = ca.leaf_for("other.com")
    assert cert3 != cert1


def test_leaf_cert_handshakes_against_trusting_client(tmp_path):
    """Real local TLS handshake: a server presents the generated leaf cert, a client that trusts
    only the generated CA connects successfully and sees the right subject."""
    ca = ensure_ca(tmp_path)
    cert_pem, key_pem = ca.leaf_for("example.com")
    cert_path = tmp_path / "leaf.pem"
    key_path = tmp_path / "leaf-key.pem"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(str(cert_path), str(key_path))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]

    def serve():
        conn, _ = sock.accept()
        tls_conn = server_ctx.wrap_socket(conn, server_side=True)
        tls_conn.recv(100)
        tls_conn.sendall(b"hello")
        tls_conn.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    client_ctx = ssl.create_default_context(cafile=str(ca.cert_path))
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw, \
         client_ctx.wrap_socket(raw, server_hostname="example.com") as tls:
        subject = dict(x[0] for x in tls.getpeercert()["subject"])
        assert subject["commonName"] == "example.com"
        tls.sendall(b"hi")
        assert tls.recv(100) == b"hello"
    thread.join(timeout=5)


def test_untrusting_client_rejects_the_leaf_cert(tmp_path):
    """A client that doesn't trust our CA must reject the handshake -- otherwise the MITM would
    work against anyone, which would make the whole allow-list safety model meaningless."""
    ca = ensure_ca(tmp_path)
    cert_pem, key_pem = ca.leaf_for("example.com")
    cert_path = tmp_path / "leaf.pem"
    key_path = tmp_path / "leaf-key.pem"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(str(cert_path), str(key_path))

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]

    def serve():
        try:
            conn, _ = sock.accept()
            server_ctx.wrap_socket(conn, server_side=True)
        except ssl.SSLError:
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()

    client_ctx = ssl.create_default_context()  # default trust store: does NOT trust our CA
    with pytest.raises(ssl.SSLError), socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        client_ctx.wrap_socket(raw, server_hostname="example.com")
    thread.join(timeout=5)
