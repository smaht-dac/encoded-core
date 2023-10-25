import boto3
import json
import logging
import os
import structlog
import transaction

from botocore.exceptions import ClientError
from copy import deepcopy
from dcicutils.ecr_utils import CGAP_ECR_REGION
from pyramid.threadlocal import get_current_request
from pyramid.traversal import resource_path
from dcicutils.secrets_utils import assume_identity
from dcicutils.misc_utils import override_environ
from snovault import (
    CONNECTION,
    calculated_property,
    load_schema,
    abstract_collection,
)
from snovault.invalidation import add_to_indexing_queue
from snovault.util import make_s3_client
from snovault.types.base import (
    Item,
    get_item_or_none,
)


logging.getLogger('boto3').setLevel(logging.CRITICAL)


log = structlog.getLogger(__name__)


HREF_SCHEMA = {
    "title": "Download URL",
    "type": "string",
    "description": "Use this link to download this file"
}
UNMAPPED_OBJECT_SCHEMA = {"type": "object"}
UPLOAD_KEY_SCHEMA = {
    "title": "Upload Key",
    "type": "string",
    "description": "File object name in S3",
}

file_workflow_run_embeds = [
    'workflow_run_inputs.workflow.title',
    'workflow_run_inputs.input_files.workflow_argument_name',
    'workflow_run_inputs.input_files.value.filename',
    'workflow_run_inputs.input_files.value.display_title',
    'workflow_run_inputs.input_files.value.file_format',
    'workflow_run_inputs.input_files.value.uuid',
    'workflow_run_inputs.input_files.value.accession',
    'workflow_run_inputs.output_files.workflow_argument_name',
    'workflow_run_inputs.output_files.value.display_title',
    'workflow_run_inputs.output_files.value.file_format',
    'workflow_run_inputs.output_files.value.uuid',
    'workflow_run_inputs.output_files.value.accession',
    'workflow_run_inputs.output_files.value_qc.url',
    'workflow_run_inputs.output_files.value_qc.overall_quality_status'
]

file_workflow_run_embeds_processed = (file_workflow_run_embeds
                                      + [e.replace('workflow_run_inputs.', 'workflow_run_outputs.')
                                         for e in file_workflow_run_embeds])


def show_upload_credentials(request=None, context=None, status=None):
    if request is None or status not in File.SHOW_UPLOAD_CREDENTIALS_STATUSES:
        return False
    return request.has_permission('edit', context)


def external_creds(bucket, key, name=None, profile_name=None):
    """
    if name is None, we want the link to s3 but no need to generate
    an access token.  This is useful for linking metadata to files that
    already exist on s3.
    """

    logging.getLogger('boto3').setLevel(logging.CRITICAL)
    credentials = {}
    s3_encrypt_key_id = None  # might be reassigned later from identity.get('ENCODED_S3_ENCRYPT_KEY_ID')
    if name is not None:
        policy = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Effect': 'Allow',
                    'Action': 's3:PutObject',
                    'Resource': f'arn:aws:s3:::{bucket}/{key}',
                },
            ]
        }
        # In the new environment, extract S3 Keys from global application configuration
        if 'IDENTITY' in os.environ:
            identity = assume_identity()
            with override_environ(**identity):
                conn = boto3.client('sts',
                                    aws_access_key_id=os.environ.get('S3_AWS_ACCESS_KEY_ID'),
                                    aws_secret_access_key=os.environ.get('S3_AWS_SECRET_ACCESS_KEY'))
            s3_encrypt_key_id = identity.get('ENCODED_S3_ENCRYPT_KEY_ID')
            if s3_encrypt_key_id:  # must be used with ACCOUNT_NUMBER as well
                policy['Statement'].append({  # NoQA - PyCharm doesn't like this append for some bogus reason
                    'Effect': 'Allow',
                    'Action': [
                        'kms:Encrypt',
                        'kms:Decrypt',
                        'kms:ReEncrypt*',
                        'kms:GenerateDataKey*',
                        'kms:DescribeKey'
                    ],
                    'Resource': f'arn:aws:kms:{CGAP_ECR_REGION}:{identity["ACCOUNT_NUMBER"]}:key/{s3_encrypt_key_id}'
                })
        # In the old account, we are always passing IAM User creds so these will just work
        else:
            conn = boto3.client('sts',
                                aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
                                aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'))
        token = conn.get_federation_token(Name=name, Policy=json.dumps(policy))
        # 'access_key' 'secret_key' 'expiration' 'session_token'
        credentials = token.get('Credentials')
        # Convert Expiration datetime object to string via cast
        # Uncaught serialization error picked up by Docker - Will 2/25/2021
        credentials['Expiration'] = str(credentials['Expiration'])
        credentials.update({
            'upload_url': f's3://{bucket}/{key}',
            'federated_user_arn': token.get('FederatedUser').get('Arn'),
            'federated_user_id': token.get('FederatedUser').get('FederatedUserId'),
            's3_encrypt_key_id': s3_encrypt_key_id,
            'request_id': token.get('ResponseMetadata').get('RequestId'),
            'key': key
        })
    return {
        'service': 's3',
        'bucket': bucket,
        'key': key,
        'upload_credentials': credentials,
    }


def property_closure(request, propname, root_uuid):
    # Must avoid cycles
    conn = request.registry[CONNECTION]
    seen = set()
    remaining = {str(root_uuid)}
    while remaining:
        seen.update(remaining)
        next_remaining = set()
        for uuid in remaining:
            obj = conn.get_by_uuid(uuid)
            next_remaining.update(obj.__json__(request).get(propname, ()))
        remaining = next_remaining - seen
    return seen


def _build_file_embedded_list():
    """Embedded list for File type."""
    return [
        # FileFormat linkTo
        "file_format.file_format",

        # File linkTo
        "related_files.relationship_type",
        "related_files.file.accession",
        "related_files.file.file_format.file_format",

        # QC
        "quality_metric.@type",
        "quality_metric.qc_list.qc_type",
        "quality_metric.qc_list.value.uuid",
    ]


@abstract_collection(
    name='files',
    unique_key='accession',
    properties={
        'title': 'Files',
        'description': 'Listing of Files',
    })
class File(Item):
    """Collection for individual files."""
    item_type = 'file'
    base_types = ['File'] + Item.base_types
    schema = load_schema('encoded_core:schemas/file.json')
    embedded_list = _build_file_embedded_list()

    SHOW_UPLOAD_CREDENTIALS_STATUSES = (
        'uploading', 'to be uploaded by workflow', 'upload failed'
    )

    @calculated_property(schema={
        "title": "Display Title",
        "description": "Name of this File",
        "type": "string"
    })
    def display_title(self, request, file_format, accession=None, external_accession=None):
        accession = accession or external_accession
        file_format_item = get_item_or_none(request, file_format, 'file-formats')
        try:
            file_extension = '.' + file_format_item.get('standard_file_extension')
        except AttributeError:
            file_extension = ''
        return '{}{}'.format(accession, file_extension)

    @calculated_property(schema={
        "title": "File Type",
        "description": "Type of File",
        "type": "string"
    })
    def file_type_detailed(self, request, file_format, file_type=None):
        outString = (file_type or 'other')
        file_format_item = get_item_or_none(request, file_format, 'file-formats')
        try:
            fformat = file_format_item.get('file_format')
            outString = outString + ' (' + fformat + ')'
        except AttributeError:
            pass
        return outString

    # def generate_track_title(self, track_info, props):
    #     if not props.get('higlass_uid'):
    #         return None
    #     exp_type = track_info.get('experiment_type', None)
    #     if exp_type is None:
    #         return None
    #     bname = track_info.get('biosource_name', 'unknown sample')
    #     ftype = props.get('file_type', 'unspecified type')
    #     assay = track_info.get('assay_info', '')
    #
    #     title = '{ft} for {bs} {et} {ai}'.format(
    #         ft=ftype, ai=assay, et=exp_type, bs=bname
    #     )
    #     return title.replace('  ', ' ').rstrip()

    def _get_file_expt_bucket(self, request, item2check):
        fatid = self.jsonld_id(request)
        if 'files' in item2check:
            if fatid in item2check.get('files'):
                return 'raw file'
        if 'processed_files' in item2check:
            if fatid in item2check.get('processed_files'):
                return 'processed file'
        of_info = item2check.get('other_processed_files', [])
        for obucket in of_info:
            ofiles = obucket.get('files')
            if [of for of in ofiles if of == fatid]:
                return obucket.get('title')
        return None

    def _update(self, properties, sheets=None):
        if not properties:
            return
        # ensure we always have s3 links setup
        sheets = {} if sheets is None else sheets.copy()
        uuid = self.uuid
        old_creds = self.propsheets.get('external', None)
        new_creds = old_creds

        # don't get new creds
        if properties.get('status', None) in self.SHOW_UPLOAD_CREDENTIALS_STATUSES:
            new_creds = self.build_external_creds(self.registry, uuid, properties)
            sheets['external'] = new_creds

        # handle extra files
        updated_extra_files = []
        extra_files = properties.get('extra_files', [])
        if extra_files:
            # get @id for parent file
            try:
                at_id = resource_path(self)
            except Exception:
                at_id = "/" + str(uuid) + "/"
            # ensure at_id ends with a slash
            if not at_id.endswith('/'):
                at_id += '/'

            file_formats = []
            for xfile in extra_files:
                # ensure a file_format (identifier for extra_file) is given and non-null
                if not ('file_format' in xfile and bool(xfile['file_format'])):
                    continue
                eformat = xfile['file_format']
                if eformat.startswith('/file-formats/'):
                    eformat = eformat[len('/file-formats/'):-1]
                xfile_format = self.registry['collections']['FileFormat'].get(eformat)
                xff_uuid = str(xfile_format.uuid)
                if not xff_uuid:
                    raise Exception("Cannot find format item for the extra file")

                if xff_uuid in file_formats:
                    raise Exception("Each file in extra_files must have unique file_format")
                file_formats.append(xff_uuid)
                xfile['file_format'] = xff_uuid

                xfile['accession'] = properties.get('accession')
                # just need a filename to trigger creation of credentials
                xfile_name = xfile.get("filename")
                if xfile_name is None:
                    xfile['filename'] = xfile['accession']
                xfile['uuid'] = str(uuid)
                # if not 'status' in xfile or not bool(xfile['status']):
                #    xfile['status'] = properties.get('status')
                ext = self.build_external_creds(self.registry, uuid, xfile)
                # build href
                file_extension = xfile_format.properties.get('standard_file_extension')
                filename = '{}.{}'.format(xfile['accession'], file_extension)
                xfile['href'] = at_id + '@@download/' + filename
                xfile['upload_key'] = ext['key']
                sheets['external' + xfile['file_format']] = ext
                updated_extra_files.append(xfile)

        if extra_files:
            properties['extra_files'] = updated_extra_files

        if old_creds:
            if old_creds.get('key') != new_creds.get('key'):
                try:
                    conn = make_s3_client()
                    bname = old_creds['bucket']
                    conn.delete_object(Bucket=bname, Key=old_creds['key'])
                except Exception as e:
                    print(e)

        # update self first to ensure 'related_files' are stored in self.properties
        super(File, self)._update(properties, sheets)

        # handle related_files. This is quite janky; must manually invalidate
        # the relation made on `related_fl` item because we are calling its
        # update() method directly, which circumvents snovault.crud_view.item_edit
        DicRefRelation = {
            "derived from": "parent of",
            "parent of": "derived from",
            "supercedes": "is superceded by",
            "is superceded by": "supercedes",
            "paired with": "paired with"
        }

        if 'related_files' in properties:
            my_uuid = str(self.uuid)
            # save these values
            curr_txn = None
            curr_request = None
            for relation in properties["related_files"]:
                try:
                    switch = relation["relationship_type"]
                    rev_switch = DicRefRelation[switch]
                    related_fl = relation["file"]
                    relationship_entry = {"relationship_type": rev_switch, "file": my_uuid}
                except Exception:
                    log.error('Error updating related_files on %s _update. %s'
                              % (my_uuid, relation))
                    continue

                target_fl = self.collection.get(related_fl)
                target_fl_props = deepcopy(target_fl.properties)
                # This is a cool python feature. If break is not hit in the loop,
                # go to the `else` statement. Works for empty lists as well
                for target_relation in target_fl_props.get('related_files', []):
                    if (target_relation.get('file') == my_uuid
                            and target_relation.get('relationship_type') == rev_switch):
                        break
                else:
                    # Get the current request in order to queue the forced
                    # update for indexing. This is bad form.
                    # Don't do this anywhere else, please!
                    if curr_txn is None:
                        curr_txn = transaction.get()
                    if curr_request is None:
                        curr_request = get_current_request()
                    # handle related_files whether or not any currently exist
                    target_related_files = target_fl_props.get('related_files', [])
                    target_related_files.append(relationship_entry)
                    target_fl_props.update({'related_files': target_related_files})
                    target_fl._update(target_fl_props)
                    to_queue = {'uuid': str(target_fl.uuid), 'sid': target_fl.sid,
                                'info': 'queued from %s _update' % my_uuid}
                    curr_txn.addAfterCommitHook(add_to_indexing_queue,
                                                args=(curr_request, to_queue, 'edit'))

    @property
    def __name__(self):
        properties = self.upgrade_properties()
        if properties.get('status') == 'replaced':
            return self.uuid
        return properties.get(self.name_key, None) or self.uuid

    def unique_keys(self, properties):
        keys = super(File, self).unique_keys(properties)
        if properties.get('status') != 'replaced':
            if 'md5sum' in properties:
                value = 'md5:{md5sum}'.format(**properties)
                keys.setdefault('alias', []).append(value)
        return keys

    @calculated_property(schema={
        "title": "Title",
        "type": "string",
        "description": "Accession of this file"
    })
    def title(self, accession=None, external_accession=None):
        return accession or external_accession

    @calculated_property(schema=HREF_SCHEMA)
    def href(self, request, file_format, accession=None, external_accession=None):
        fformat = get_item_or_none(request, file_format, 'file-formats')
        try:
            file_extension = '.' + fformat.get('standard_file_extension')
        except AttributeError:
            file_extension = ''
        accession = accession or external_accession
        filename = '{}{}'.format(accession, file_extension)
        return request.resource_path(self) + '@@download/' + filename

    @calculated_property(schema=UPLOAD_KEY_SCHEMA)
    def upload_key(self, request):
        properties = self.properties
        external = self.propsheets.get('external', {})
        if not external:
            try:
                external = self.build_external_creds(self.registry, self.uuid, properties)
            except ClientError:
                log.error(os.environ)
                log.error(properties)
                return 'UPLOAD KEY FAILED'
        return external['key']

    @calculated_property(
        condition=show_upload_credentials, schema=UNMAPPED_OBJECT_SCHEMA
    )
    def upload_credentials(self):
        external = self.propsheets.get('external', None)
        if external is not None:
            return external['upload_credentials']

    @calculated_property(
        condition=show_upload_credentials, schema=UNMAPPED_OBJECT_SCHEMA
    )
    def extra_files_creds(self):
        external = self.propsheets.get('external', None)
        if external is not None:
            extras = []
            for extra in self.properties.get('extra_files', []):
                eformat = extra.get('file_format')
                xfile_format = self.registry['collections']['FileFormat'].get(eformat)
                try:
                    xff_uuid = str(xfile_format.uuid)
                except AttributeError:
                    print("Can't find required format uuid for %s" % eformat)
                    continue
                extra_creds = self.propsheets.get('external' + xff_uuid)
                extra['upload_credentials'] = extra_creds['upload_credentials']
                extras.append(extra)
            return extras

    @classmethod
    def get_bucket(cls, registry):
        return registry.settings['file_upload_bucket']

    @classmethod
    def build_external_creds(cls, registry, uuid, properties):
        bucket = cls.get_bucket(registry)
        fformat = properties.get('file_format')
        if fformat.startswith('/file-formats/'):
            fformat = fformat[len('/file-formats/'):-1]
        prop_format = registry['collections']['FileFormat'].get(fformat)
        try:
            file_extension = prop_format.properties['standard_file_extension']
        except KeyError:
            raise Exception('File format not in list of supported file types')
        key = '{uuid}/{accession}.{file_extension}'.format(
            file_extension=file_extension, uuid=uuid,
            accession=properties.get('accession'))

        # remove the path from the file name and only take first 32 chars
        fname = properties.get('filename')
        name = None
        if fname:
            name = fname.split('/')[-1][:32]

        profile_name = registry.settings.get('file_upload_profile_name')
        return external_creds(bucket, key, name, profile_name)

    @classmethod
    def create(cls, registry, uuid, properties, sheets=None):
        if properties.get('status') in cls.SHOW_UPLOAD_CREDENTIALS_STATUSES:
            sheets = {} if sheets is None else sheets.copy()
            sheets['external'] = cls.build_external_creds(registry, uuid, properties)
        return super(File, cls).create(registry, uuid, properties, sheets)

    class Collection(Item.Collection):
        pass
