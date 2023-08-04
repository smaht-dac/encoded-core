from dcicutils.project_utils import C4ProjectRegistry
from snovault.project_defs import SnovaultProject
from .project_env import APPLICATION_NAME, APPLICATION_PYPROJECT_NAME


@C4ProjectRegistry.register(APPLICATION_PYPROJECT_NAME)
class EncodedCoreProject(SnovaultProject):
    NAMES = {'NAME': APPLICATION_NAME, 'PYPI_NAME': APPLICATION_PYPROJECT_NAME}
    ACCESSION_PREFIX = 'ENC'
    PROJECT_NAME = 'encoded_core'
