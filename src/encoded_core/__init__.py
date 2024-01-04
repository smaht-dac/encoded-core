import os
from pyramid.config import Configurator
from pyramid.settings import asbool

from snovault.app import session, configure_dbsession
from snovault.elasticsearch import APP_FACTORY
from snovault.elasticsearch.interfaces import INVALIDATION_SCOPE_ENABLED
from .local_roles import LocalRolesAuthorizationPolicy


APP_VERSION_REGISTRY_KEY = 'encoded-core.app_version'


def app_version(config):
    if not config.registry.settings.get(APP_VERSION_REGISTRY_KEY):
        # we update version as part of deployment process `deploy_beanstalk.py`
        # but if we didn't check env then git
        version = os.environ.get("ENCODED_VERSION", "test")
        config.registry.settings[APP_VERSION_REGISTRY_KEY] = version


def main(global_config, **local_config):
    """ Returns a pyramid wsgi application that can be used as encoded-core - should only
        be used in testing
    """
    settings = global_config
    settings.update(local_config)

    # enable invalidation scope
    settings[INVALIDATION_SCOPE_ENABLED] = True

    config = Configurator(settings=settings)

    config.registry[APP_FACTORY] = main  # used by mp_indexer
    config.include(app_version)

    config.include('pyramid_multiauth')  # must be before calling set_authorization_policy
    # Override default authz policy set by pyramid_multiauth
    config.set_authorization_policy(LocalRolesAuthorizationPolicy())
    config.include(session)

    # must include, as tm.attempts was removed from pyramid_tm
    config.include('pyramid_retry')

    # for CGAP, always enable type=nested mapping
    # NOTE: this MUST occur prior to including Snovault, otherwise it will not work
    config.add_settings({'mappings.use_nested': True})
    config.include(configure_dbsession)
    config.include('snovault')
    config.commit()  # commit so search can override listing

    if 'elasticsearch.server' in config.registry.settings:
        config.include('snovault.elasticsearch')
        config.include('.search.search')
        config.include('.search.compound_search')  # could make enabling configurable

    if asbool(settings.get('testing', False)):
        config.include('snovault.tests.testing_views')
        config.include('snovault.root')

    config.include('.upgrade')
    config.scan()

    app = config.make_wsgi_app()
    return app
