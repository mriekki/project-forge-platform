import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / 'deploy-from-wsl.py'
spec = importlib.util.spec_from_file_location('portfolio_deploy', SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class RemoteDeployTests(unittest.TestCase):
    def test_interval(self):
        for v in ('5m','15m','1h','24h','86400s'):
            self.assertTrue(mod.interval_valid(v), v)
        for v in ('0m','4m','2d','15m;touch /tmp/wrong','999999999999999d',''):
            self.assertFalse(mod.interval_valid(v), v)

    def test_strict_options(self):
        p = {'identityFile': '/home/test/.ssh/id_pf',
             'knownHostsFile':'/home/test/.ssh/pf_known_hosts',
             'sshAlias':'stable-pf','port':22,'user':'operator','hostName':'production.example'}
        args = mod.ssh_args(p, 'true')
        for text in ('StrictHostKeyChecking=yes','IdentitiesOnly=yes','GlobalKnownHostsFile=none',
                     'ForwardAgent=no','PasswordAuthentication=no','BatchMode=yes','HostKeyAlias=stable-pf'):
            self.assertIn(text,args)
        self.assertEqual(args[-2:], ['operator@production.example','true'])
        self.assertNotIn('accept-new',args)

    def test_profile_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            ident = p/'key'; trust = p/'known_hosts'
            ident.write_text('test'); trust.write_text('test')
            obj = {'targetName':'production','hostName':'prod.example', 'sshAlias':'pf-prod',
                   'user':'mark','port':22,'identityFile':str(ident),
                   'knownHostsFile':str(trust),'addressOverride':None}
            (p/'production.json').write_text(json.dumps(obj))
            self.assertEqual(mod.profile_load('production',p)['hostName'],'prod.example')
            (p/'production.json').write_text(json.dumps(dict(obj, targetName='other')))
            with self.assertRaises(mod.DeploymentError):
                mod.profile_load('production',p)
            (p/'production.json').write_text(json.dumps(dict(obj, addressOverride='-oProxyCommand=shell')))
            with self.assertRaises(mod.DeploymentError):
                mod.profile_load('production',p)

    def test_archive_contains_only_explicit_files(self):
        archive = mod.make_archive()
        with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as tar:
            names=tar.getnames()
            self.assertEqual(len(names),len(mod.BUNDLE_FILES))
            self.assertTrue(all(name.startswith('project-forge-portfolio-sync/') for name in names))
            self.assertTrue(all('.git/' not in name and 'token' not in name for name in names))

    def test_failed_preflight_prevents_upload(self):
        with patch.object(mod, 'check_tools', side_effect=mod.DeploymentError('no sudo')), \
                patch.object(mod, 'make_archive') as archive, \
                patch.object(mod, 'run_remote') as remote:
            with self.assertRaises(mod.DeploymentError):
                mod.install({}, '15m')
            archive.assert_not_called()
            remote.assert_not_called()

    def test_install_calls_all_steps_and_cleanup(self):
        calls=[]
        def run(profile, command, *, stdin=None, interactive=False, capture=False):
            calls.append((command,stdin is not None,interactive))
            return '/tmp/pf-portfolio-sync.ABC12345' if command.startswith('mktemp') else ''
        with patch.object(mod, 'check_tools'), patch.object(mod, 'run_remote',side_effect=run):
            mod.install({}, '15m')
        self.assertEqual(len(calls), 6)
        self.assertEqual(calls[1][1], True)
        self.assertEqual(calls[3][2], True)
        self.assertTrue(calls[-1][0].startswith('rm -rf -- /tmp/pf-portfolio-sync.'))

    def test_unexpected_temp_path_blocks_transfer(self):
        with patch.object(mod, 'check_tools'), \
                patch.object(mod,'run_remote',return_value='/tmp/other'), \
                patch.object(mod,'make_archive') as archive:
            with self.assertRaises(mod.DeploymentError):
                mod.install({},'15m')
            archive.assert_not_called()

if __name__=='__main__':
    unittest.main()
