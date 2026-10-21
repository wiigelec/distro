"""Validate proposed native package build procedures without executing them.

This is an authoring/inspection contract, not an M2 execution engine or
an assertion that the selected native package closure is complete.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re

class NativeRecipeError(ValueError):
    pass

IDENT = re.compile(r"[a-z][a-z0-9+.-]*\Z")
ALLOWED = {'source', 'build', 'destdir', 'prefix', 'jobs', 'target'}


def validate(recipe: dict) -> dict:
    if not isinstance(recipe, dict) or recipe.get('schema_version') != 1:
        raise NativeRecipeError('recipe schema must be 1')
    name = recipe.get('name')
    owner = recipe.get('source_package')
    if any(not isinstance(x, str) or not IDENT.fullmatch(x) for x in (name, owner)):
        raise NativeRecipeError('invalid package or source-owner identity')
    if recipe.get('review_status') != 'unreviewed':
        raise NativeRecipeError('draft recipes must explicitly remain unreviewed')
    if recipe.get('execution') != 'native-chroot':
        raise NativeRecipeError('native procedures must be declared for native chroot execution')
    for kind in ('build_dependencies', 'runtime_dependencies'):
        deps = recipe.get(kind)
        if not isinstance(deps, list) or len(set(deps)) != len(deps) or any(not isinstance(v,str) or not IDENT.fullmatch(v) for v in deps):
            raise NativeRecipeError(kind + ' must contain unique package identities')
        if name in deps:
            raise NativeRecipeError('self-dependency must be documented as a cycle break')
    steps = recipe.get('steps')
    if not isinstance(steps, list) or not steps:
        raise NativeRecipeError('nonempty native build procedure required')
    seen = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'name', 'argv'}:
            raise NativeRecipeError('every step requires name and argv only')
        label, argv = step['name'], step['argv']
        if not isinstance(label,str) or not IDENT.fullmatch(label) or label in seen:
            raise NativeRecipeError('invalid or duplicate procedure step')
        seen.add(label)
        if not isinstance(argv,list) or not argv or any(not isinstance(x,str) or not x or '\x00' in x or '\n' in x for x in argv):
            raise NativeRecipeError('procedure argv must be nonempty literal strings')
        if argv[0] in ('sh', 'bash', '/bin/sh', '/bin/bash', 'env', '/usr/bin/env'):
            raise NativeRecipeError('implicit shell execution is forbidden')
        for arg in argv:
            # Only explicit fixed substitutions; no shell expansions or command text.
            if '$' in arg or '`' in arg or ';' in arg or '&&' in arg or '||' in arg:
                raise NativeRecipeError('shell syntax is not a native recipe interface')
            for token in re.findall(r'\{([^{}]+)\}', arg):
                if token not in ALLOWED:
                    raise NativeRecipeError('unsupported recipe substitution: ' + token)
            if arg.count('{') != arg.count('}'):
                raise NativeRecipeError('unbalanced substitutions')
    required = recipe.get('required_outputs')
    if not isinstance(required,list) or not required or len(set(required)) != len(required):
        raise NativeRecipeError('explicit required output list needed')
    for dest in required:
        if not isinstance(dest,str) or not dest.startswith('/usr/') or '..' in Path(dest).parts or '{' in dest or '$' in dest:
            raise NativeRecipeError('required output must be a fixed path under /usr')
    return {'name':name,'source_package':owner,'steps':len(steps),
            'build_dependencies':recipe['build_dependencies'],
            'runtime_dependencies':recipe['runtime_dependencies'],'review_status':'unreviewed'}


def main() -> int:
    parser=argparse.ArgumentParser(description='Inspect native package build recipes without running them')
    parser.add_argument('recipes', nargs='+', type=Path)
    args=parser.parse_args()
    for path in args.recipes:
        result=validate(json.loads(path.read_text(encoding='utf-8')))
        print(json.dumps({'file':str(path), **result},sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
