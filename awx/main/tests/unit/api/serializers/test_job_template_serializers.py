# Python
import pytest
import mock

from six.moves import xrange

# AWX
from awx.api.serializers import (
    JobTemplateSerializer,
)
from awx.api.views import JobTemplateDetail
from awx.main.models import (
    Role,
    User,
    Job,
    JobTemplate,
)
from rest_framework.test import APIRequestFactory

#DRF
from rest_framework import serializers


def mock_JT_resource_data():
    return {}


@pytest.fixture
def job_template(mocker):
    mock_jt = mocker.MagicMock(spec=JobTemplate)
    mock_jt.pk = 5
    mock_jt.host_config_key = '9283920492'
    mock_jt.validation_errors = mock_JT_resource_data
    return mock_jt


@pytest.fixture
def job(mocker, job_template):
    return mocker.MagicMock(pk=5, job_template=job_template)


@pytest.fixture
def jobs(mocker):
    return [Job(id=x, name='job-%d' % x) for x in xrange(0, 25)]


@mock.patch('awx.api.serializers.UnifiedJobTemplateSerializer.get_related', lambda x,y: {})
@mock.patch('awx.api.serializers.JobOptionsSerializer.get_related', lambda x,y: {})
class TestJobTemplateSerializerGetRelated():
    @pytest.mark.parametrize("related_resource_name", [
        'jobs',
        'schedules',
        'activity_stream',
        'launch',
        'notification_templates_any',
        'notification_templates_success',
        'notification_templates_error',
        'survey_spec',
        'labels',
        'callback',
    ])
    def test_get_related(self, test_get_related, job_template, related_resource_name):
        test_get_related(JobTemplateSerializer, job_template, 'job_templates', related_resource_name)

    def test_callback_absent(self, get_related_mock_and_run, job_template):
        job_template.host_config_key = None
        related = get_related_mock_and_run(JobTemplateSerializer, job_template)
        assert 'callback' not in related


class TestJobTemplateSerializerGetSummaryFields():
    def test__recent_jobs(self, mocker, job_template, jobs):

        job_template.unifiedjob_unified_jobs = mocker.MagicMock(**{
            'non_polymorphic.return_value': mocker.MagicMock(**{
                'only.return_value': mocker.MagicMock(**{
                    'order_by.return_value': jobs
                })
            })
        })

        serializer = JobTemplateSerializer()
        recent_jobs = serializer._recent_jobs(job_template)

        job_template.unifiedjob_unified_jobs.non_polymorphic.assert_called_once_with()
        job_template.unifiedjob_unified_jobs.non_polymorphic().only().order_by.assert_called_once_with('-created')
        assert len(recent_jobs) == 10
        for x in jobs[:10]:
            assert recent_jobs == [{'id': x.id, 'status': x.status, 'finished': x.finished} for x in jobs[:10]]

    def test_survey_spec_exists(self, test_get_summary_fields, mocker, job_template):
        job_template.survey_spec = {'name': 'blah', 'description': 'blah blah'}
        test_get_summary_fields(JobTemplateSerializer, job_template, 'survey')

    def test_survey_spec_absent(self, get_summary_fields_mock_and_run, job_template):
        job_template.survey_spec = None
        summary = get_summary_fields_mock_and_run(JobTemplateSerializer, job_template)
        assert 'survey' not in summary

    def test_copy_edit_standard(self, mocker, job_template_factory):
        """Verify that the exact output of the access.py methods
        are put into the serializer user_capabilities"""

        jt_obj = job_template_factory('testJT', project='proj1', persisted=False).job_template
        jt_obj.admin_role = Role(id=9, role_field='admin_role')
        jt_obj.execute_role = Role(id=8, role_field='execute_role')
        jt_obj.read_role = Role(id=7, role_field='execute_role')
        user = User(username="auser")
        serializer = JobTemplateSerializer(job_template)
        serializer.show_capabilities = ['copy', 'edit']
        serializer._summary_field_labels = lambda self: []
        serializer._recent_jobs = lambda self: []
        request = APIRequestFactory().get('/api/v2/job_templates/42/')
        request.user = user
        view = JobTemplateDetail()
        view.request = request
        view.kwargs = {}
        serializer.context['view'] = view

        with mocker.patch("awx.api.serializers.role_summary_fields_generator", return_value='Can eat pie'):
            with mocker.patch("awx.main.access.JobTemplateAccess.can_change", return_value='foobar'):
                with mocker.patch("awx.main.access.JobTemplateAccess.can_copy", return_value='foo'):
                    with mock.patch.object(jt_obj.__class__, 'get_deprecated_credential', return_value=None):
                        response = serializer.get_summary_fields(jt_obj)

        assert response['user_capabilities']['copy'] == 'foo'
        assert response['user_capabilities']['edit'] == 'foobar'


class TestJobTemplateSerializerValidation(object):
    good_extra_vars = ["{\"test\": \"keys\"}", "---\ntest: key"]
    bad_extra_vars = ["{\"test\": \"keys\"", "---\ntest: [2"]

    def test_validate_extra_vars(self):
        serializer = JobTemplateSerializer()
        for ev in self.good_extra_vars:
            serializer.validate_extra_vars(ev)
        for ev in self.bad_extra_vars:
            with pytest.raises(serializers.ValidationError):
                serializer.validate_extra_vars(ev)
