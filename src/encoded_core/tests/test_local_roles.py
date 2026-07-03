"""Unit tests for encoded_core.local_roles.

These exercise the pure principal-resolution logic (``local_principals`` and
``merged_local_principals``) plus the thin ``LocalRolesAuthorizationPolicy``
wrapper. No running server is required: the functions operate on any object
exposing ``__parent__`` (walked by ``pyramid.location.lineage``) together with
the optional ``__ac_local_roles__`` / ``__ac_local_roles_block__`` attributes.
"""
import pytest

from ..local_roles import (
    local_principals,
    merged_local_principals,
    LocalRolesAuthorizationPolicy,
)


class Location:
    """Minimal stand-in for a traversal context / resource.

    ``lineage`` walks the ``__parent__`` chain, so building a small linked list
    of these is enough to reproduce the traversal environment the real policy
    sees at request time.
    """

    def __init__(self, local_roles=None, block=False, parent=None):
        # Only set the dunder attributes when provided so that getattr(...,
        # default) branches in the production code are exercised realistically.
        if local_roles is not None:
            self.__ac_local_roles__ = local_roles
        if block:
            self.__ac_local_roles_block__ = True
        self.__parent__ = parent


# ---------------------------------------------------------------------------
# local_principals
# ---------------------------------------------------------------------------

def test_local_principals_no_local_roles_returns_input_unchanged():
    """With no local roles anywhere in the lineage, the input is returned as-is."""
    principals = ['user.alice', 'group.admins']
    context = Location()
    result = local_principals(context, principals)
    # Not merely equal -- the function should short-circuit and hand back the
    # very object it was given.
    assert result is principals


def test_local_principals_matching_principal_adds_roles():
    context = Location(local_roles={'user.alice': ['role.editor', 'role.viewer']})
    result = local_principals(context, ['user.alice'])
    assert set(result) == {'user.alice', 'role.editor', 'role.viewer'}


def test_local_principals_string_role_is_wrapped():
    """A non-iterable (string) role value must be treated as a single role."""
    context = Location(local_roles={'user.alice': 'role.solo'})
    result = local_principals(context, ['user.alice'])
    assert set(result) == {'user.alice', 'role.solo'}


def test_local_principals_callable_local_roles_is_invoked():
    context = Location(local_roles=lambda: {'user.bob': ['role.admin']})
    result = local_principals(context, ['user.bob'])
    assert set(result) == {'user.bob', 'role.admin'}


def test_local_principals_unmatched_principal_yields_no_extra_roles():
    """A principal absent from the mapping (KeyError branch) adds nothing."""
    context = Location(local_roles={'user.alice': ['role.editor']})
    principals = ['user.stranger']
    result = local_principals(context, principals)
    # No local principals accumulated -> original list handed back.
    assert result is principals


def test_local_principals_accumulates_across_lineage():
    grandparent = Location(local_roles={'user.alice': ['role.grand']})
    parent = Location(local_roles={'user.alice': ['role.parent']}, parent=grandparent)
    child = Location(local_roles={'user.alice': ['role.child']}, parent=parent)
    result = local_principals(child, ['user.alice'])
    assert set(result) == {'user.alice', 'role.child', 'role.parent', 'role.grand'}


def test_local_principals_block_stops_ancestor_traversal():
    """A blocking node contributes its own roles but hides its ancestors'."""
    parent = Location(local_roles={'user.alice': ['role.parent']})
    child = Location(local_roles={'user.alice': ['role.child']}, block=True, parent=parent)
    result = local_principals(child, ['user.alice'])
    # role.parent must NOT leak through the block.
    assert set(result) == {'user.alice', 'role.child'}


def test_local_principals_block_on_childless_node_hides_parent():
    parent = Location(local_roles={'user.alice': ['role.parent']})
    child = Location(block=True, parent=parent)
    result = local_principals(child, ['user.alice'])
    assert result == ['user.alice']


def test_local_principals_callable_returning_empty_is_skipped():
    """A callable that returns a falsy mapping hits the ``continue`` branch."""
    context = Location(local_roles=lambda: {})
    principals = ['user.alice']
    assert local_principals(context, principals) is principals


# ---------------------------------------------------------------------------
# merged_local_principals
# ---------------------------------------------------------------------------

def test_merged_local_principals_no_roles_returns_input():
    principals = ['role.editor']
    context = Location()
    assert merged_local_principals(context, principals) is principals


def test_merged_local_principals_intersecting_role_adds_principal():
    """If any granted role overlaps the mapped roles, the principal is added."""
    context = Location(local_roles={'user.alice': ['role.editor']})
    result = merged_local_principals(context, ['role.editor'])
    assert set(result) == {'role.editor', 'user.alice'}


def test_merged_local_principals_disjoint_roles_add_nothing():
    context = Location(local_roles={'user.alice': ['role.editor']})
    principals = ['role.viewer']
    result = merged_local_principals(context, principals)
    assert result is principals


def test_merged_local_principals_string_role_is_wrapped():
    context = Location(local_roles={'user.alice': 'role.editor'})
    result = merged_local_principals(context, ['role.editor'])
    assert set(result) == {'role.editor', 'user.alice'}


def test_merged_local_principals_callable_and_block():
    parent = Location(local_roles={'user.parent': ['role.shared']})
    child = Location(local_roles=lambda: {'user.child': ['role.shared']},
                     block=True, parent=parent)
    result = merged_local_principals(child, ['role.shared'])
    # Child's principal is added; parent is blocked out.
    assert set(result) == {'role.shared', 'user.child'}


# ---------------------------------------------------------------------------
# LocalRolesAuthorizationPolicy
# ---------------------------------------------------------------------------

class RecordingPolicy:
    """Fake wrapped policy that records how it was called."""

    def __init__(self, permits_result=True, allowed=None):
        self.permits_result = permits_result
        self.allowed = allowed if allowed is not None else ['role.editor']
        self.permits_calls = []
        self.allowed_calls = []

    def permits(self, context, principals, permission):
        self.permits_calls.append((context, list(principals), permission))
        return self.permits_result

    def principals_allowed_by_permission(self, context, permission):
        self.allowed_calls.append((context, permission))
        return list(self.allowed)


def test_policy_defaults_to_acl_authorization_policy():
    from pyramid.authorization import ACLAuthorizationPolicy
    policy = LocalRolesAuthorizationPolicy()
    assert isinstance(policy.wrapped_policy, ACLAuthorizationPolicy)


def test_policy_uses_supplied_wrapped_policy():
    wrapped = RecordingPolicy()
    policy = LocalRolesAuthorizationPolicy(wrapped_policy=wrapped)
    assert policy.wrapped_policy is wrapped


def test_policy_permits_expands_principals_before_delegating():
    wrapped = RecordingPolicy(permits_result=True)
    policy = LocalRolesAuthorizationPolicy(wrapped_policy=wrapped)
    context = Location(local_roles={'user.alice': ['role.editor']})

    assert policy.permits(context, ['user.alice'], 'edit') is True
    # The wrapped policy must have seen the expanded principal set, not the raw
    # ['user.alice'] passed in.
    _, seen_principals, permission = wrapped.permits_calls[0]
    assert permission == 'edit'
    assert set(seen_principals) == {'user.alice', 'role.editor'}


def test_policy_principals_allowed_merges_local_principals():
    wrapped = RecordingPolicy(allowed=['role.editor'])
    policy = LocalRolesAuthorizationPolicy(wrapped_policy=wrapped)
    context = Location(local_roles={'user.alice': ['role.editor']})

    result = policy.principals_allowed_by_permission(context, 'edit')
    assert wrapped.allowed_calls == [(context, 'edit')]
    # merged_local_principals should fold user.alice in alongside role.editor.
    assert set(result) == {'role.editor', 'user.alice'}
