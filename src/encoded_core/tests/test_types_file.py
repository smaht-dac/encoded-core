import pytest

from unittest import mock
from ..types import file as tf
from ..types.file import external_creds


@pytest.fixture
def file(testapp, file_formats):
    item = {
        'file_format': file_formats.get('fastq').get('uuid'),
        'md5sum': '00000000000000000000000000000000',
        'filename': 'my.fastq.gz',
        'status': 'uploaded',
    }
    res = testapp.post_json('/file_fastq', item)
    return res.json['@graph'][0]


def test_external_creds():

    with mock.patch.object(tf, 'boto3', autospec=True):

        ret = external_creds('test-wfout-bucket', 'test-key', 'name')
        assert ret['key'] == 'test-key'
        assert ret['bucket'] == 'test-wfout-bucket'
        assert ret['service'] == 's3'
        assert 'upload_credentials' in ret.keys()


def test_external_creds_assume_role(monkeypatch):
    """ Confirms external_creds derives scoped S3 credentials via sts:AssumeRole
        (rather than the retired sts:GetFederationToken), sourcing the role ARN
        from S3_UPLOAD_ROLE_ARN and mapping the AssumeRole response fields correctly.
    """
    monkeypatch.delenv('IDENTITY', raising=False)
    monkeypatch.setenv('S3_UPLOAD_ROLE_ARN', 'arn:aws:iam::123456789012:role/test-upload-role')

    fake_sts_response = {
        'Credentials': {
            'AccessKeyId': 'FAKEACCESSKEY',
            'SecretAccessKey': 'FAKESECRETKEY',
            'SessionToken': 'FAKESESSIONTOKEN',
            'Expiration': '2024-01-01T00:00:00Z',
        },
        'AssumedRoleUser': {
            'Arn': 'arn:aws:sts::123456789012:assumed-role/test-upload-role/name',
            'AssumedRoleId': 'AROAEXAMPLE123:name',
        },
        'ResponseMetadata': {'RequestId': 'fake-request-id'},
    }
    mock_sts_client = mock.Mock()
    mock_sts_client.assume_role.return_value = fake_sts_response

    with mock.patch.object(tf, 'boto3') as mock_boto3:
        mock_boto3.client.return_value = mock_sts_client
        ret = external_creds('test-wfout-bucket', 'test-key', 'name')

    mock_boto3.client.assert_called_once_with('sts')
    _, call_kwargs = mock_sts_client.assume_role.call_args
    assert call_kwargs['RoleArn'] == 'arn:aws:iam::123456789012:role/test-upload-role'
    assert call_kwargs['RoleSessionName'] == 'name'

    creds = ret['upload_credentials']
    assert creds['federated_user_arn'] == fake_sts_response['AssumedRoleUser']['Arn']
    assert creds['federated_user_id'] == fake_sts_response['AssumedRoleUser']['AssumedRoleId']
    assert creds['request_id'] == 'fake-request-id'


@pytest.fixture
def processed_file_data(file_formats):
    return {
        'file_format': file_formats.get('bam').get('uuid'),
    }


def test_validate_produced_from_files_no_produced_by_and_filename_no_filename(
        testapp, processed_file_data):
    res = testapp.post_json('/files-processed', processed_file_data, status=201)
    assert not res.json.get('errors')


def test_validate_filename_invalid_file_format_post(testapp, processed_file_data):
    processed_file_data['file_format'] = 'stringy file format'
    processed_file_data['filename'] = 'test_file.bam'
    res = testapp.post_json('/files-processed', processed_file_data, status=422)
    errors = res.json['errors']
    descriptions = ''.join([e['description'] for e in errors])
    assert 'Problem getting file_format for test_file.bam' in descriptions


def test_validate_filename_valid_file_format_and_name_post(testapp, processed_file_data):
    processed_file_data['filename'] = 'test_file.bam'
    res = testapp.post_json('/files-processed', processed_file_data, status=201)
    assert not res.json.get('errors')


def test_validate_filename_invalid_filename_post(testapp, processed_file_data):
    processed_file_data['filename'] = 'test_file_bam'
    res = testapp.post_json('/files-processed', processed_file_data, status=422)
    errors = res.json['errors']
    descriptions = ''.join([e['description'] for e in errors])
    assert "Filename test_file_bam extension does not agree with specified file format. Valid extension(s): '.bam'" in descriptions


def test_validate_filename_valid_filename_patch(testapp, processed_file_data):
    processed_file_data['filename'] = 'test_file1.bam'
    res1 = testapp.post_json('/files-processed', processed_file_data, status=201)
    assert not res1.json.get('errors')
    res1_props = res1.json['@graph'][0]
    assert res1_props['filename'] == 'test_file1.bam'
    filename2patch = 'test_file2.bam'
    res2 = testapp.patch_json(res1_props['@id'], {'filename': filename2patch}, status=200)
    assert not res2.json.get('errors')
    assert res2.json['@graph'][0]['filename'] == 'test_file2.bam'


def test_validate_filename_invalid_filename_patch(testapp, processed_file_data):
    processed_file_data['filename'] = 'test_file1.bam'
    res1 = testapp.post_json('/files-processed', processed_file_data, status=201)
    assert not res1.json.get('errors')
    res1_props = res1.json['@graph'][0]
    assert res1_props['filename'] == 'test_file1.bam'
    filename2patch = 'test_file2.txt'
    res2 = testapp.patch_json(res1_props['@id'], {'filename': filename2patch}, status=422)
    errors = res2.json['errors']
    descriptions = ''.join([e['description'] for e in errors])
    assert "Filename test_file2.txt extension does not agree with specified file format. Valid extension(s): '.bam'" in descriptions


def test_validate_produced_from_files_invalid_post(testapp, processed_file_data):
    fids = ['not_a_file_id', 'definitely_not']
    processed_file_data['produced_from'] = fids
    res = testapp.post_json('/files-processed', processed_file_data, status=422)
    errors = res.json['errors']
    descriptions = [e['description'] for e in errors]
    for fid in fids:
        desc = "'%s' not found" % fid
        assert desc in descriptions


def test_validate_extra_files_no_extra_files(testapp, processed_file_data):
    res = testapp.post_json('/files-processed', processed_file_data, status=201)
    assert not res.json.get('errors')


def test_validate_extra_files_extra_files_good_post(testapp, processed_file_data):
    extf = {'file_format': 'bai'}
    processed_file_data['extra_files'] = [extf]
    res = testapp.post_json('/files-processed', processed_file_data, status=201)
    accession = res.json['@graph'][0]['accession']
    extra_file_name = res.json['@graph'][0]['extra_files'][0]['filename']
    assert extra_file_name == f'{accession}.bam.bai'
    assert not res.json.get('errors')


def test_validate_extra_files_extra_files_bad_post_extra_same_as_primary(testapp, processed_file_data):
    extf = {'file_format': 'bam'}
    processed_file_data['extra_files'] = [extf]
    res = testapp.post_json('/files-processed', processed_file_data, status=422)
    assert res.json['errors'][0]['name'] == 'File: invalid extra_file formats'
    assert "'bam' format cannot be the same for file and extra_file" == res.json['errors'][0]['description']


def test_validate_extra_files_extra_files_bad_patch_extra_same_as_primary(testapp, processed_file_data):
    extf = {'file_format': 'bam'}
    res1 = testapp.post_json('/files-processed', processed_file_data, status=201)
    pfid = res1.json['@graph'][0]['@id']
    res2 = testapp.patch_json(pfid, {'extra_files': [extf]}, status=422)
    assert res2.json['errors'][0]['name'] == 'File: invalid extra_file formats'
    assert "'bam' format cannot be the same for file and extra_file" == res2.json['errors'][0]['description']


def test_validate_extra_files_extra_files_bad_post_existing_extra_format(testapp, processed_file_data):
    extfs = [{'file_format': 'bai'}, {'file_format': 'bai'}]
    processed_file_data['extra_files'] = extfs
    res = testapp.post_json('/files-processed', processed_file_data, status=422)
    assert res.json['errors'][0]['name'] == 'File: invalid extra_file formats'
    assert "Multple extra files with 'bai' format cannot be submitted at the same time" == res.json['errors'][0]['description']


def test_validate_extra_files_extra_files_ok_patch_existing_extra_format(testapp, processed_file_data):
    extf = {'file_format': 'bai'}
    processed_file_data['extra_files'] = [extf]
    res1 = testapp.post_json('/files-processed', processed_file_data, status=201)
    pfid = res1.json['@graph'][0]['@id']
    res2 = testapp.patch_json(pfid, {'extra_files': [extf]}, status=200)
    assert not res2.json.get('errors')


def test_validate_extra_files_parent_should_not_have_extras(
        testapp, processed_file_data, file_formats):
    extf = {'file_format': 'bai'}
    processed_file_data['file_format'] = file_formats.get('zip').get('uuid')
    processed_file_data['extra_files'] = [extf]
    res1 = testapp.post_json('/files-processed', processed_file_data, status=422)
    errors = res1.json['errors']
    descriptions = ''.join([e['description'] for e in errors])
    assert "File with format zip should not have extra_files" in descriptions


def test_validate_extra_files_bad_extras_format(
        testapp, processed_file_data, file_formats):
    extf = {'file_format': 'whosit'}
    processed_file_data['extra_files'] = [extf]
    res1 = testapp.post_json('/files-processed', processed_file_data, status=422)
    errors = res1.json['errors']
    descriptions = ''.join([e['description'] for e in errors])
    assert "'whosit' not a valid or known file format" in descriptions


def test_validate_file_format_validity_for_file_type_allows(testapp, file_formats):
    my_fastq_file = {
        'file_format': file_formats.get('fastq').get('uuid'),
    }
    my_proc_file = {
        'file_format': file_formats.get('bam').get('uuid'),
    }
    res1 = testapp.post_json('/files-submitted', my_fastq_file, status=201)
    res2 = testapp.post_json('/files-processed', my_proc_file, status=201)
    assert not res1.json.get('errors')
    assert not res2.json.get('errors')


def test_validate_file_format_validity_for_file_type_fires(testapp, file_formats):
    my_fastq_file = {
        'file_format': file_formats.get('bam').get('uuid'),
    }
    my_proc_file = {
        'file_format': file_formats.get('fastq').get('uuid'),
    }
    res1 = testapp.post_json('/files-submitted', my_fastq_file, status=422)
    errors = res1.json['errors']
    descriptions = ''.join([e['description'] for e in errors])
    assert "File format bam is not allowed for FileSubmitted" in descriptions
    res2 = testapp.post_json('/files-processed', my_proc_file, status=422)
    errors = res2.json['errors']
    descriptions = ''.join([e['description'] for e in errors])
    assert "File format fastq is not allowed for FileProcessed" in descriptions


def test_file_format_does_not_exist(testapp, file_formats):
    my_fastq_file = {
        'file_format': 'waldo',
    }
    res1 = testapp.post_json('/files-submitted', my_fastq_file, status=422)
    errors = res1.json['errors']
    descriptions = ''.join([e['description'] for e in errors])
    assert "'waldo' not found" in descriptions


def test_filename_patch_fails_wrong_format(testapp, file_formats):
    my_fastq_file = {
        'file_format': file_formats.get('fastq').get('uuid'),
        'filename': 'test.fastq.gz'
    }
    res1 = testapp.post_json('/files-submitted', my_fastq_file, status=201)
    resobj = res1.json['@graph'][0]
    patch_data = {"file_format": file_formats.get('bam').get('uuid')}
    res2 = testapp.patch_json('/files-submitted/' + resobj['uuid'], patch_data, status=422)
    errors = res2.json['errors']
    error1 = "Filename test.fastq.gz extension does not agree with specified file format. Valid extension(s): '.bam'"
    error2 = "File format bam is not allowed for FileSubmitted"
    descriptions = ''.join([e['description'] for e in errors])
    assert error1 in descriptions
    assert error2 in descriptions


def test_filename_patch_works_with_different_format(testapp, file_formats):
    my_proc_file = {
        'file_format': file_formats.get('bam').get('uuid'),
        'filename': 'test.bam'
    }
    res1 = testapp.post_json('/files-processed', my_proc_file, status=201)
    resobj = res1.json['@graph'][0]
    patch_data = {"file_format": file_formats.get('zip').get('uuid'), 'filename': 'test.zip'}
    res2 = testapp.patch_json('/files-processed/' + resobj['uuid'], patch_data, status=200)
    assert not res2.json.get('errors')


def test_file_format_patch_works_if_no_filename(testapp, file_formats):
    my_proc_file = {
        'file_format': file_formats.get('bam').get('uuid')
    }
    res1 = testapp.post_json('/files-processed', my_proc_file, status=201)
    resobj = res1.json['@graph'][0]
    patch_data = {"file_format": file_formats.get('zip').get('uuid')}
    res2 = testapp.patch_json('/files-processed/' + resobj['uuid'], patch_data, status=200)
    assert not res2.json.get('errors')
