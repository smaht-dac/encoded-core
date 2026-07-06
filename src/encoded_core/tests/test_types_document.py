"""Unit tests for encoded_core.types.document.

``mimetypes_are_equal`` only reads the class-level ``mimetype_map``, so it can
be exercised on a bare instance without standing up the app / attachment
machinery.
"""
import pytest

from ..types.document import Document


@pytest.fixture
def document():
    # __new__ avoids Item.__init__ (which needs a registry/model); the method
    # under test only touches the class attribute ``mimetype_map``.
    return Document.__new__(Document)


def test_two_text_types_are_equal(document):
    # Any two text/* mimetypes are considered equal regardless of subtype.
    assert document.mimetypes_are_equal('text/plain', 'text/html') is True


def test_identical_mimetypes_are_equal(document):
    assert document.mimetypes_are_equal('application/pdf', 'application/pdf') is True


def test_mapped_mimetype_pair_is_equal(document):
    # application/proband+xml maps to text/plain in mimetype_map.
    assert document.mimetypes_are_equal('application/proband+xml', 'text/plain') is True


def test_mapping_is_directional(document):
    # The map is consulted as map[m1] -> [m2, ...]. Only the forward direction
    # (proband+xml -> text/plain) matches; the reverse falls through the map
    # lookup and the m1 == m2 fallback, so it is NOT equal.
    assert document.mimetypes_are_equal('text/plain', 'application/proband+xml') is False


def test_unrelated_mimetypes_not_equal(document):
    assert document.mimetypes_are_equal('application/pdf', 'image/png') is False


def test_text_and_nontext_not_equal_unless_mapped(document):
    assert document.mimetypes_are_equal('text/plain', 'application/pdf') is False
