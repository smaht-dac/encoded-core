"""
The type file for the collection Pages.  Which is used for static pages on the portal
"""
from snovault import collection, load_schema
from snovault.types.base import Item


@collection(
    name='pages',
    unique_key='page:name',
    properties={
        'title': 'Pages',
        'description': 'Static Pages for the Portal',
    })
class Page(Item):
    """Links to StaticSections"""
    item_type = 'page'
    schema = load_schema('encoded_core:schemas/page.json')
    embedded_list = ['content.*']

    class Collection(Item.Collection):
        pass


# XXX: Legacy code... should not touch it for now... - Will 27 May 2023
for field in ['display_title', 'name', 'description', 'content.name']:
    Page.embedded_list = Page.embedded_list + [
        'children.' + field, 'children.children.' + field, 'children.children.children.' + field
    ]
