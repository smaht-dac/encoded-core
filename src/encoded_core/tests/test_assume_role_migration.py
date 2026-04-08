#!/usr/bin/env python3
#Kellys Refactor Test File: Can be deleted once working
"""
Standalone test for the assume_role migration in external_creds().
Run with:  python test_assume_role_migration.py
"""
import boto3, json, os, sys
import pytest

ROLE_ARN = os.environ.get('S3_UPLOAD_ROLE_ARN')
BUCKET   = os.environ.get('TEST_S3_BUCKET')
KEY      = os.environ.get('TEST_S3_KEY')
SESSION  = 'migration-test-session'


def test_get_scoped_credentials():
    if not ROLE_ARN:
        pytest.skip('S3_UPLOAD_ROLE_ARN not set - skipping')
    print('TEST 1: assume_role returns credentials...')
    conn = boto3.client('sts')
    token = conn.assume_role(
        RoleArn=ROLE_ARN,
        RoleSessionName=SESSION,
        Policy=json.dumps(build_upload_policy(BUCKET, KEY))
    )
    creds = token['Credentials']
    assert 'AccessKeyId' in creds
    assert 'SecretAccessKey' in creds
    assert 'SessionToken' in creds
    assumed_user = token['AssumedRoleUser']
    assert 'Arn' in assumed_user
    assert 'AssumedRoleId' in assumed_user
    print(f'  OK — expires {creds["Expiration"]}')
    return creds


def test_upload_works():
    if not ROLE_ARN:
        pytest.skip('S3_UPLOAD_ROLE_ARN not set - skipping')
    print('TEST 2: scoped creds can upload to target key...')
    creds = _get_creds()
    s3 = boto3.client('s3',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'])
    s3.put_object(Bucket=BUCKET, Key=KEY, Body=b'migration test content')
    print('  OK')


def test_download_works():
    if not ROLE_ARN:
        pytest.skip('S3_UPLOAD_ROLE_ARN not set - skipping')
    print('TEST 3: scoped creds can download target key...')
    creds = _get_creds()
    s3 = boto3.client('s3',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'])
    resp = s3.get_object(Bucket=BUCKET, Key=KEY)
    assert resp['Body'].read() == b'migration test content'
    print('  OK')


def test_other_key_denied():
    if not ROLE_ARN:
        pytest.skip('S3_UPLOAD_ROLE_ARN not set - skipping')
    print('TEST 4: scoped creds CANNOT access a different key (policy enforcement)...')
    creds = _get_creds()
    s3 = boto3.client('s3',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'])
    try:
        s3.get_object(Bucket=BUCKET, Key='some/completely/different/key.txt')
        pytest.fail('Should have been denied!')
    except Exception as e:
        if 'AccessDenied' in str(e) or '403' in str(e):
            print('  OK — access correctly denied')
        else:
            raise


def test_download_only_policy():
    if not ROLE_ARN:
        pytest.skip('S3_UPLOAD_ROLE_ARN not set - skipping')
    print('TEST 5: download-only policy (upload=False) denies PutObject...')
    download_policy = {
        "Version": "2012-10-17",
        "Statement": [{"Action": ["s3:GetObject"],
                       "Resource": [f"arn:aws:s3:::{BUCKET}/{KEY}"],
                       "Effect": "Allow"}]
    }
    conn = boto3.client('sts')
    token = conn.assume_role(
        RoleArn=ROLE_ARN,
        RoleSessionName=SESSION + '-dl',
        Policy=json.dumps(download_policy)
    )
    creds = token['Credentials']
    s3 = boto3.client('s3',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'])
    try:
        s3.put_object(Bucket=BUCKET, Key=KEY, Body=b'should fail')
        pytest.fail('PutObject should have been denied!')
    except Exception:
        print('  OK — PutObject correctly denied on download-only creds')


def build_upload_policy(bucket, key):
    """Mirrors the policy built in external_creds() for upload=True."""
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Action": ["s3:GetObject", "s3:PutObject"],
            "Resource": [f"arn:aws:s3:::{bucket}/{key}"],
            "Effect": "Allow"
        }, {
            "Action": ["s3:ListBucket"],
            "Resource": [f"arn:aws:s3:::{bucket}"],
            "Condition": {"StringLike": {"s3:prefix": [key]}},
            "Effect": "Allow"
        }, {
            "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*",
                       "kms:GenerateDataKey*", "kms:DescribeKey"],
            "Resource": "*",
            "Effect": "Allow"
        }]
    }


def _get_creds():
    """Helper to get fresh assumed role credentials."""
    conn = boto3.client('sts')
    token = conn.assume_role(
        RoleArn=ROLE_ARN,
        RoleSessionName=SESSION,
        Policy=json.dumps(build_upload_policy(BUCKET, KEY))
    )
    return token['Credentials']


if __name__ == '__main__':
    if not ROLE_ARN:
        print('S3_UPLOAD_ROLE_ARN not set — export it before running directly')
        sys.exit(1)
    creds = _get_creds()
    s3 = boto3.client('s3',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'])
    test_get_scoped_credentials()
    test_upload_works()
    test_download_works()
    test_other_key_denied()
    test_download_only_policy()
    print()
    print('All tests passed. Ready to open PR.')