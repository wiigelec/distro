import importlib.util
import pathlib
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'src/bootstrap/dependency_closure.py'
spec = importlib.util.spec_from_file_location('dependency_closure', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inventory():
    return {'schema_version': 1, 'roots': ['compiler'], 'packages': [
        {'distro_name': 'compiler', 'build_dependencies': ['libc'], 'runtime_dependencies': ['libc']},
        {'distro_name': 'libc', 'build_dependencies': [], 'runtime_dependencies': []}]}


class ClosureTests(unittest.TestCase):
    def test_closed_inventory(self):
        self.assertEqual(module.resolve_closure(inventory())['packages'], ['compiler', 'libc'])

    def test_missing_dependency(self):
        data = inventory()
        data['packages'][0]['build_dependencies'].append('binutils')
        with self.assertRaises(module.ClosureError):
            module.resolve_closure(data)

    def test_missing_root(self):
        data = inventory()
        data['roots'] = ['systemd']
        with self.assertRaises(module.ClosureError):
            module.resolve_closure(data)

    def test_unreachable_inventory_entry(self):
        data = inventory()
        data['packages'].append({'distro_name': 'unreferenced', 'build_dependencies': [], 'runtime_dependencies': []})
        with self.assertRaises(module.ClosureError):
            module.resolve_closure(data)

    def test_unreviewed_cycle(self):
        data = inventory()
        data['packages'][1]['build_dependencies'] = ['compiler']
        with self.assertRaises(module.ClosureError):
            module.resolve_closure(data)

    def test_reviewed_cycle(self):
        data = inventory()
        data['packages'][1]['build_dependencies'] = ['compiler']
        data['reviewed_cycle_breaks'] = [{'packages': ['compiler', 'libc'], 'reason': 'staged compiler bootstrap'}]
        self.assertEqual(module.resolve_closure(data)['reviewed_cycles'], [['compiler', 'libc']])

    def test_self_cycle_requires_review(self):
        data = inventory()
        data['packages'][1]['runtime_dependencies'] = ['libc']
        with self.assertRaises(module.ClosureError):
            module.resolve_closure(data)

    def test_duplicate_dependency_rejected(self):
        data = inventory()
        data['packages'][0]['build_dependencies'] = ['libc', 'libc']
        with self.assertRaises(module.ClosureError):
            module.resolve_closure(data)


if __name__ == '__main__':
    unittest.main()
