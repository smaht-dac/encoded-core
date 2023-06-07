from snovault import (
    calculated_property,
    collection,
    load_schema,
)
from .file import File, file_workflow_run_embeds


@collection(
    name='files-processed',
    properties={
        'title': 'Processed Files',
        'description': 'Listing of Processed Files',
    })
class FileProcessed(File):
    """Collection for individual processed files."""
    item_type = 'file_processed'
    schema = load_schema('encoded_core:schemas/file_processed.json')
    embedded_list = File.embedded_list + file_workflow_run_embeds
    rev = dict(File.rev, **{
        'workflow_run_inputs': ('WorkflowRun', 'input_files.value'),
        'workflow_run_outputs': ('WorkflowRun', 'output_files.value'),
    })
    aggregated_items = {
        "last_modified": [
            "date_modified"
        ],
    }

    @classmethod
    def get_bucket(cls, registry):
        return registry.settings['file_wfout_bucket']

    @calculated_property(schema={
        "title": "Input of Workflow Runs",
        "description": "All workflow runs that this file serves as an input to",
        "type": "array",
        "items": {
            "title": "Input of Workflow Run",
            "type": ["string", "object"],
            "linkTo": "WorkflowRun"
        }
    })
    def workflow_run_inputs(self, request, disable_wfr_inputs=False):
        # switch this calc prop off for some processed files, i.e. control exp files
        if not disable_wfr_inputs:
            return self.rev_link_atids(request, "workflow_run_inputs")
        else:
            return []

    @calculated_property(schema={
        "title": "Output of Workflow Runs",
        "description": "All workflow runs that this file serves as an output from",
        "type": "array",
        "items": {
            "title": "Output of Workflow Run",
            "type": "string",
            "linkTo": "WorkflowRun"
        }
    })
    def workflow_run_outputs(self, request):
        return self.rev_link_atids(request, "workflow_run_outputs")

    # processed files don't want md5 as unique key
    def unique_keys(self, properties):
        keys = super(FileProcessed, self).unique_keys(properties)
        if keys.get('alias'):
            keys['alias'] = [k for k in keys['alias'] if not k.startswith('md5:')]
        return keys
