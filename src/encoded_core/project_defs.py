from dcicutils.project_utils import C4ProjectRegistry
from snovault.project_defs import SnovaultProject


@C4ProjectRegistry.register('encoded-core')
class EncodedCoreProject(SnovaultProject):
    NAMES = {'NAME': 'core', 'PYPI_NAME': 'encoded-core'}
    ACCESSION_PREFIX = 'ENC'
