import copy
from snovault import calculated_property, collection, load_schema
from snovault.types.base import Item


def _build_workflows_embedded_list():
    """ Helper function for building workflow embedded list. """
    return Item.embedded_list + [
            'steps.name',

            # Objects
            'steps.inputs.*',
            'steps.outputs.*',

            # Software linkTo
            'steps.meta.software_used.name',
            'steps.meta.software_used.title',
            'steps.meta.software_used.version',
            'steps.meta.software_used.source_url',

            # FileFormat linkTo
            'arguments.argument_format.file_format',

            'arguments.argument_type',
            'arguments.workflow_argument_name'
    ]


@collection(
    name='workflows',
    properties={
        'title': 'Workflows',
        'description': 'Listing of 4DN analysis workflows',
    })
class Workflow(Item):
    """The Workflow class that describes a workflow and steps in it."""

    item_type = 'workflow'
    schema = load_schema('encoded_core:schemas/workflow.json')
    embedded_list = _build_workflows_embedded_list()
    rev = {
        'newer_versions': ('Workflow', 'previous_version')
    }

    @calculated_property(schema={
        "title": "Newer Versions",
        "description": "Newer versions of this workflow",
        "type": "array",
        "exclude_from": ["FFedit-create"],
        "items": {
            "title": "Newer versions",
            "type": ["string", "object"],
            "linkTo": "Workflow"
        }
    })
    def newer_versions(self, request):
        return self.rev_link_atids(request, "newer_versions")


def _build_workflow_run_embedded_list():
    """ Helper function for building workflow embedded list. """
    return Item.embedded_list + [
        # Workflow linkTo
        'workflow.category',
        'workflow.experiment_types',
        'workflow.app_name',
        'workflow.title',
        'workflow.steps.name',

        # Software linkTo
        'workflow.steps.meta.software_used.name',
        'workflow.steps.meta.software_used.title',
        'workflow.steps.meta.software_used.version',
        'workflow.steps.meta.software_used.source_url',

        # String
        'input_files.workflow_argument_name',
        # File linkTo
        'input_files.value.filename',
        'input_files.value.display_title',
        'input_files.value.href',
        'input_files.value.file_format',
        'input_files.value.accession',
        'input_files.value.@type',
        'input_files.value.@id',
        'input_files.value.file_size',
        'input_files.value.quality_metric.url',
        'input_files.value.quality_metric.overall_quality_status',
        'input_files.value.status',

        # String
        'output_files.workflow_argument_name',

        # File linkTo
        'output_files.value.filename',
        'output_files.value.display_title',
        'output_files.value.href',
        'output_files.value.file_format',
        'output_files.value.accession',
        'output_files.value.@type',
        'output_files.value.@id',
        'output_files.value.file_size',
        'output_files.value.quality_metric.url',
        'output_files.value.quality_metric.overall_quality_status',
        'output_files.value.status',
        'output_files.value_qc.url',
        'output_files.value_qc.overall_quality_status'
    ]


steps_run_data_schema = {
    "type": "object",
    "properties": {
        "file": {
            "type": "array",
            "title": "File(s)",
            "description": "File(s) for this step input/output argument.",
            "items": {
                "type": ["string", "object"],  # Either string (uuid) or a object/dict containing uuid & other front-end-relevant properties from File Item.
                "linkTo": "File"  # TODO: (Med/High Priority) Make this work. Will likely wait until after embedding edits b.c. want to take break from WF stuff and current solution works.
            }
        },
        "meta": {
            "type": "array",
            "title": "Additional metadata for input/output file(s)",
            "description": "List of additional info that might be related to file, but not part of File Item itself, such as ordinal.",
            "items": {
                "type": "object"
            }
        },
        "value": {  # This is used in place of run_data.file, e.g. for a parameter string value, that does not actually have a file.
            "title": "Value",
            "type": "string",
            "description": "Value used for this output argument."
        },
        "type": {
            "type": "string",
            "title": "I/O Type"
        }
    }
}


workflow_schema = load_schema('encoded_core:schemas/workflow.json')
workflow_steps_property_schema = workflow_schema.get('properties', {}).get('steps')
workflow_run_steps_property_schema = copy.deepcopy(workflow_steps_property_schema)
workflow_run_steps_property_schema['items']['properties']['inputs']['items']['properties']['run_data'] = steps_run_data_schema
workflow_run_steps_property_schema['items']['properties']['outputs']['items']['properties']['run_data'] = steps_run_data_schema


@collection(
    name='workflow-runs',
    properties={
        'title': 'Workflow Runs',
        'description': 'Listing of executions of 4DN analysis workflows',
    })
class WorkflowRun(Item):
    """The WorkflowRun class that describes execution of a workflow."""

    item_type = 'workflow_run'
    schema = load_schema('encoded_core:schemas/workflow_run.json')
    embedded_list = _build_workflow_run_embedded_list()

    @calculated_property(schema=workflow_run_steps_property_schema, category='page')
    def steps(self, request):
        '''
        Extends the 'inputs' & 'outputs' (lists of dicts) properties of calculated property 'analysis_steps' (list of dicts) from
        WorkflowRun's related Workflow with additional property 'run_data', which contains references to Files, Parameters, and Reports
        generated by this specific Workflow Run.

        :returns: List of analysis_steps items, extended with 'inputs' and 'outputs'.
        '''
        workflow = self.properties.get('workflow')
        if workflow is None:
            return []

        workflow = request.embed('/' + workflow)
        analysis_steps = workflow.get('steps')

        if not isinstance(analysis_steps, list) or len(analysis_steps) == 0:
            return []

        # fileCache = {} # Unnecessary unless we'll convert file @id into plain embedded dictionary, in which case we use this to avoid re-requests for same file UUID.

        def get_global_source_or_target(all_io_source_targets):
            # Find source or target w/o a 'step'.
            # Step outputs or inputs with a source or target without a "step" defined
            # are considered global inputs/outputs. Matching WorkflowRun.[output|input]_files
            # is done against step step.[inputs | output].[target | source].name.
            global_pointing_source_target = [
                source_target for source_target in all_io_source_targets
                if source_target.get('step') is None
            ]
            if len(global_pointing_source_target) > 1:
                raise Exception('Found more than one source or target without a step.')
            if len(global_pointing_source_target) == 0:
                return None
            return global_pointing_source_target[0]


        def map_run_data_to_io_arg(step_io_arg, wfr_runtime_inputs, io_type):
            '''
            Add file metadata in form of 'run_data' : { 'file' : { '@id', 'display_title', etc. } } to AnalysisStep dict's 'input' or 'output' list item dict
            if one of own input or output files' workflow_argument_name matches the AnalysisStep dict's input or output's sourceOrTarget.workflow_argument_name.

            :param step_io_arg: Reference to an 'input' or 'output' dict passed in from a Workflow-derived analysis_step.
            :param wfr_runtime_inputs: List of Step inputs or outputs, such as 'input_files', 'output_files', 'quality_metric', or 'parameters'.
            :returns: True if found and added run_data property to analysis_step.input or analysis_step.output (param inputOrOutput).
            '''
            # is_global_arg = step_io_arg.get('meta', {}).get('global', False) == True
            # if not is_global_arg:
            #    return False # Skip. We only care about global arguments.

            value_field_name = 'value' if io_type == 'parameter' else 'file'

            global_pointing_source_target = get_global_source_or_target(step_io_arg.get('source', step_io_arg.get('target', [])))
            if not global_pointing_source_target:
                return False

            matched_runtime_io_data = [
                io_object for io_object in wfr_runtime_inputs
                if (
                    global_pointing_source_target['name'] == io_object.get('workflow_argument_name') and
                    # Quality Metrics might be saved with `value_qc` in place of `value`
                    (io_object.get('value') is not None or io_object.get('value_qc') is not None)
                )
            ]

            if len(matched_runtime_io_data) > 0:
                matched_runtime_io_data = sorted(matched_runtime_io_data, key=lambda io_object: io_object.get('ordinal', 1))

                # List of file or Item UUIDs.
                value_list = []

                # Aligned-to-file-list-indices list of file metadata(s)
                meta_list = []

                for io_dict in matched_runtime_io_data:
                    # Quality Metrics might be saved with `value_qc` instead of `value`
                    linked_to_item_uuid = io_dict.get('value') or io_dict.get('value_qc')
                    value_list.append(linked_to_item_uuid)
                    # Add all remaining properties from dict in (e.g.) 'input_files','output_files',etc. list.
                    # Contains things like dimension, ordinal, file_format, and so forth.
                    meta_dict = { k:v for (k,v) in io_dict.items() if k not in [ 'value', 'value_qc', 'type', 'workflow_argument_name' ] }
                    # There is a chance we do not have the file_format in the input_files list. Most often this would occur if multiple
                    # files in input argument list
                    meta_list.append(meta_dict)

                step_io_arg['run_data'] = {
                    value_field_name : value_list,
                    "type" : io_type,
                    "meta" : meta_list
                }
                return True
            return False


        def mergeArgumentsWithSameArgumentName(args):
            '''Merge arguments with the same workflow_argument_name, unless differing ordinals'''
            seen_argument_names = {}
            resultArgs = []
            for arg in args:
                argName = arg.get('workflow_argument_name')
                if argName:
                    priorArgument = seen_argument_names.get(argName)
                    if priorArgument and priorArgument.get('ordinal', 1) == arg.get('ordinal', 1):
                        priorArgument.update(arg)
                    else:
                        resultArgs.append(arg)
                        seen_argument_names[argName] = arg
            return resultArgs


        output_files = mergeArgumentsWithSameArgumentName(self.properties.get('output_files', []))
        input_files = mergeArgumentsWithSameArgumentName(self.properties.get('input_files', []))
        input_params = mergeArgumentsWithSameArgumentName(self.properties.get('parameters', []))

        for step in analysis_steps:
            # Add output file metadata to step outputs & inputs, based on workflow_argument_name v step output target name.

            for output in step['outputs']:
                map_run_data_to_io_arg(output, output_files, 'output')

            for input in step['inputs']:
                if input.get('meta', {}).get('type') != 'parameter':
                    map_run_data_to_io_arg(input, input_files, 'input')
                else:
                    map_run_data_to_io_arg(input, input_params, 'parameter')

        return analysis_steps


@collection(
    name='workflow-runs-awsem',
    properties={
        'title': 'Workflow Runs AWSEM',
        'description': 'Listing of executions of 4DN analysis workflows on AWSEM platform',
    })
class WorkflowRunAwsem(WorkflowRun):
    """The WorkflowRun class that describes execution of a workflow on AWSEM platform."""
    base_types = ['WorkflowRun'] + Item.base_types
    item_type = 'workflow_run_awsem'
    schema = load_schema('encoded_core:schemas/workflow_run_awsem.json')
    embedded_list = WorkflowRun.embedded_list
