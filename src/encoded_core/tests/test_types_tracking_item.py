"""Unit tests for the TrackingItem.display_title calculated property.

``display_title`` does not use instance state, so it can be exercised on a bare
instance. It has several branches (tracking type + optional date/analytics)
that the integration tests do not cover directly.
"""
import pytest

from ..types.tracking_item import TrackingItem


@pytest.fixture
def tracking_item():
    return TrackingItem.__new__(TrackingItem)


def test_google_analytics_with_for_date(tracking_item):
    result = tracking_item.display_title(
        'google_analytics',
        date_created='2020-01-02T03:04:05',
        google_analytics={'for_date': '2020-01-01'},
    )
    assert result == 'Google Analytics for 2020-01-01'


def test_google_analytics_without_for_date(tracking_item):
    result = tracking_item.display_title(
        'google_analytics',
        date_created='2020-01-02T03:04:05',
        google_analytics={},
    )
    assert result == 'Google Analytics Item'


def test_google_analytics_missing_analytics_block(tracking_item):
    # google_analytics is None -> for_date stays None -> generic GA title.
    result = tracking_item.display_title('google_analytics',
                                         date_created='2020-01-02T03:04:05')
    assert result == 'Google Analytics Item'


def test_download_tracking_with_date_truncates_to_day(tracking_item):
    # date_created is sliced to its first 10 chars (YYYY-MM-DD).
    result = tracking_item.display_title('download_tracking',
                                         date_created='2020-01-02T03:04:05')
    assert result == 'Download Tracking Item from 2020-01-02'


def test_download_tracking_without_date(tracking_item):
    result = tracking_item.display_title('download_tracking', date_created=None)
    assert result == 'Download Tracking Item'


def test_unknown_tracking_type_with_date(tracking_item):
    result = tracking_item.display_title('other',
                                         date_created='2021-12-31T23:59:59')
    assert result == 'Tracking Item from 2021-12-31'


def test_unknown_tracking_type_without_date(tracking_item):
    result = tracking_item.display_title('other', date_created=None)
    assert result == 'Tracking Item'
