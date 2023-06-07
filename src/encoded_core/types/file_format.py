from snovault import (
    calculated_property,
    collection,
    load_schema,
)
from snovault.attachment import ItemWithAttachment


@collection(
    name='file-formats',
    unique_key='file_format:file_format',
    properties={
        'title': 'File Formats',
        'description': 'Listing of file formats used by 4DN'
    }
)
class FileFormat(ItemWithAttachment):
    """The class to store information about 4DN file formats"""
    item_type = 'file_format'
    schema = load_schema('encoded_core:schemas/file_format.json')
    name_key = 'file_format'

    @calculated_property(schema={
        "title": "Display Title",
        "description": "File Format name or extension.",
        "type": "string"
    })
    def display_title(self, file_format):
        return file_format
