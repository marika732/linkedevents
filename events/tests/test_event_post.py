# -*- coding: utf-8 -*-
from datetime import timedelta

import pytest
from django.utils import timezone, translation
from .utils import versioned_reverse as reverse

from events.tests.utils import assert_event_data_is_equal
from .conftest import DATETIME
from events.models import Event
from django.conf import settings


@pytest.fixture
def list_url():
    return reverse('event-list')


# === util methods ===

def create_with_post(api_client, event_data, data_source=None):
    create_url = reverse('event-list')
    if data_source:
        create_url += '?api_key=' + data_source.api_key

    # save with post
    response = api_client.post(create_url, event_data, format='json')
    assert response.status_code == 201, str(response.content)

    # double-check with get
    resp2 = api_client.get(response.data['@id'])
    assert resp2.status_code == 200, str(response.content)

    return resp2


# === tests ===

@pytest.mark.django_db
def test__create_a_minimal_event_with_post(api_client,
                                           minimal_event_dict,
                                           user):
    api_client.force_authenticate(user=user)
    response = create_with_post(api_client, minimal_event_dict)
    assert_event_data_is_equal(minimal_event_dict, response.data)


@pytest.mark.django_db
def test__a_non_user_cannot_create_an_event(api_client, minimal_event_dict):

    response = api_client.post(reverse('event-list'), minimal_event_dict, format='json')
    assert response.status_code == 401


@pytest.mark.django_db
def test__a_non_admin_cannot_create_an_event(api_client, minimal_event_dict, user):
    user.get_default_organization().admin_users.remove(user)
    api_client.force_authenticate(user)

    response = api_client.post(reverse('event-list'), minimal_event_dict, format='json')
    assert response.status_code == 403


@pytest.mark.django_db
def test__api_key_with_organization_can_create_an_event(api_client, minimal_event_dict, data_source, organization):

    data_source.owner = organization
    data_source.save()

    response = create_with_post(api_client, minimal_event_dict, data_source)
    assert_event_data_is_equal(minimal_event_dict, response.data)


@pytest.mark.django_db
def test__api_key_without_organization_cannot_create_an_event(api_client, minimal_event_dict, data_source):

    response = api_client.post(reverse('event-list') + '?api_key=' + data_source.api_key,
                               minimal_event_dict, format='json')
    assert response.status_code == 403


@pytest.mark.django_db
def test__unknown_api_key_cannot_create_an_event(api_client, minimal_event_dict):

    response = api_client.post(reverse('event-list') + '?api_key=unknown', format='json')
    assert response.status_code == 401


@pytest.mark.django_db
def test__empty_api_key_cannot_create_an_event(api_client, minimal_event_dict):

    response = api_client.post(reverse('event-list') + '?api_key=',
                               minimal_event_dict, format='json')
    assert response.status_code == 401


@pytest.mark.django_db
def test__cannot_create_an_event_ending_before_start_time(list_url,
                                                          api_client,
                                                          minimal_event_dict,
                                                          user):
    api_client.force_authenticate(user=user)
    minimal_event_dict['end_time'] = (timezone.now() + timedelta(days=1)).isoformat()
    minimal_event_dict['start_time'] = (timezone.now() + timedelta(days=2)).isoformat()
    response = api_client.post(list_url, minimal_event_dict, format='json')
    assert response.status_code == 400
    assert 'end_time' in response.data


@pytest.mark.django_db
def test__create_a_draft_event_without_location_and_keyword(list_url,
                                                            api_client,
                                                            minimal_event_dict,
                                                            user):
    api_client.force_authenticate(user=user)
    minimal_event_dict.pop('location')
    minimal_event_dict.pop('keywords')
    minimal_event_dict['publication_status'] = 'draft'
    response = create_with_post(api_client, minimal_event_dict)
    assert_event_data_is_equal(minimal_event_dict, response.data)

    # the drafts should not be visible to unauthorized users
    api_client.logout()
    resp2 = api_client.get(response.data['@id'])
    assert '@id' not in resp2.data

@pytest.mark.django_db
def test__cannot_create_a_draft_event_without_a_name(list_url,
                                                               api_client,
                                                               minimal_event_dict,
                                                               user):
    api_client.force_authenticate(user=user)
    minimal_event_dict.pop('name')
    minimal_event_dict['publication_status'] = 'draft'
    response = api_client.post(list_url, minimal_event_dict, format='json')
    assert response.status_code == 400
    assert 'name' in response.data


@pytest.mark.django_db
def test__cannot_publish_an_event_without_location(list_url,
                                                               api_client,
                                                               minimal_event_dict,
                                                               user):
    api_client.force_authenticate(user=user)
    minimal_event_dict.pop('location')
    response = api_client.post(list_url, minimal_event_dict, format='json')
    assert response.status_code == 400
    assert 'location' in response.data


@pytest.mark.django_db
def test__cannot_publish_an_event_without_keywords(list_url,
                                                               api_client,
                                                               minimal_event_dict,
                                                               user):
    api_client.force_authenticate(user=user)
    minimal_event_dict.pop('keywords')
    response = api_client.post(list_url, minimal_event_dict, format='json')
    assert response.status_code == 400
    assert 'keywords' in response.data


@pytest.mark.django_db
def test__create_a_complex_event_with_post(api_client,
                                           complex_event_dict,
                                           user):
    api_client.force_authenticate(user=user)
    response = create_with_post(api_client, complex_event_dict)
    assert_event_data_is_equal(complex_event_dict, response.data)


@pytest.mark.django_db
def test__autopopulated_fields_at_create(
        api_client, minimal_event_dict, user, user2, other_data_source, organization, organization2):

    # create an event
    api_client.force_authenticate(user=user)
    response = create_with_post(api_client, minimal_event_dict)

    event = Event.objects.get(id=response.data['id'])
    assert event.created_by == user
    assert event.last_modified_by == user
    assert event.created_time is not None
    assert event.last_modified_time is not None
    assert event.data_source.id == settings.SYSTEM_DATA_SOURCE_ID
    assert event.publisher == organization


# the following values may not be posted
@pytest.mark.django_db
@pytest.mark.parametrize("non_permitted_input,non_permitted_response", [
    ({'id': 'not_allowed:1'}, 400), # may not fake id
    ({'data_source': 'theotherdatasourceid'}, 400),  # may not fake data source
    ({'publisher': 'test_organization2'}, 400),  # may not fake organization
])
def test__non_editable_fields_at_create(api_client, minimal_event_dict, list_url, user,
                              non_permitted_input, non_permitted_response):
    api_client.force_authenticate(user)

    minimal_event_dict.update(non_permitted_input)

    response = api_client.post(list_url, minimal_event_dict, format='json')
    assert response.status_code == non_permitted_response
    if non_permitted_response >= 400:
        # check that there is an error message for the corresponding field
        assert list(non_permitted_input)[0] in response.data


# location field is used for JSONLDRelatedField tests
@pytest.mark.django_db
@pytest.mark.parametrize("ld_input,ld_expected", [
    ({'location': {'@id': '/v1/place/test%20location/'}}, 201),
    ({'location': {'@id': ''}}, 400),  # field required
    ({'location': {'foo': 'bar'}}, 400),  # incorrect json
    ({'location': '/v1/place/test%20location/'}, 400),  # incorrect json
    ({'location': 7}, 400),  # incorrect json
    ({'location': None}, 400),  # cannot be null
    ({}, 400),  # field required
])
def test__jsonld_related_field(api_client, minimal_event_dict, list_url, place, user, ld_input, ld_expected):
    api_client.force_authenticate(user)

    del minimal_event_dict['location']
    minimal_event_dict.update(ld_input)

    response = api_client.post(list_url, minimal_event_dict, format='json')
    assert response.status_code == ld_expected
    if ld_expected >= 400:
        # check that there is a error message for location field
        assert 'location' in response.data


@pytest.mark.django_db
def test_start_time_and_end_time_validation(api_client, minimal_event_dict, user):
    api_client.force_authenticate(user)

    minimal_event_dict['start_time'] = timezone.now() - timedelta(days=2)
    minimal_event_dict['end_time'] = timezone.now() - timedelta(days=1)

    with translation.override('en'):
        response = api_client.post(reverse('event-list'), minimal_event_dict, format='json')
    assert response.status_code == 400
    assert 'Start time cannot be in the past.' in response.data['start_time']
    assert 'End time cannot be in the past.' in response.data['end_time']
