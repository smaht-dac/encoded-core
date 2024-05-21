import pytest
from ..file_views import extract_bucket_and_key


@pytest.fixture
def test_processed_file(testapp, file_formats):
    data = {
        "uuid": "cca15caa-bc11-4a6a-8998-ea0c69df8b9d",
        "file_format": "bam",
        "accession": "TSTFI2115172",
        "file_size": 5000,
        "md5sum": "211e09ebf240c7256747d10e24cb99fd"
    }
    testapp.post_json('/FileProcessed', data, status=201)


@pytest.mark.parametrize('url, expected', [
    ('https://test-bucket.s3.com/file.bam',
     ('test-bucket', 'file.bam')),
    ('http://test-bucket.s3.amazonaws.com/file.bam',
     ('test-bucket', 'file.bam')),
    ('https://test-bucket.s3.amazonaws.com/file.bam',
     ('test-bucket', 'file.bam')),
    ('https://smaht-unit-testing-wfout.s3.amazonaws.com/cca15caa-bc11-4a6a-8998-ea0c69df8b9d/TSTFI0211073.bam',
     ('smaht-unit-testing-wfout', 'cca15caa-bc11-4a6a-8998-ea0c69df8b9d/TSTFI0211073.bam'))
])
def test_extract_bucket_and_key(url, expected):
    """ Tests the helper function for pulling bucket/key information from a URL """
    bucket, key = extract_bucket_and_key(url)
    assert bucket == expected[0]
    assert key == expected[1]


def _test_uri_get(testapp, uri):
    """ Helper functions that tests that we can get back download creds via GET """
    if '@@download_cli' not in uri:
        uri = f'{uri}@@download_cli'
    res = testapp.get(uri).json['download_credentials']
    assert 'AccessKeyId' in res
    assert 'ASIA' in res['AccessKeyId']  # only real check we can do that this key is real
    assert 'SecretAccessKey' in res
    assert 'SessionToken' in res


def test_download_cli_get(test_processed_file, testapp):
    """ Basic tests on the base data model """
    item = testapp.get('/files-processed/cca15caa-bc11-4a6a-8998-ea0c69df8b9d/').json
    atid, uuid = item['@id'], item['uuid']
    # test failure cases
    testapp.get(f'/blah/download_cli/', status=404)
    testapp.get(f'//download_cli/', status=404)
    # test with @@download
    _test_uri_get(testapp, f'{atid}')
    _test_uri_get(testapp, f'/{uuid}/')
    # test without @@download
    _test_uri_get(testapp, f'{atid}')
    _test_uri_get(testapp, f'/{uuid}/')
