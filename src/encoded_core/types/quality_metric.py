"""The type file for the collection Quality Metric."""
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
from snovault import (
    abstract_collection,
    calculated_property,
    collection,
    load_schema,
)
# from pyramid.security import Authenticated
from snovault.types.base import (
    Item,
    # ALLOW_SUBMITTER_ADD,
    # lab_award_attribution_embed_list
)


# S3 URL identifier
S3_BUCKET_DOMAIN_SUFFIX = '.s3.amazonaws.com'


"""Schema for QCs' quality_metric_summary calculated property"""
QC_SUMMARY_SCHEMA = {
    "type": "array",
    "title": "Quality Metric Summary",
    "description": "Selected Quality Metrics for Summary",
    "exclude_from": ["FFedit-create"],
    "items": {
            "title": "Selected Quality Metric",
            "type": "object",
            "required": ["title", "value", "numberType"],
            "additionalProperties": False,
            "properties": {
                "title": {
                    "type": "string",
                    "title": "Title",
                    "description": "Title of the Quality Metric",
                },
                "title_tooltip": {
                    "type": "string",
                    "title": "Tooltip Title",
                    "description": "tooltip for the quality metric title to be displayed upon mouseover"
                },
                "sample": {
                    "type": "string",
                    "title": "Sample",
                    "description": "sample for which the quality metric was calculated"
                },
                "value": {
                    "type": "string",
                    "title": "Value",
                    "description": "value of the quality metric as a string"
                },
                "tooltip": {
                    "type": "string",
                    "title": "Tooltip",
                    "description": "tooltip for the quality metric to be displayed upon mouseover"
                },
                "numberType": {
                    "type": "string",
                    "title": "Type",
                    "description": "type of the quality metric",
                    "enum": ["string", "integer", "float", "percent"]
                }
            }
    }
}


"""OVERALL QAULITY SCORE INFO
All QC objects come with a field 'overall_quality_status', which is by default set to 'PASS'
For some qc object we don't have a current protocol to judge the overall quality based on the
fields in the qc item.
When there is a way to make this assesment, add this algorithm as a function to the corresponding
qc class, and update the value. If you implement it for a class with existing items, you will need
to trigger the update with empty patches."""


@abstract_collection(
    name='quality-metrics',
    properties={
        'title': 'Quality Metrics',
        'description': 'Listing of quality metrics',
    })
class QualityMetric(Item):
    """Quality metrics class."""
    item_type = 'quality_metric'
    base_types = ['QualityMetric'] + Item.base_types
    schema = load_schema('encoded_core:schemas/quality_metric.json')
    embedded_list = Item.embedded_list


@collection(
    name="quality-metrics-generic",
    properties={
        "title": "Generic Quality Metrics",
        "description": "Listing of Generic Quality Metrics",
    },
)
class QualityMetricGeneric(QualityMetric):
    item_type = "quality_metric_generic"
    schema = load_schema("encoded_core:schemas/quality_metric_generic.json")
    embedded_list = QualityMetric.embedded_list


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
