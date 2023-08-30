import datetime
import pytz
import structlog

from pyramid.httpexceptions import (
    HTTPForbidden,
    HTTPTemporaryRedirect,
    HTTPNotFound,
)
from pyramid.response import Response
from pyramid.settings import asbool
from pyramid.view import view_config
from snovault import (
    AfterModified,
    BeforeModified,
)
from snovault.elasticsearch import ELASTIC_SEARCH
from snovault.schema_utils import schema_validator
from snovault.util import debug_log
from snovault.validators import (
    validate_item_content_post,
    validate_item_content_put,
    validate_item_content_patch,
    validate_item_content_in_place,
    no_validate_item_content_post,
    no_validate_item_content_put,
    no_validate_item_content_patch
)
from urllib.parse import (
    parse_qs,
    urlparse,
)
from snovault.authentication import session_properties
from snovault.search.search import make_search_subreq
from snovault.util import check_user_is_logged_in, make_s3_client
from snovault.types.base import (
    get_item_or_none,
    collection_add,
    item_edit,
)
from .types.file import File, external_creds


log = structlog.getLogger(__name__)


def includeme(config):
    config.scan(__name__)


@view_config(name='upload', context=File, request_method='GET',
             permission='edit')
@debug_log
def get_upload(context, request):
    external = context.propsheets.get('external', {})
    upload_credentials = external.get('upload_credentials')
    # Show s3 location info for files originally submitted to EDW.

    if upload_credentials is None and external.get('service') == 's3':
        upload_credentials = {
            'upload_url': 's3://{bucket}/{key}'.format(**external),
        }
    return {
        '@graph': [{
            '@id': request.resource_path(context),
            'upload_credentials': upload_credentials,
            'extra_files_creds': context.extra_files_creds(),
        }],
    }


@view_config(name='upload', context=File, request_method='POST',
             permission='edit', validators=[schema_validator({"type": "object"})])
@debug_log
def post_upload(context, request):
    properties = context.upgrade_properties()
    if properties['status'] not in ('uploading', 'to be uploaded by workflow', 'upload failed'):
        raise HTTPForbidden('status must be "uploading" to issue new credentials')
    # accession_or_external = properties.get('accession')
    external = context.propsheets.get('external', None)

    if external is None:
        # Handle objects initially posted as another state.
        bucket = request.registry.settings['file_upload_bucket']
        # maybe this should be properties.uuid
        uuid = context.uuid
        file_format = get_item_or_none(request, properties.get('file_format'), 'file-formats')
        try:
            file_extension = '.' + file_format.get('standard_file_extension')
        except AttributeError:
            file_extension = ''

        key = '{uuid}/{accession}.{file_extension}'.format(
            file_extension=file_extension, uuid=uuid, **properties)

    elif external.get('service') == 's3':
        bucket = external['bucket']
        key = external['key']
    else:
        raise ValueError(external.get('service'))

    # remove the path from the file name and only take first 32 chars
    name = None
    if properties.get('filename'):
        name = properties.get('filename').split('/')[-1][:32]
    profile_name = request.registry.settings.get('file_upload_profile_name')
    creds = external_creds(bucket, key, name, profile_name)
    # in case we haven't uploaded a file before
    context.propsheets['external'] = creds

    new_properties = properties.copy()
    if properties['status'] == 'upload failed':
        new_properties['status'] = 'uploading'

    registry = request.registry
    registry.notify(BeforeModified(context, request))
    context.update(new_properties, {'external': creds})
    registry.notify(AfterModified(context, request))

    rendered = request.embed('/%s/@@object' % context.uuid, as_user=True)
    result = {
        'status': 'success',
        '@type': ['result'],
        '@graph': [rendered],
    }
    return result


def is_file_to_download(properties, file_format, expected_filename=None):
    try:
        file_extension = '.' + file_format.get('standard_file_extension')
    except AttributeError:
        file_extension = ''
    accession_or_external = properties.get('accession') or properties.get('external_accession')
    if not accession_or_external:
        return False
    filename = '{accession}{file_extension}'.format(
        accession=accession_or_external, file_extension=file_extension)
    if expected_filename is None:
        return filename
    elif expected_filename != filename:
        return False
    else:
        return filename


@view_config(name='download', context=File, request_method='GET',
             permission='view', subpath_segments=[0, 1])
def download(context, request):
    """ File download route. Generates a pre-signed S3 URL for the object that expires eventually. """
    check_user_is_logged_in(request)

    # first check for restricted status
    try:
        user_props = session_properties(context, request)
    except Exception as e:
        user_props = {'error': str(e)}
    tracking_values = {'user_agent': request.user_agent, 'remote_ip': request.remote_addr,
                       'user_uuid': user_props.get('details', {}).get('uuid', 'anonymous'),
                       'request_path': request.path_info, 'request_headers': str(dict(request.headers))}

    # proxy triggers if we should use Axel-redirect, useful for s3 range byte queries
    try:
        use_download_proxy = request.client_addr not in request.registry['aws_ipset']
    except TypeError:
        # this fails in testing due to testapp not having ip
        use_download_proxy = False

    # with extra_files the user may be trying to download the main file
    # or one of the files in extra files, the following logic will
    # search to find the "right" file and redirect to a download link for that one
    properties = context.upgrade_properties()
    file_format = get_item_or_none(request, properties.get('file_format'), 'file-formats')
    _filename = None
    if request.subpath:
        _filename, = request.subpath
    filename = is_file_to_download(properties, file_format, _filename)
    if not filename:
        found = False
        for extra in properties.get('extra_files', []):
            eformat = get_item_or_none(request, extra.get('file_format'), 'file-formats')
            filename = is_file_to_download(extra, eformat, _filename)
            if filename:
                found = True
                properties = extra
                external = context.propsheets.get('external' + eformat.get('uuid'))
                if eformat is not None:
                    tracking_values['file_format'] = eformat.get('file_format')
                break
        if not found:
            raise HTTPNotFound(_filename)
    else:
        external = context.propsheets.get('external', {})
        if file_format is not None:
            tracking_values['file_format'] = file_format.get('file_format')
    tracking_values['filename'] = filename

    if not external:
        external = context.build_external_creds(request.registry, context.uuid, properties)
    if external.get('service') == 's3':
        external_bucket = external['bucket']
        wfout_bucket = request.registry.settings['file_wfout_bucket']
        files_bucket = request.registry.settings['file_upload_bucket']
        if external_bucket not in [wfout_bucket, files_bucket]:
            if 'wfout' not in external_bucket:
                external_bucket = files_bucket
            else:
                external_bucket = wfout_bucket
            log.error(f'Encountered s3 bucket mismatch - ignoring metadata value {external_bucket}'
                      f' and using registry value {external_bucket}')
        conn = make_s3_client()
        param_get_object = {
            'Bucket': external_bucket,
            'Key': external['key'],
            'ResponseContentDisposition': 'attachment; filename=' + filename
        }
        if 'Range' in request.headers:
            tracking_values['range_query'] = True
            param_get_object.update({'Range': request.headers.get('Range')})
        else:
            tracking_values['range_query'] = False
        location = conn.generate_presigned_url(
            ClientMethod='get_object',
            Params=param_get_object,
            ExpiresIn=36*60*60
        )
    else:
        raise ValueError(external.get('service'))

    # tracking_values['experiment_type'] = get_file_experiment_type(request, context, properties)
    # # create a tracking_item to track this download
    # tracking_item = {'status': 'in review by lab', 'tracking_type': 'download_tracking',
    #                  'download_tracking': tracking_values}
    # try:
    #     TrackingItem.create_and_commit(request, tracking_item, clean_headers=True)
    # except Exception as e:
    #     log.error('Cannot create TrackingItem on download of %s' % context.uuid, error=str(e))

    if asbool(request.params.get('soft')):
        expires = int(parse_qs(urlparse(location).query)['Expires'][0])
        return {
            '@type': ['SoftRedirect'],
            'location': location,
            'expires': datetime.datetime.fromtimestamp(expires, pytz.utc).isoformat(),
        }

    if 'Range' in request.headers:
        try:
            response_body = conn.get_object(**param_get_object)
        except Exception as e:
            raise e
        response_dict = {
            'body': response_body.get('Body').read(),
            # status_code : 206 if partial, 200 if the range covers whole file
            'status_code': response_body.get('ResponseMetadata').get('HTTPStatusCode'),
            'accept_ranges': response_body.get('AcceptRanges'),
            'content_length': response_body.get('ContentLength'),
            'content_range': response_body.get('ContentRange')
        }
        return Response(**response_dict)

    # We don't use X-Accel-Redirect here so that client behaviour is similar for
    # both aws and non-aws users.
    if use_download_proxy:
        location = request.registry.settings.get('download_proxy', '') + str(location)

    # 307 redirect specifies to keep original method
    raise HTTPTemporaryRedirect(location=location)


def validate_file_format_validity_for_file_type(context, request):
    """Check if the specified file format (e.g. fastq) is allowed for the file type (e.g. FileFastq).
    """
    data = request.json
    if 'file_format' in data:
        file_format_item = get_item_or_none(request, data['file_format'], 'file-formats')
        if not file_format_item:
            # item level validation will take care of generating the error
            return
        file_format_name = file_format_item['file_format']
        allowed_types = file_format_item.get('valid_item_types', [])
        file_type = context.type_info.name
        if file_type not in allowed_types:
            msg = 'File format {} is not allowed for {}'.format(file_format_name, file_type)
            request.errors.add('body', 'File: invalid format', msg)
        else:
            request.validated.update({})


def validate_file_filename(context, request):
    """ validator for filename field """
    found_match = False
    data = request.json
    if 'filename' not in data:
        # see if there is an existing file_name
        filename = context.properties.get('filename')
        if not filename:
            return
    else:
        filename = data['filename']
    ff = data.get('file_format')
    if not ff:
        ff = context.properties.get('file_format')
    file_format_item = get_item_or_none(request, ff, 'file-formats')
    if not file_format_item:
        msg = 'Problem getting file_format for %s' % filename
        request.errors.add('body', 'File: no format', msg)
        return
    msg = None
    try:
        file_extensions = [file_format_item.get('standard_file_extension')]
        if file_format_item.get('other_allowed_extensions'):
            file_extensions.extend(file_format_item.get('other_allowed_extensions'))
            file_extensions = list(set(file_extensions))
    except (AttributeError, TypeError):
        msg = 'Problem getting file_format for %s' % filename
    else:
        if file_format_item.get('file_format') == 'other':
            found_match = True
        elif not file_extensions:  # this shouldn't happen
            pass
        for extension in file_extensions:
            if filename[-(len(extension) + 1):] == '.' + extension:
                found_match = True
                break
    if found_match:
        request.validated.update({})
    else:
        if not msg:
            msg = ["'." + ext + "'" for ext in file_extensions]
            msg = ', '.join(msg)
            msg = ('Filename %s extension does not agree with specified file format. '
                   'Valid extension(s): %s' % (filename, msg))
        request.errors.add('body', 'File: invalid extension', msg)


def validate_processed_file_unique_md5_with_bypass(context, request):
    """validator to check md5 on processed files, unless you tell it not to"""
    # skip validator if not file processed
    if context.type_info.item_type != 'file_processed':
        return
    data = request.json
    if 'md5sum' not in data or not data['md5sum']:
        return
    if 'force_md5' in request.query_string:
        return
    # we can of course patch / put to ourselves the same md5 we previously had
    if context.properties.get('md5sum') == data['md5sum']:
        return

    if ELASTIC_SEARCH in request.registry:
        search = make_search_subreq(request, '/search/?type=File&md5sum=%s' % data['md5sum'])
        search_resp = request.invoke_subrequest(search, True)
        if search_resp.status_int < 400:
            # already got this md5
            found = search_resp.json['@graph'][0]['accession']
            request.errors.add('body', 'File: non-unique md5sum', 'md5sum %s already exists for accession %s' %
                               (data['md5sum'], found))
    else:  # find it in the database
        conn = request.registry['connection']
        res = conn.get_by_json('md5sum', data['md5sum'], 'file_processed')
        if res is not None:
            # md5 already exists
            found = res.properties['accession']
            request.errors.add('body', 'File: non-unique md5sum', 'md5sum %s already exists for accession %s' %
                               (data['md5sum'], found))


def validate_processed_file_produced_from_field(context, request):
    """validator to make sure that the values in the
    produced_from field are valid file identifiers"""
    # skip validator if not file processed
    if context.type_info.item_type != 'file_processed':
        return
    data = request.json
    if 'produced_from' not in data:
        return
    files_ok = True
    files2chk = data['produced_from']
    for i, f in enumerate(files2chk):
        try:
            fid = get_item_or_none(request, f, 'files').get('uuid')
        except AttributeError:
            files_ok = False
            request.errors.add('body', 'File: invalid produced_from id', "'%s' not found" % f)
            # bad_files.append(f)
        else:
            if not fid:
                files_ok = False
                request.errors.add('body', 'File: invalid produced_from id', "'%s' not found" % f)

    if files_ok:
        request.validated.update({})


def validate_extra_file_format(context, request):
    """validator to check to be sure that file_format of extrafile is not the
       same as the file and is a known format for the schema
    """
    files_ok = True
    data = request.json
    if not data.get('extra_files'):
        return
    extras = data['extra_files']
    # post should always have file_format as it is required patch may or may not
    ff = data.get('file_format')
    if not ff:
        ff = context.properties.get('file_format')
    file_format_item = get_item_or_none(request, ff, 'file-formats')
    if not file_format_item or 'standard_file_extension' not in file_format_item:
        request.errors.add('body', 'File: no extra_file format', "Can't find parent file format for extra_files")
        return
    parent_format = file_format_item['uuid']
    schema_eformats = file_format_item.get('extrafile_formats')
    if not schema_eformats:  # means this parent file shouldn't have any extra files
        request.errors.add(
            'body', 'File: invalid extra files',
            "File with format %s should not have extra_files" % file_format_item.get('file_format')
        )
        return
    else:
        valid_ext_formats = []
        for ok_format in schema_eformats:
            ok_format_item = get_item_or_none(request, ok_format, 'file-formats')
            try:
                off_uuid = ok_format_item.get('uuid')
            except AttributeError:
                raise Exception("FileFormat Item %s contains unknown FileFormats"
                                " in the extrafile_formats property" % file_format_item.get('uuid'))
            valid_ext_formats.append(off_uuid)
    seen_ext_formats = []
    # formats = request.registry['collections']['FileFormat']
    for i, ef in enumerate(extras):
        eformat = ef.get('file_format')
        if eformat is None:
            return  # will fail the required extra_file.file_format
        eformat_item = get_item_or_none(request, eformat, 'file-formats')
        try:
            ef_uuid = eformat_item.get('uuid')
        except AttributeError:
            request.errors.add(
                'body', 'File: invalid extra_file format', "'%s' not a valid or known file format" % eformat
            )
            files_ok = False
            break
        if ef_uuid in seen_ext_formats:
            request.errors.add(
                'body', 'File: invalid extra_file formats',
                "Multple extra files with '%s' format cannot be submitted at the same time" % eformat
            )
            files_ok = False
            break
        else:
            seen_ext_formats.append(ef_uuid)
        if ef_uuid == parent_format:
            request.errors.add(
                'body', 'File: invalid extra_file formats',
                "'%s' format cannot be the same for file and extra_file" % file_format_item.get('file_format')
            )
            files_ok = False
            break

        if ef_uuid not in valid_ext_formats:
            request.errors.add(
                'body', 'File: invalid extra_file formats',
                "'%s' not a valid extrafile_format for '%s'" % (eformat, file_format_item.get('file_format'))
            )
            files_ok = False
    if files_ok:
        request.validated.update({})


def build_drs_object_from_props(drs_object_base, props):
    """ Takes in base properties for a DRS object we expect on all items and expands them if corresponding
        properties exist
    """
    # fields that match exactly in name and structure
    for exact_field in [
        'description',
    ]:
        if exact_field in props:
            drs_object_base[exact_field] = props[exact_field]

    # size is required by DRS so take it or default to 0
    drs_object_base['size'] = props.get('file_size', 0)

    # use system uuid as alias
    drs_object_base['aliases'] = [props['uuid']]

    # fields that are mapped to different names/structure
    if 'content_md5sum' in props:
        drs_object_base['checksums'] = [
            {
                'checksum': props['content_md5sum'],
                'type': 'md5'
            }
        ]
        # use md5sum as version
        drs_object_base['version'] = props['content_md5sum']
    if 'filename' in props:
        drs_object_base['name'] = props['filename']
    if 'last_modified' in props:
        drs_object_base['updated_time'] = props['last_modified']['date_modified']
    return drs_object_base


@view_config(name='drs', context=File, request_method='GET',
             permission='view', subpath_segments=[0, 1])
def drs(context, request):
    """ DRS object implementation for file. """
    rendered_object = request.embed(str(context.uuid), '@@object', as_user=True)
    accession = rendered_object['accession']
    drs_object_base = {
        'id': rendered_object['@id'],
        'created_time': rendered_object['date_created'],
        'drs_id': accession,
        'self_uri': f'drs://{request.host}{request.path}',
        'access_methods': [
            {
                # always prefer https
                'access_url': {
                    'url': f'https://{request.host}/{accession}/@@download'
                },
                'type': 'https'
            },
            {
                # but provide http as well in case we are not on prod
                'access_url': {
                    'url': f'http://{request.host}/{accession}/@@download'
                },
                'type': 'http'
            },
        ]
    }
    return build_drs_object_from_props(drs_object_base, rendered_object)


@view_config(context=File.Collection, permission='add', request_method='POST',
             validators=[validate_item_content_post,
                         validate_file_filename,
                         validate_extra_file_format,
                         validate_file_format_validity_for_file_type,
                         validate_processed_file_unique_md5_with_bypass,
                         validate_processed_file_produced_from_field])
@view_config(context=File.Collection, permission='add_unvalidated', request_method='POST',
             validators=[no_validate_item_content_post],
             request_param=['validate=false'])
@debug_log
def file_add(context, request, render=None):
    return collection_add(context, request, render)


@view_config(context=File, permission='edit', request_method='PUT',
             validators=[validate_item_content_put,
                         validate_file_filename,
                         validate_extra_file_format,
                         validate_file_format_validity_for_file_type,
                         validate_processed_file_unique_md5_with_bypass,
                         validate_processed_file_produced_from_field])
@view_config(context=File, permission='edit', request_method='PATCH',
             validators=[validate_item_content_patch,
                         validate_file_filename,
                         validate_extra_file_format,
                         validate_file_format_validity_for_file_type,
                         validate_processed_file_unique_md5_with_bypass,
                         validate_processed_file_produced_from_field])
@view_config(context=File, permission='edit_unvalidated', request_method='PUT',
             validators=[no_validate_item_content_put],
             request_param=['validate=false'])
@view_config(context=File, permission='edit_unvalidated', request_method='PATCH',
             validators=[no_validate_item_content_patch],
             request_param=['validate=false'])
@view_config(context=File, permission='index', request_method='GET',
             validators=[validate_item_content_in_place,
                         validate_file_filename,
                         validate_extra_file_format,
                         validate_file_format_validity_for_file_type,
                         validate_processed_file_unique_md5_with_bypass,
                         validate_processed_file_produced_from_field],
             request_param=['check_only=true'])
@debug_log
def file_edit(context, request, render=None):
    return item_edit(context, request, render)
