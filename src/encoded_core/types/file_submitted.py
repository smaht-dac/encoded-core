from snovault import (
    calculated_property,
    collection,
    load_schema,
)
from .file import File, _build_file_embedded_list, file_workflow_run_embeds


def _build_file_submitted_embedded_list():
    """Embedded list for FileSubmitted items."""
    return _build_file_embedded_list() + file_workflow_run_embeds + [
        "quality_metric.overall_quality_status",
        "quality_metric.Total Sequences",
        "quality_metric.Sequence length",
        "quality_metric.url",
    ]


@collection(
    name="files-submitted",
    properties={
        "title": "Submitted Files",
        "description": "Listing of Submitted Files",
    })
class FileSubmitted(File):
    """Collection for individual submitted files."""
    item_type = 'file_submitted'
    schema = load_schema('encoded_core:schemas/file_submitted.json')
    embedded_list = _build_file_submitted_embedded_list()
    rev = dict(File.rev, **{
        'workflow_run_inputs': ('WorkflowRun', 'input_files.value'),
        'workflow_run_outputs': ('WorkflowRun', 'output_files.value'),
    })

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
    def workflow_run_inputs(self, request):
        return self.rev_link_atids(request, "workflow_run_inputs")

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

