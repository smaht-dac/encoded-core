"""The type file for the collection Quality Metric."""
from snovault import (
    abstract_collection,
    collection,
    load_schema,
)
from snovault.types.base import (
    Item
)


"""OVERALL QAULITY SCORE INFO
All QC objects come with a field 'overall_quality_status', which is by default set to 'PASS'
For some qc object we don't have a current protocol to judge the overall quality based on the
fields in the qc item.
When there is a way to make this assesment, add this algorithm as a function to the corresponding
qc class, and update the value. If you implement it for a class with existing items, you will need
to trigger the update with empty patches."""


# NOTE: past version sof quality metrics had many schemas, but now we use 'QualityMetricGeneric' as
# the general way of implementing QCs - should cover 90% of cases, if new types are needed they should
# extend quality metric

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
