"""Unit tests for the pure helpers in encoded_core.page_views.

The static-page endpoint itself needs a running app (DB traversal, embeds), but
the tree-shaping helpers it relies on are pure functions over plain dicts and
are the parts most prone to off-by-one / branch bugs. Those are covered here
directly, no server required.
"""
import pytest

from pyramid.httpexceptions import (
    HTTPMovedPermanently,
    HTTPFound,
    HTTPSeeOther,
    HTTPTemporaryRedirect,
)

from ..page_views import (
    get_pyramid_http_exception_for_redirect_code,
    generate_at_type_for_page,
    cleanup_page_tree,
    add_sibling_parent_relations_to_tree,
)


# ---------------------------------------------------------------------------
# get_pyramid_http_exception_for_redirect_code
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('code, expected', [
    (301, HTTPMovedPermanently),
    (302, HTTPFound),
    (303, HTTPSeeOther),
    (307, HTTPTemporaryRedirect),
])
def test_redirect_code_maps_to_exception(code, expected):
    assert get_pyramid_http_exception_for_redirect_code(code) is expected


def test_redirect_code_unknown_raises_keyerror():
    # 308 is deliberately not in the mapping.
    with pytest.raises(KeyError):
        get_pyramid_http_exception_for_redirect_code(308)


# ---------------------------------------------------------------------------
# generate_at_type_for_page
# ---------------------------------------------------------------------------

def test_at_type_single_level_leaf():
    result = generate_at_type_for_page({'@id': '/about'})
    assert result == ['AboutPage', 'StaticPage', 'Portal']


def test_at_type_nested_builds_descending_prefixes():
    # Two path components produce the full-prefix type then the shorter prefix.
    result = generate_at_type_for_page({'@id': '/help/user-guide'})
    assert result == ['HelpUser-guidePage', 'HelpPage', 'StaticPage', 'Portal']


def test_at_type_root_has_no_page_prefixes():
    # '/' splits to no non-empty components -> only the trailing common types.
    result = generate_at_type_for_page({'@id': '/'})
    assert result == ['StaticPage', 'Portal']


def test_at_type_with_children_inserts_directory_page():
    result = generate_at_type_for_page({'@id': '/help', 'children': [{'name': 'x'}]})
    assert result == ['HelpPage', 'DirectoryPage', 'StaticPage', 'Portal']


def test_at_type_three_levels_order():
    result = generate_at_type_for_page({'@id': '/a/b/c'})
    assert result == ['ABCPage', 'ABPage', 'APage', 'StaticPage', 'Portal']


# ---------------------------------------------------------------------------
# cleanup_page_tree
# ---------------------------------------------------------------------------

def test_cleanup_leaf_marks_is_leaf_and_drops_empty_children():
    node = {'name': 'about', 'children': []}
    cleanup_page_tree(node)
    assert node['@id'] == '/about'
    assert node['@type'] == ['AboutPage', 'StaticPage', 'Portal']
    assert node['is_leaf'] is True
    assert 'children' not in node


def test_cleanup_prunes_children_with_errors():
    node = {
        'name': 'top',
        'children': [
            {'name': 'top/ok', 'children': [], 'content': [{'x': 1}],
             'uuid': 'u1', 'display_title': 'OK'},
            {'name': 'top/bad', 'error': 'not found'},
        ],
    }
    cleanup_page_tree(node)
    remaining_names = [c['name'] for c in node['children']]
    assert remaining_names == ['top/ok']


def test_cleanup_drops_empty_leaf_children_without_content():
    # A child that is a leaf (no children) *and* has no content should be
    # pruned by the second filter pass.
    node = {
        'name': 'top',
        'children': [
            {'name': 'top/empty', 'children': [], 'uuid': 'u', 'display_title': 'E'},
        ],
    }
    cleanup_page_tree(node)
    assert node['children'] == []


def test_cleanup_sets_sibling_position_and_length():
    node = {
        'name': 'top',
        'children': [
            {'name': 'top/a', 'children': [], 'content': [1], 'uuid': 'a', 'display_title': 'A'},
            {'name': 'top/b', 'children': [], 'content': [1], 'uuid': 'b', 'display_title': 'B'},
        ],
    }
    cleanup_page_tree(node)
    assert len(node['children']) == 2
    for idx, child in enumerate(node['children']):
        assert child['sibling_length'] == 2
        assert child['sibling_position'] == idx


# ---------------------------------------------------------------------------
# add_sibling_parent_relations_to_tree
# ---------------------------------------------------------------------------

def test_sibling_relations_wire_previous_next_and_parent():
    tree = {
        'name': 'root',
        'children': [
            {'name': 'a', 'children': []},
            {'name': 'b', 'children': []},
            {'name': 'c', 'children': []},
        ],
    }
    out = add_sibling_parent_relations_to_tree(tree)
    first, mid, last = out['children']

    # First child: has a next, no previous.
    assert 'previous' not in first
    assert first['next']['name'] == 'b'

    # Middle child: both neighbours plus parent.
    assert mid['previous']['name'] == 'a'
    assert mid['next']['name'] == 'c'
    assert mid['parent']['name'] == 'root'

    # Last child: has a previous, no next.
    assert last['previous']['name'] == 'b'
    assert 'next' not in last


def test_sibling_relations_leaf_returns_node_unchanged():
    leaf = {'name': 'solo', 'children': []}
    out = add_sibling_parent_relations_to_tree(leaf)
    assert out is leaf


def test_sibling_relations_does_not_mutate_input():
    tree = {'name': 'root', 'children': [{'name': 'a', 'children': []}]}
    add_sibling_parent_relations_to_tree(tree)
    # Original child dict must not have gained a 'parent' back-reference; the
    # function copies nodes before wiring relations.
    assert 'parent' not in tree['children'][0]


def test_sibling_relations_recurses_into_grandchildren():
    tree = {
        'name': 'root',
        'children': [
            {
                'name': 'parent',
                'children': [
                    {'name': 'g1', 'children': []},
                    {'name': 'g2', 'children': []},
                ],
            },
        ],
    }
    out = add_sibling_parent_relations_to_tree(tree)
    grandchildren = out['children'][0]['children']
    assert grandchildren[0]['next']['name'] == 'g2'
    assert grandchildren[1]['previous']['name'] == 'g1'
    assert grandchildren[0]['parent']['name'] == 'parent'
