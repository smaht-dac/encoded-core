"""Unit tests for WorkflowRun.steps run-data mapping logic.

``WorkflowRun.steps`` is a ``category='page'`` calculated property that grafts
run-time file/parameter metadata onto the analysis-step template pulled from the
associated Workflow. The mapping logic (global source/target detection, matching
by ``workflow_argument_name``, ordinal-based merging, value/value_qc handling) is
intricate and is not exercised directly by the integration tests.

The method only reads ``self.properties`` and calls ``request.embed(...)``, so it
is driven here with a light stub context plus a fake request that returns a
pre-built workflow dict. A fresh workflow dict is built per call because
``steps`` mutates the embedded step dicts in place.
"""
import pytest

from ..types.workflow import WorkflowRun


# The property decorator leaves the underlying function in place; grab it once.
steps = WorkflowRun.steps


class StubContext:
    """Minimal object exposing the ``properties`` the method reads."""

    def __init__(self, properties):
        self.properties = properties


class FakeRequest:
    """Returns a canned workflow dict from ``embed`` (like request.embed)."""

    def __init__(self, workflow):
        self._workflow = workflow
        self.embed_calls = []

    def embed(self, path, *args, **kwargs):
        self.embed_calls.append(path)
        return self._workflow


def _single_step_workflow(inputs=None, outputs=None):
    return {
        'steps': [
            {
                'name': 's1',
                'inputs': inputs if inputs is not None else [],
                'outputs': outputs if outputs is not None else [],
            }
        ]
    }


def test_steps_returns_empty_when_no_workflow():
    ctx = StubContext({'workflow': None})
    request = FakeRequest(_single_step_workflow())
    assert steps(ctx, request) == []
    # embed must not be called if there is no workflow to resolve.
    assert request.embed_calls == []


def test_steps_returns_empty_when_steps_not_a_list():
    ctx = StubContext({'workflow': 'wf1'})
    request = FakeRequest({'steps': None})
    assert steps(ctx, request) == []


def test_steps_returns_empty_when_no_steps():
    ctx = StubContext({'workflow': 'wf1'})
    request = FakeRequest({'steps': []})
    assert steps(ctx, request) == []
    # The workflow *was* resolved.
    assert request.embed_calls == ['/wf1']


def test_steps_maps_output_file_run_data():
    ctx = StubContext({
        'workflow': 'wf1',
        'output_files': [
            {'workflow_argument_name': 'outA', 'value': 'file-1',
             'ordinal': 1, 'file_format': 'bam'},
        ],
    })
    wf = _single_step_workflow(
        outputs=[{'name': 'o1', 'target': [{'name': 'outA'}]}],
    )
    result = steps(ctx, FakeRequest(wf))
    run_data = result[0]['outputs'][0]['run_data']
    assert run_data['file'] == ['file-1']
    assert run_data['type'] == 'output'
    # meta excludes value/value_qc/type/workflow_argument_name.
    assert run_data['meta'] == [{'ordinal': 1, 'file_format': 'bam'}]


def test_steps_maps_input_data_file_run_data():
    ctx = StubContext({
        'workflow': 'wf1',
        'input_files': [{'workflow_argument_name': 'inA', 'value': 'file-2', 'ordinal': 1}],
    })
    wf = _single_step_workflow(
        inputs=[{'name': 'i1', 'meta': {'type': 'data file'},
                 'source': [{'name': 'inA'}]}],
    )
    result = steps(ctx, FakeRequest(wf))
    run_data = result[0]['inputs'][0]['run_data']
    assert run_data['file'] == ['file-2']
    assert run_data['type'] == 'input'


def test_steps_maps_parameter_run_data_uses_value_field():
    ctx = StubContext({
        'workflow': 'wf1',
        'parameters': [{'workflow_argument_name': 'pA', 'value': '5'}],
    })
    wf = _single_step_workflow(
        inputs=[{'name': 'p1', 'meta': {'type': 'parameter'},
                 'source': [{'name': 'pA'}]}],
    )
    result = steps(ctx, FakeRequest(wf))
    run_data = result[0]['inputs'][0]['run_data']
    # Parameters use the 'value' field name rather than 'file'.
    assert run_data['value'] == ['5']
    assert run_data['type'] == 'parameter'
    assert 'file' not in run_data


def test_steps_uses_value_qc_when_value_absent():
    ctx = StubContext({
        'workflow': 'wf1',
        'output_files': [{'workflow_argument_name': 'outA', 'value_qc': 'qc-1', 'ordinal': 1}],
    })
    wf = _single_step_workflow(
        outputs=[{'name': 'o1', 'target': [{'name': 'outA'}]}],
    )
    result = steps(ctx, FakeRequest(wf))
    assert result[0]['outputs'][0]['run_data']['file'] == ['qc-1']


def test_steps_no_matching_argument_leaves_run_data_absent():
    ctx = StubContext({
        'workflow': 'wf1',
        'output_files': [{'workflow_argument_name': 'somethingelse', 'value': 'f'}],
    })
    wf = _single_step_workflow(
        outputs=[{'name': 'o1', 'target': [{'name': 'outA'}]}],
    )
    result = steps(ctx, FakeRequest(wf))
    assert 'run_data' not in result[0]['outputs'][0]


def test_steps_non_global_target_leaves_run_data_absent():
    # A target carrying a 'step' is not global, so it is ignored.
    ctx = StubContext({
        'workflow': 'wf1',
        'output_files': [{'workflow_argument_name': 'outA', 'value': 'f'}],
    })
    wf = _single_step_workflow(
        outputs=[{'name': 'o1', 'target': [{'name': 'outA', 'step': 's0'}]}],
    )
    result = steps(ctx, FakeRequest(wf))
    assert 'run_data' not in result[0]['outputs'][0]


def test_steps_multiple_globals_raises():
    ctx = StubContext({
        'workflow': 'wf1',
        'output_files': [{'workflow_argument_name': 'outA', 'value': 'f'}],
    })
    wf = _single_step_workflow(
        outputs=[{'name': 'o1', 'target': [{'name': 'outA'}, {'name': 'outB'}]}],
    )
    with pytest.raises(Exception, match='more than one source or target'):
        steps(ctx, FakeRequest(wf))


def test_steps_merges_same_argument_name_same_ordinal():
    # Two output files sharing argument name AND ordinal collapse to one entry
    # (later one wins via dict.update).
    ctx = StubContext({
        'workflow': 'wf1',
        'output_files': [
            {'workflow_argument_name': 'outA', 'value': 'f1', 'ordinal': 1},
            {'workflow_argument_name': 'outA', 'value': 'f2', 'ordinal': 1},
        ],
    })
    wf = _single_step_workflow(
        outputs=[{'name': 'o1', 'target': [{'name': 'outA'}]}],
    )
    result = steps(ctx, FakeRequest(wf))
    assert result[0]['outputs'][0]['run_data']['file'] == ['f2']


def test_steps_keeps_same_argument_name_differing_ordinals():
    # Differing ordinals are preserved as separate values, sorted by ordinal.
    ctx = StubContext({
        'workflow': 'wf1',
        'output_files': [
            {'workflow_argument_name': 'outA', 'value': 'f2', 'ordinal': 2},
            {'workflow_argument_name': 'outA', 'value': 'f1', 'ordinal': 1},
        ],
    })
    wf = _single_step_workflow(
        outputs=[{'name': 'o1', 'target': [{'name': 'outA'}]}],
    )
    result = steps(ctx, FakeRequest(wf))
    # Sorted by ordinal -> f1 (ord 1) then f2 (ord 2).
    assert result[0]['outputs'][0]['run_data']['file'] == ['f1', 'f2']
