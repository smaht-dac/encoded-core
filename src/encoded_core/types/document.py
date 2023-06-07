from snovault import (
    calculated_property,
    collection,
    load_schema,
)
from snovault.attachment import ItemWithAttachment
from snovault.types.base import (
    Item
)


@collection(
    name='documents',
    properties={
        'title': 'Documents',
        'description': 'Listing of Documents',
    })
class Document(ItemWithAttachment):
    """Document class."""

    item_type = 'document'
    schema = load_schema('encoded_core:schemas/document.json')
    embedded_list = []
    mimetype_map = {'application/proband+xml': ['text/plain']}

    def mimetypes_are_equal(self, m1, m2):
        """ Checks that mime_type m1 and m2 are equal """
        major1 = m1.split('/')[0]
        major2 = m2.split('/')[0]
        if major1 == 'text' and major2 == 'text':
            return True
        if m1 in self.mimetype_map and m2 in self.mimetype_map[m1]:
            return True
        return m1 == m2

    @calculated_property(schema={
        "title": "Display Title",
        "description": "Document filename, if available.",
        "type": "string"
    })
    def display_title(self, attachment=None):
        if attachment:
            return attachment.get('download')
        return Item.display_title(self)

    class Collection(Item.Collection):
        pass
