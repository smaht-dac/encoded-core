import datetime
import pytz
import re
from urllib.parse import parse_qs, urlparse
from pyramid.settings import asbool
from pyramid.view import view_config
from pyramid.httpexceptions import (
    HTTPTemporaryRedirect,
    HTTPNotFound,
)
from snovault.util import build_s3_presigned_get_url
from .types.quality_metric import QualityMetric


def includeme(config):
    config.scan(__name__)


# S3 URL identifier
S3_BUCKET_DOMAIN_SUFFIX = '.s3.amazonaws.com'

# Matches virtual-hosted-style (<bucket>.s3[.<region>].amazonaws.com) and
# path-style (s3[.<region>].amazonaws.com) S3 endpoint hostnames only. Used to
# make sure a QualityMetric's stored 'url' actually points at S3 before we
# hand its bucket/key off to build_s3_presigned_get_url - see parse_qc_s3_url.
S3_HOSTNAME_PATTERN = re.compile(
    r'^([a-z0-9][a-z0-9.\-]*\.)?s3[.\-]([a-z0-9\-]+\.)?amazonaws\.com$', re.IGNORECASE
)


def parse_qc_s3_url(url):
    """ Parses the given s3 URL into its pair of bucket, key
        Note that this function works the way it does because of how these
        urls end up in our database. Eventually we should clean this up.
        TODO: use version in utils
        Format:
            https://s3.amazonaws.com/cgap-devtest-main-application-cgap-devtest-wfout/GAPFI1HVXJ5F/fastqc_report.html
            https://cgap-devtest-main-application-tibanna-logs.s3.amazonaws.com/41c2fJDQcLk3.metrics/metrics.html

        Raises ValueError if the url does not point at an S3 endpoint - this
        value comes from stored item metadata and is used to build a
        presigned S3 URL using the application's own AWS credentials, so it
        must not be allowed to point at an arbitrary host (SSRF).
    """
    parsed_url = urlparse(url)
    hostname = parsed_url.hostname or ''
    if not S3_HOSTNAME_PATTERN.match(hostname):
        raise ValueError('QualityMetric url does not point to an S3 location: %s' % url)
    if hostname.endswith(S3_BUCKET_DOMAIN_SUFFIX):
        bucket = hostname[:-len(S3_BUCKET_DOMAIN_SUFFIX)]
        key = parsed_url.path.lstrip('/')
    else:
        [bucket, key] = parsed_url.path.lstrip('/').split('/', 1)
    return bucket, key


@view_config(name='download', context=QualityMetric, request_method='GET',
             permission='view', subpath_segments=[0, 1])
def download(context, request):
    """ Downloads the quality metric report from S3 """
    properties = context.upgrade_properties()
    if 'url' not in properties:
        raise HTTPNotFound(properties)
    # parse direct s3 link
    # format: https://s3.amazonaws.com/cgap-devtest-main-application-cgap-devtest-wfout/GAPFI1HVXJ5F/fastqc_report.html
    # or: https://cgap-devtest-main-application-tibanna-logs.s3.amazonaws.com/41c2fJDQcLk3.metrics/metrics.html
    try:
        bucket, key = parse_qc_s3_url(properties['url'])
    except ValueError:
        raise HTTPNotFound(properties)
    params_to_get_obj = {
        'Bucket': bucket,
        'Key': key
    }
    location = build_s3_presigned_get_url(params=params_to_get_obj)

    if asbool(request.params.get('soft')):
        expires = int(parse_qs(urlparse(location).query)['Expires'][0])
        return {
            '@type': ['SoftRedirect'],
            'location': location,
            'expires': datetime.datetime.fromtimestamp(expires, pytz.utc).isoformat(),
        }

    # 307 redirect specifies to keep original method
    raise HTTPTemporaryRedirect(location=location)  # 307