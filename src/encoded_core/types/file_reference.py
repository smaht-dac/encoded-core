from snovault import (
    collection,
    load_schema,
)
from .file import File


@collection(
    name='files-reference',
    properties={
        'title': 'Reference Files',
        'description': 'Listing of Reference Files',
        })
class FileReference(File):
    """Collection for individual reference files."""
    item_type = 'file_reference'
    schema = load_schema('encoded_core:schemas/file_reference.json')
    embedded_list = File.embedded_list
