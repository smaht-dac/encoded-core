from snovault import collection, load_schema
from snovault.types.base import Item


@collection(
    name='higlass-view-configs',
    unique_key='higlass_view_config:name',
    properties={
        'title': 'HiGlass Displays',
        'description': 'Displays and view configurations for HiGlass',
    })
class HiglassViewConfig(Item):
    """
    Item type which contains a `view_config` property and other metadata.
    """

    item_type = 'higlass_view_config'
    schema = load_schema('encoded_core:schemas/higlass_view_config.json')
    embedded_list = []
    name_key = 'name'
