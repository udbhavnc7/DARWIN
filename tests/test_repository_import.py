"""Only HTTPS GitHub source at an approved pinned commit may execute."""
import json
from pathlib import Path

import pytest

from darwin.repository_catalog import SANCHAY_COMMIT, SANCHAY_REPOSITORY
from darwin.repository_import import (RepositoryError, RepositoryImporter, validate_ref,
                                      validate_repository_url)


def write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def sanchay_tree(root: Path) -> Path:
    write(root, 'web/package.json', json.dumps({
        'dependencies': {'react': '^19.3.1'}, 'devDependencies': {'vite': '^7.0.0'},
    }))
    write(root, 'web/src/utils/reporting.ts', '''
export function computeReportTotals() {}
export function computeCategorySpending() {}
export function computeCategoryBreakdown() {}
export function computePayeeBreakdown() {}
''')
    write(root, 'web/src/utils/money.ts', 'export function addMoney() { return 0; }')
    write(root, 'web/src/utils/categories.ts', 'export const CATEGORIES = [];')
    write(root, 'web/src/types/finance.ts', 'export type Transaction = { id: string };')
    write(root, 'web/src/components/ReportsTab.tsx', 'ReportsTab computes computeReportTotals.')
    write(root, 'web/src/data/persistence.ts', "localStorage.getItem('sanchay.local.v1');")
    return root


class FakeGit:
    def resolve(self, url, ref):
        return 'f' * 40


def test_repository_url_is_canonical_and_strict():
    repo = validate_repository_url('https://github.com/udbhavnc7/Sanchay.git/')
    assert repo.url == 'https://github.com/udbhavnc7/Sanchay'
    assert (repo.owner, repo.name) == ('udbhavnc7', 'Sanchay')


@pytest.mark.parametrize('url, code', [
    ('http://github.com/a/b', 'unsupported_scheme'),
    ('git@github.com:a/b.git', 'unsupported_scheme'),
    ('https://user:token@github.com/a/b', 'credentials_rejected'),
    ('https://gitlab.com/a/b', 'unsupported_host'),
    ('https://github.com/a/b?ref=main', 'invalid_repository'),
    ('https://github.com/a/b/tree/main', 'invalid_repository'),
    ('https://github.com/a', 'invalid_repository'),
    ('https://github.com/-a/b', 'invalid_repository'),
    ('https://github.com:8443/a/b', 'invalid_repository'),
])
def test_unsafe_urls_are_rejected(url, code):
    with pytest.raises(RepositoryError) as caught:
        validate_repository_url(url)
    assert caught.value.code == code


@pytest.mark.parametrize('ref', ['main', 'v1.2.3', 'feature/reporting-v2', 'a' * 40])
def test_safe_refs_are_accepted(ref):
    assert validate_ref(ref) == ref


@pytest.mark.parametrize('ref', ['-main', '/main', 'main/', 'main..x', 'a//b', 'main@{1}', 'x.lock'])
def test_unsafe_refs_are_rejected(ref):
    with pytest.raises(RepositoryError) as caught:
        validate_ref(ref)
    assert caught.value.code == 'invalid_ref'


def test_consent_is_required_before_any_download(tmp_path):
    importer = RepositoryImporter(cache_root=tmp_path / 'cache', git=FakeGit())
    with pytest.raises(RepositoryError) as caught:
        importer.inspect(SANCHAY_REPOSITORY, 'main', False)
    assert caught.value.code == 'consent_required'
    assert caught.value.status_code == 428


def test_pinned_source_is_classified_and_execution_is_allowed(tmp_path):
    source = sanchay_tree(tmp_path / 'source')
    importer = RepositoryImporter(
        cache_root=tmp_path / 'cache', git=FakeGit(),
        source_override={SANCHAY_REPOSITORY: source}, resolve_override=SANCHAY_COMMIT,
    )
    record = importer.inspect(SANCHAY_REPOSITORY, 'main', True)
    assert record['source']['commit_sha'] == SANCHAY_COMMIT
    assert record['source']['trusted'] is True
    assert record['execution_allowed'] is True
    assert record['project']['type'] == 'react_webview_local_app'
    assert record['supported_evaluations'][0]['adapter_id'] == 'sanchay-reporting-v1'
    assert record['_source_root'] == str(source.resolve())


def test_unpinned_revision_is_inspection_only(tmp_path):
    source = sanchay_tree(tmp_path / 'source')
    importer = RepositoryImporter(
        cache_root=tmp_path / 'cache', git=FakeGit(),
        source_override={SANCHAY_REPOSITORY: source}, resolve_override='e' * 40,
    )
    record = importer.inspect(SANCHAY_REPOSITORY, 'main', True)
    assert record['execution_allowed'] is False
    assert record['supported_evaluations'] == []
    assert record['evaluation_status'] == 'UNSUPPORTED_PROJECT'
    assert any('not the pinned, audited revision' in warning for warning in record['warnings'])


def test_unknown_repository_is_inspection_only_not_checkout_lab(tmp_path):
    source = tmp_path / 'source'
    write(source, 'README.md', '# An unrelated project')
    importer = RepositoryImporter(
        cache_root=tmp_path / 'cache', git=FakeGit(),
        source_override={'https://github.com/example/unknown': source},
        resolve_override='a' * 40,
    )
    record = importer.inspect('https://github.com/example/unknown', 'main', True)
    assert record['execution_allowed'] is False
    assert record['evaluation_status'] == 'UNSUPPORTED_PROJECT'
    assert any('No runnable optimization adapter' in warning for warning in record['warnings'])
