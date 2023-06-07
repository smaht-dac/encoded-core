"""The type file for image collection."""

from snovault import (
    collection,
    load_schema,
)
from snovault.types.base import (
    Item,
)
from snovault.attachment import ItemWithAttachment


@collection(
    name='images',
    unique_key='image:filename',
    properties={
        'title': 'Image',
        'description': 'Listing of portal images',
    })
class Image(ItemWithAttachment):
    """Class image,defines accepted file types."""

    item_type = 'image'
    schema = load_schema('encoded_core:schemas/image.json')
    schema['properties']['attachment']['properties']['type']['enum'] = [
        'image/png',
        'image/jpeg',
        'image/gif',
    ]
    embedded_list = Item.embedded_list  # + lab_award_attribution_embed_list

    def unique_keys(self, properties):
        """smth."""
        keys = super(Image, self).unique_keys(properties)
        value = properties.get("attachment", {}).get("download")
        if value:
            keys.setdefault('image:filename', []).append(value)
        return keys
