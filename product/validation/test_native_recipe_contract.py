"""Native build recipe authoring contract tests (not build execution)."""
import json
from pathlib import Path
import sys
import unittest
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/bootstrap'))
from native_recipe_contract import NativeRecipeError, validate

class NativeRecipeContractTests(unittest.TestCase):
    def setUp(self):
        self.path=Path(__file__).resolve().parents[1]/'src/bootstrap/native-recipes'
        self.sample=json.loads((self.path/'bash.json').read_text())
    def test_draft_seed_recipes(self):
        for name in ('bash','coreutils','make'):
            with self.subTest(name=name):
                recipe=json.loads((self.path/(name+'.json')).read_text())
                self.assertEqual(validate(recipe)['name'],name)
    def test_review_status_cannot_be_silently_promoted(self):
        r=deepcopy(self.sample);r['review_status']='approved'
        with self.assertRaises(NativeRecipeError):validate(r)
    def test_shell_execution_rejected(self):
        r=deepcopy(self.sample);r['steps'][0]['argv']=['sh','-c','touch /host']
        with self.assertRaises(NativeRecipeError):validate(r)
    def test_missing_dependency_declarations_rejected(self):
        r=deepcopy(self.sample);del r['build_dependencies']
        with self.assertRaises(NativeRecipeError):validate(r)
    def test_unbounded_output_rejected(self):
        r=deepcopy(self.sample);r['required_outputs']=['/etc/passwd']
        with self.assertRaises(NativeRecipeError):validate(r)
    def test_bad_variable_rejected(self):
        r=deepcopy(self.sample);r['steps'][0]['argv'].append('{unreviewed_value}')
        with self.assertRaises(NativeRecipeError):validate(r)
    def test_direct_self_dependency_rejected(self):
        r=deepcopy(self.sample);r['runtime_dependencies'].append('bash')
        with self.assertRaises(NativeRecipeError):validate(r)

if __name__=='__main__':unittest.main()
