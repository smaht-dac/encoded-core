"""Abstract collection for UserContent and sub-classes of StaticSection, HiglassViewConfig, etc."""

from snovault import (
    abstract_collection,
    calculated_property,
    collection,
    load_schema
)
from snovault.interfaces import STORAGE
from snovault.types.base import (
    Item,
)
import ipaddress
import os
import socket
import structlog
import urllib3
from urllib.parse import urlparse


log = structlog.getLogger(__name__)


@abstract_collection(
    name='user-contents',
    unique_key='user_content:name',
    properties={
        'title': "User Content Listing",
        'description': 'Listing of all types of content which may be created by people.',
    })
class UserContent(Item):
    item_type = 'user_content'
    base_types = ['UserContent'] + Item.base_types
    schema = load_schema('encoded_core:schemas/user_content.json')
    embedded_list = []

    @calculated_property(schema={
        "title": "Content",
        "description": "Content (unused)",
        "type": "string"
    })
    def content(self, request):
        return None

    @calculated_property(schema={
        "title": "File Type",
        "description": "Type of this Item (unused)",
        "type": "string"
    })
    def filetype(self, request):
        return None

    def _update(self, properties, sheets=None):
        if properties.get('name') is None and self.uuid is not None:
            properties['name'] = str(self.uuid)
        super(UserContent, self)._update(properties, sheets)

    @classmethod
    def create(cls, registry, uuid, properties, sheets=None):
        submitted_by_uuid = properties.get('submitted_by')
        institution_schema = cls.schema and cls.schema.get('properties', {}).get('institution')
        project_schema = cls.schema and cls.schema.get('properties', {}).get('project')
        if (
            not submitted_by_uuid                               # Shouldn't happen
            or (not institution_schema and not project_schema)            # If not applicable for Item type (shouldn't happen as props defined on UserContent schema)
            or ('institution' in properties or 'project' in properties)   # If values exist already - ideal case - occurs for general submission process(es)
        ):
            # Default for all other Items
            return super(UserContent, cls).create(registry, uuid, properties, sheets)

        submitted_by_item = registry[STORAGE].get_by_uuid(submitted_by_uuid)

        if submitted_by_item:
            # All linkTo property values, if present, are UUIDs
            if 'institution' not in properties and 'institution' in submitted_by_item.properties:
                # Use institution of submitter
                properties['institution'] = submitted_by_item.properties['institution']

            if 'project' not in properties and 'project' in submitted_by_item.properties:
                # Use project of submitter
                properties['project'] = submitted_by_item.properties['project']

        return super(UserContent, cls).create(registry, uuid, properties, sheets)


@collection(
    name='static-sections',
    unique_key='user_content:name',
    properties={
        'title': 'Static Sections',
        'description': 'Static Sections for the Portal',
    })
class StaticSection(UserContent):
    """The Software class that contains the software... used."""
    item_type = 'static_section'
    schema = load_schema('encoded_core:schemas/static_section.json')

    @calculated_property(schema={
        "title": "Content",
        "description": "Content for the page",
        "type": "string"
    })
    def content(self, request, body=None, file=None):

        if isinstance(body, str) or isinstance(body, dict) or isinstance(body, list):
            # Don't need to load in anything. We don't currently support dict/json body (via schema) but could in future.
            return body

        if isinstance(file, str):
            if file[0:4] == 'http' and '://' in file[4:8]:  # Remote File
                return get_remote_file_contents(file)
            else:                                           # Local File
                repo_root = os.path.abspath(os.path.dirname(os.path.realpath(__file__)) + "/../../..")
                file_path = os.path.abspath(repo_root + file)   # Go to top of repo, append file
                # Reject any 'file' value (e.g. containing '../') that would resolve
                # outside of the repo, so this can't be used to read arbitrary files
                # off of the server's filesystem.
                if os.path.commonpath([repo_root, file_path]) != repo_root:
                    log.error("StaticSection 'file' resolves outside of repo root, refusing to read", file=file)
                    return None
                return get_local_file_contents(file_path)

        return None

    @calculated_property(schema={
        "title": "File Type",
        "description": "Type of file used for content",
        "type": "string"
    })
    def filetype(self, request, body=None, file=None, options=None):
        if options and options.get('filetype') is not None:
            return options['filetype']
        if isinstance(body, str):
            return 'txt'
        if isinstance(body, dict) or isinstance(body, list):
            return 'json'
        if isinstance(file, str):
            filename_parts = file.split('.')
            if len(filename_parts) > 1:
                return filename_parts[len(filename_parts) - 1]
            else:
                return 'txt' # Default if no file extension.
        return None


def get_local_file_contents(filename, contentFilesLocation=None):
    if contentFilesLocation is None:
        full_file_path = filename
    else:
        full_file_path = contentFilesLocation + '/' + filename
    if not os.path.isfile(full_file_path):
        return None
    file = open(full_file_path, encoding="utf-8")
    output = file.read()
    file.close()
    return output


def _resolve_safe_remote_ip(hostname):
    """ Resolves hostname once and, if every address it resolves to is public
        (not private/loopback/link-local/etc), returns one of those IPs -
        so a StaticSection 'file' URL can't be used to make the server issue
        requests to internal services or the cloud metadata endpoint (SSRF).
        Returns None if the hostname doesn't resolve or resolves to anything
        non-public.
    """
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return None
    ips = []
    for _, _, _, _, sockaddr in addrinfos:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_reserved or ip.is_multicast or ip.is_unspecified
        ):
            return None
        ips.append(sockaddr[0])
    return ips[0] if ips else None


def get_remote_file_contents(uri):
    parsed = urlparse(uri)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        log.error("StaticSection 'file' is not a valid http(s) URL, refusing to fetch", uri=uri)
        return None
    ip = _resolve_safe_remote_ip(parsed.hostname)
    if ip is None:
        log.error("StaticSection 'file' resolves to a non-public host, refusing to fetch", uri=uri)
        return None
    # Connect directly to the IP address just validated above, rather than
    # letting the HTTP client re-resolve the hostname itself: if we let it
    # re-resolve, an attacker controlling DNS for the host could serve a
    # public IP for the check above and then a private/link-local one (e.g.
    # cloud metadata) for the actual connection moments later (DNS
    # rebinding), bypassing the check entirely. The Host header and TLS SNI
    # are still set to the original hostname so virtual-hosting and
    # certificate validation behave normally.
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    path = parsed.path or '/'
    if parsed.query:
        path = f'{path}?{parsed.query}'
    if parsed.scheme == 'https':
        pool = urllib3.HTTPSConnectionPool(
            ip, port=port, timeout=10, retries=False,
            assert_hostname=parsed.hostname, server_hostname=parsed.hostname,
        )
    else:
        pool = urllib3.HTTPConnectionPool(ip, port=port, timeout=10, retries=False)
    try:
        # Don't follow redirects: a host that passes the checks above could still
        # redirect to an internal/metadata address, bypassing them entirely. A flat
        # no-redirects policy is simpler than re-validating each hop and is
        # sufficient here.
        resp = pool.urlopen('GET', path, headers={'Host': parsed.hostname}, redirect=False)
    except urllib3.exceptions.HTTPError as e:
        log.error("StaticSection 'file' request failed", uri=uri, error=str(e))
        return None
    finally:
        pool.close()
    if 300 <= resp.status < 400:
        log.error("StaticSection 'file' returned a redirect, refusing to follow", uri=uri,
                  location=resp.headers.get('Location'))
        return None
    return resp.data.decode('utf-8', errors='replace')
