import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mobile',ROOT/'mobile.py')
mobile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile)


class MobileTests(unittest.TestCase):
    def test_detects_only_private_hardware_address(self):
        result=types.SimpleNamespace(returncode=0,stdout=json.dumps([{'name':'WLAN','ip':['10.1.2.3']},{'name':'VPN','ip':'198.18.0.1'}]))
        with patch.object(mobile.subprocess,'run',return_value=result):
            self.assertEqual(mobile.discover_lan(),'10.1.2.3')

    def test_discovery_without_network_has_clear_error(self):
        result=types.SimpleNamespace(returncode=0,stdout='[]')
        with patch.object(mobile.subprocess,'run',return_value=result):
            with self.assertRaises(RuntimeError):
                mobile.discover_lan()

    def test_pin_is_persistent_and_not_regenerated(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.test-work') as temp:
            with patch.object(mobile,'ROOT',Path(temp)):
                first=mobile.load_pin()
                self.assertEqual(len(first),10)
                self.assertTrue(first.isdigit())
                self.assertEqual(first,mobile.load_pin())
