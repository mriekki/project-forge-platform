import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / 'sync.py'
spec = importlib.util.spec_from_file_location('portfolio_sync', SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
CFG = {
    'owner': 'mriekki', 'project_number': 1, 'project_name': 'Project Forge Portfolio',
    'repositories': ['mriekki/project-forge-platform', 'mriekki/project-forge-core'],
    'exclude_title_prefixes': ['[project-forge-release]', '[project-forge-publish]'],
}

def issue(repo, num):
    return f'https://github.com/mriekki/{repo}/issues/{num}'

class SyncTests(unittest.TestCase):
    def test_config_load_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'config.json'
            p.write_text(json.dumps(CFG))
            self.assertEqual(len(mod.settings(p)['repositories']), 2)
            p.write_text(json.dumps(dict(CFG, repositories=[CFG['repositories'][0]] * 2)))
            with self.assertRaises(mod.SyncError):
                mod.settings(p)

    def test_project_private_verified(self):
        def fake(*cmd):
            if cmd[:2] == ('api','user'):
                return 'mriekki'
            return json.dumps({'data': {'user': {'projectV2': {
                'public': False, 'title': CFG['project_name'], 'number': 1,
                'url': 'https://github.com/users/mriekki/projects/1',
                'repositories': {'nodes': [{'nameWithOwner': r} for r in CFG['repositories']],
                                 'pageInfo': {'hasNextPage': False}}
            }}}})
        with patch.object(mod, 'gh', side_effect=fake):
            self.assertEqual(mod.verify_project(CFG)['public'], False)

    def test_public_fails_closed(self):
        with patch.object(mod, 'gh', return_value='mriekki'), patch.object(mod, 'gh_json', return_value={
            'data': {'user': {'projectV2': {'public': True}}}}):
            with self.assertRaisesRegex(mod.SyncError,'PRIVATE'):
                mod.verify_project(CFG)

    def test_existing_item_dedupes_and_detects_truncation(self):
        url = issue('project-forge-core',86)
        with patch.object(mod, 'gh_json', return_value={'items':[{'content':{'url':url}}], 'totalCount':1}):
            self.assertEqual(mod.fetch_existing(CFG), {url})
        with patch.object(mod, 'gh_json', return_value={'items':[], 'totalCount':5}):
            with self.assertRaisesRegex(mod.SyncError,'pagination'):
                mod.fetch_existing(CFG)

    def test_skips_release_issues_and_preserves_real_issues(self):
        p = 'project-forge-platform'; c = 'project-forge-core'
        def fake(*cmd):
            if 'mriekki/' + p in cmd:
                return [{'url':issue(p,291),'title':'Release gate: distribute Feedback'},
                        {'url':issue(p,285),'title':'[project-forge-release] 4.27.1'},
                        {'url':issue(p,294),'title':'Project Portfolio sync'}]
            return [{'url':issue(c,86),'title':'Cross-repository tracking'}]
        with patch.object(mod, 'gh_json',side_effect=fake):
            self.assertEqual(mod.fetch_candidates(CFG),[issue(p,291),issue(p,294),issue(c,86)])

    def test_one_repository_failure_means_zero_writes(self):
        p = 'project-forge-platform'
        def fetch(cfg):
            raise mod.SyncError('source unavailable')
        with patch.object(mod, 'verify_project', return_value={'url':'https://github.com/users/mriekki/projects/1'}), \
                patch.object(mod, 'fetch_existing', return_value={}), \
                patch.object(mod, 'fetch_candidates',side_effect=fetch), \
                patch.object(mod, 'gh') as writer:
            with self.assertRaises(mod.SyncError):
                mod.synchronize(CFG)
            writer.assert_not_called()

    def test_only_add_missing_issue_and_no_field_updates(self):
        u1 = issue('project-forge-core', 86)
        u2 = issue('project-forge-platform', 294)
        with patch.object(mod, 'verify_project', return_value={'url':'https://github.com/users/mriekki/projects/1'}), \
                patch.object(mod, 'fetch_existing', return_value={u1}), \
                patch.object(mod, 'fetch_candidates', return_value=[u1,u2]), \
                patch.object(mod, 'gh',return_value='{}') as writer:
            result = mod.synchronize(CFG)
            self.assertEqual((result['added'],result['already_present'],result['failures']), (1,1,[]))
            self.assertEqual(writer.call_count, 1)
            self.assertIn(u2, writer.call_args.args)
            self.assertIn('item-add', writer.call_args.args)

    def test_dry_run_no_writes(self):
        with patch.object(mod, 'verify_project', return_value={'url':'https://github.com/users/mriekki/projects/1'}), \
                patch.object(mod, 'fetch_existing', return_value=set()), \
                patch.object(mod, 'fetch_candidates', return_value=[issue('project-forge-core',86)]), \
                patch.object(mod, 'gh') as writer:
            result = mod.synchronize(CFG, dry_run=True)
            self.assertEqual(result['missing'],1)
            self.assertEqual(result['added'],0)
            writer.assert_not_called()

    def test_unexpected_repo_url_fails(self):
        with patch.object(mod, 'gh_json',return_value=[{'url':issue('fake-other',23),'title':'Issue'}]):
            with self.assertRaisesRegex(mod.SyncError,'Unexpected Issue URL'):
                mod.fetch_candidates(CFG)

if __name__ == '__main__':
    unittest.main()
