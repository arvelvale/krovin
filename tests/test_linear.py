from types import SimpleNamespace
import pytest
from agent.tools.linear import LinearClient, linear_list_issues, linear_list_projects
from agent.tools.base import ToolError


def client(project=''):
    lc = LinearClient('test', 'DAY', project)
    lc._team = {'id': 'team-day'}
    lc._project_id = 'demo-id' if project else ''
    return lc


def test_project_filter_preserves_team_and_labels_results():
    lc = client()
    def gql(query, variables):
        assert variables['f'] == {'team': {'id': {'eq': 'team-day'}}, 'project': {'name': {'eqIgnoreCase': 'Pomodoro'}}}
        return {'issues': {'nodes': [{'identifier': 'DAY-301', 'title': '番茄钟应用', 'state': {'name': 'Todo'}, 'project': {'name': 'Pomodoro'}}]}}
    lc.gql = gql
    result = linear_list_issues({'project_name': 'Pomodoro'}, SimpleNamespace(linear=lc))
    assert 'DAY-301 [项目：Pomodoro]' in result
    assert 'DAY-299' not in result


def test_missing_project_does_not_fall_back():
    lc = client()
    calls = []
    def gql(query, variables):
        calls.append(variables)
        return {'issues': {'nodes': []}}
    lc.gql = gql
    result = linear_list_issues({'project_name': 'pomodora'}, SimpleNamespace(linear=lc))
    assert len(calls) == 1
    assert calls[0]['f']['project']['name']['eqIgnoreCase'] == 'pomodora'
    assert '不要用其它项目' in result


def test_project_filter_cannot_bypass_configured_scope():
    lc = client('演示项目')
    lc.gql = lambda *args: pytest.fail('不应请求其它项目')
    with pytest.raises(ToolError, match='仅允许访问'):
        linear_list_issues({'project_name': 'Pomodoro'}, SimpleNamespace(linear=lc))


def test_project_discovery_paginates_in_selected_team():
    lc = client()
    calls = []
    def gql(query, variables):
        calls.append(variables)
        end = variables['after'] is not None
        return {'team': {'projects': {'nodes': [{'name': 'Pomodoro' if end else '演示项目'}], 'pageInfo': {'hasNextPage': not end, 'endCursor': 'next'}}}}
    lc.gql = gql
    result = linear_list_projects({}, SimpleNamespace(linear=lc))
    assert 'Pomodoro' in result
    assert calls == [{'id': 'team-day', 'after': None}, {'id': 'team-day', 'after': 'next'}]
