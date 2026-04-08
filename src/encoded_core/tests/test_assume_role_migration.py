#!/usr/bin/env python3
"""
Standalone test for the assume_role migration in external_creds().
Run with:  python test_assume_role_migration.py
"""
import boto3, json, os, sys
 
ROLE_ARN    = os.environ['S3_UPLOAD_ROLE_ARN']
BUCKET      = os.environ['TEST_S3_BUCKET']
KEY         = os.environ['TEST_S3_KEY']
SESSION     = 'migration-test-session'
 
def build_upload_policy(bucket, key):
    """Mirrors the policy built in external_creds() for upload=True."""
    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Action": ["s3:GetObject", "s3:PutObject"],
            "Resource": [f"arn:aws:s3:::{bucket}/{key}"],
            "Effect": "Allow"
        }, 
        {
            "Action": ["s3:ListBucket"],
            "Resource": [f"arn:aws:s3:::{bucket}"],
            "Condition": {"StringLike": {"s3:prefix": [key]}},
            "Effect": "Allow"
        },
        {
            "Action": [
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey"
            ],
            "Resource": "*",
            "Effect": "Allow"
        }
        ]
    }
    return policy
 
def test_get_scoped_credentials():
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
def test_upload_works(creds):
    print('TEST 2: scoped creds can upload to target key...')
    s3 = boto3.client('s3',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'])
    s3.put_object(Bucket=BUCKET, Key=KEY, Body=b'migration test content')
    print('  OK')
    return s3
def test_download_works(s3):
    print('TEST 3: scoped creds can download target key...')
    resp = s3.get_object(Bucket=BUCKET, Key=KEY)
    assert resp['Body'].read() == b'migration test content'
    print('  OK')
def test_other_key_denied(creds):
    print('TEST 4: scoped creds CANNOT access a different key (policy enforcement)...')
    s3 = boto3.client('s3',
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'])
    try:
        s3.get_object(Bucket=BUCKET, Key='some/completely/different/key.txt')
        print('  FAIL — should have been denied!')
        sys.exit(1)
    except s3.exceptions.ClientError as e:
        assert e.response['Error']['Code'] in ('403', 'AccessDenied')
        print('  OK — access correctly denied')
def test_download_only_policy():
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
        print('  FAIL — PutObject should have been denied!')
        sys.exit(1)
    except Exception:
        print('  OK — PutObject correctly denied on download-only creds')
if __name__ == '__main__':
    creds = test_get_scoped_credentials()
    s3    = test_upload_works(creds)
    test_download_works(s3)
    test_other_key_denied(creds)
    test_download_only_policy()
    print()
    print('All tests passed. Ready to open PR.')
