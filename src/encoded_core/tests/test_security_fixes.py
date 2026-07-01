"""
End-to-end style tests for the SSRF/LFI, S3 confused-deputy, and Range-DoS
fixes applied to StaticSection's file content loading (types/user_content.py),
QualityMetric's @@download (qc_views.py), and File's @@download (file_views.py).

These tests exercise the vulnerable code paths directly against real network
sockets and streams (rather than only asserting on mocked calls) so that a
regression that reopens SSRF/LFI/DoS would actually be observed here.
"""
import http.server
import os
import threading

import pytest

from ..file_views import _iter_and_close
from ..qc_views import parse_qc_s3_url
from ..types.user_content import StaticSection, get_remote_file_contents


# ---------------------------------------------------------------------------
# StaticSection local 'file' path traversal (LFI) - types/user_content.py
# ---------------------------------------------------------------------------

def test_static_section_rejects_path_traversal_outside_repo():
    """ A 'file' value that escapes the repo root (e.g. '../../../../etc/passwd')
        must not be read from disk. """
    content = StaticSection.content(None, request=None, file='/../../../../../../../../etc/passwd')
    assert content is None


def test_static_section_allows_legitimate_file_within_repo():
    """ Sanity check that the traversal guard doesn't break normal repo-relative
        file loading (existing behavior should be preserved). """
    content = StaticSection.content(None, request=None, file='/README.rst')
    assert content is not None
    assert len(content) > 0


# ---------------------------------------------------------------------------
# StaticSection remote 'file' SSRF - types/user_content.py
# ---------------------------------------------------------------------------

def test_get_remote_file_contents_blocks_loopback_host():
    """ Real (unmocked) DNS resolution of 'localhost' must be rejected before
        any request is issued - this is the core SSRF guard. """
    assert get_remote_file_contents('http://localhost:1/should-not-be-fetched') is None


def test_get_remote_file_contents_blocks_loopback_ip_literal():
    assert get_remote_file_contents('http://127.0.0.1:1/should-not-be-fetched') is None


def test_get_remote_file_contents_rejects_non_http_scheme():
    assert get_remote_file_contents('file:///etc/passwd') is None


def test_get_remote_file_contents_rejects_malformed_url():
    # Invalid IPv6-literal-like host that urlparse/hostname parsing chokes on.
    assert get_remote_file_contents('http://[::1') is None


def test_get_remote_file_contents_rejects_malformed_port():
    assert get_remote_file_contents('http://example.com:not-a-port/') is None


class _EchoOr302Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/redirect-me':
            self.send_response(302)
            self.send_header('Location', 'http://169.254.169.254/latest/meta-data/')
            self.end_headers()
        else:
            body = b'safe local content'
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)


@pytest.fixture
def local_http_server():
    server = http.server.HTTPServer(('127.0.0.1', 0), _EchoOr302Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_get_remote_file_contents_fetches_once_ssrf_check_bypassed_for_test_server(
        local_http_server, monkeypatch):
    """ The IP-safety check itself is proven above (real DNS to localhost is
        blocked). Here we bypass *only* that check - since our test HTTP
        server necessarily lives on loopback - to prove the rest of the
        pipeline (direct-IP connect, Host header, response decoding) still
        successfully returns real content for a normal 200 response. """
    port = local_http_server.server_address[1]
    monkeypatch.setattr(
        'encoded_core.types.user_content._resolve_safe_remote_ip',
        lambda hostname: '127.0.0.1',
    )
    content = get_remote_file_contents(f'http://example.com:{port}/ok')
    assert content == 'safe local content'


def test_get_remote_file_contents_does_not_follow_redirects(local_http_server, monkeypatch):
    """ Even once a host passes the SSRF check, a redirect response (which could
        point anywhere, e.g. the cloud metadata endpoint) must not be followed. """
    port = local_http_server.server_address[1]
    monkeypatch.setattr(
        'encoded_core.types.user_content._resolve_safe_remote_ip',
        lambda hostname: '127.0.0.1',
    )
    content = get_remote_file_contents(f'http://example.com:{port}/redirect-me')
    assert content is None


# ---------------------------------------------------------------------------
# QualityMetric @@download S3 confused-deputy SSRF - qc_views.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('url,expected', [
    (
        'https://s3.amazonaws.com/cgap-devtest-bucket/GAPFI1HVXJ5F/fastqc_report.html',
        ('cgap-devtest-bucket', 'GAPFI1HVXJ5F/fastqc_report.html'),
    ),
    (
        'https://cgap-devtest-main-application-tibanna-logs.s3.amazonaws.com/41c2fJDQcLk3.metrics/metrics.html',
        ('cgap-devtest-main-application-tibanna-logs', '41c2fJDQcLk3.metrics/metrics.html'),
    ),
])
def test_parse_qc_s3_url_accepts_legitimate_s3_urls(url, expected):
    assert parse_qc_s3_url(url) == expected


@pytest.mark.parametrize('url', [
    # Arbitrary attacker-controlled host - not S3 at all.
    'https://attacker.example.com/bucket/key',
    # Confused-deputy attempt: bucket name crafted to make the *path*, not the
    # actual host, look like an S3 domain.
    'https://attacker.example.com/s3.amazonaws.com/key',
    # Hostname that merely ends with the S3 suffix as a subdomain suffix trick.
    'https://s3.amazonaws.com.attacker.example.com/bucket/key',
])
def test_parse_qc_s3_url_rejects_non_s3_hosts(url):
    with pytest.raises(ValueError):
        parse_qc_s3_url(url)


# ---------------------------------------------------------------------------
# File @@download Range-request memory exhaustion (DoS) - file_views.py
# ---------------------------------------------------------------------------

class _RecordingStream:
    """ Minimal stand-in for the boto3 StreamingBody returned by S3 get_object. """

    def __init__(self, data, chunk_size_served=4):
        self._remaining = data
        self._chunk_size_served = chunk_size_served
        self.read_calls = []
        self.closed = False

    def read(self, size):
        self.read_calls.append(size)
        chunk, self._remaining = (
            self._remaining[:self._chunk_size_served], self._remaining[self._chunk_size_served:]
        )
        return chunk

    def close(self):
        self.closed = True


def test_iter_and_close_streams_in_chunks_instead_of_buffering_whole_file():
    data = os.urandom(1024 * 1024 * 3)  # 3MB - larger than a single 1MB chunk
    stream = _RecordingStream(data, chunk_size_served=1024 * 1024)

    collected = b''.join(_iter_and_close(stream))

    assert collected == data
    # Proves the fix reads incrementally (multiple .read() calls) rather than
    # a single .read() of the whole body, which is what caused the memory
    # exhaustion for large ranged files.
    assert len(stream.read_calls) > 1
    assert stream.closed is True


def test_iter_and_close_closes_stream_on_early_client_disconnect():
    """ If the consumer (e.g. a WSGI server whose client aborted a Range
        download) stops iterating early, the S3 stream must still be closed
        so the connection is released back to the pool instead of leaking. """
    data = os.urandom(1024 * 1024 * 3)
    stream = _RecordingStream(data, chunk_size_served=1024 * 1024)

    gen = _iter_and_close(stream)
    next(gen)  # consume exactly one chunk, then abandon the generator
    gen.close()

    assert stream.closed is True
