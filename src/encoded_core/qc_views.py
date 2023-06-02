import datetime
import pytz
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


def parse_qc_s3_url(url):
    """ Parses the given s3 URL into its pair of bucket, key
        Note that this function works the way it does because of how these
        urls end up in our database. Eventually we should clean this up.
        TODO: use version in utils
        Format:
            https://s3.amazonaws.com/cgap-devtest-main-application-cgap-devtest-wfout/GAPFI1HVXJ5F/fastqc_report.html
            https://cgap-devtest-main-application-tibanna-logs.s3.amazonaws.com/41c2fJDQcLk3.metrics/metrics.html
    """
    parsed_url = urlparse(url)
    if parsed_url.hostname.endswith(S3_BUCKET_DOMAIN_SUFFIX):
        bucket = parsed_url.hostname[:-len(S3_BUCKET_DOMAIN_SUFFIX)]
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
    bucket, key = parse_qc_s3_url(properties['url'])
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