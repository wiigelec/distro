#!/usr/bin/env python3
"""B1.2 read-only audit of host-executable cross-Binutils and target linker defaults."""
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

TARGET = 'x86_64-unknown-linux-gnu'

def run(argv, timeout=25):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False, env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        return {'returncode':p.returncode, 'stdout':p.stdout[:250000], 'stderr':p.stderr[:8000]}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'error':type(e).__name__, 'message':str(e)[:400]}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
    return h.hexdigest()

def audit(work):
    prefix=work/'prefix'/'bin'
    tools={}
    for short in ('as','ld'):
        path=prefix/(TARGET+'-'+short)
        rec={'path':str(path),'exists':path.is_file()}
        if path.is_file():
            rec['sha256']=digest(path)
            rec['elf_header']=run(['/usr/bin/readelf','-h',str(path)])
            rec['program_headers']=run(['/usr/bin/readelf','-lW',str(path)])
            rec['dynamic_section']=run(['/usr/bin/readelf','-dW',str(path)])
            rec['version']=run([str(path),'--version'])
            rec['interpreter']=re.findall(r'Requesting program interpreter: ([^\]]+)',rec['program_headers'].get('stdout',''))
            rec['needed']=re.findall(r'\(NEEDED\).*?\[([^\]]+)\]',rec['dynamic_section'].get('stdout',''))
            rec['rpath_runpath']=re.findall(r'\((?:RPATH|RUNPATH)\).*?\[([^\]]+)\]',rec['dynamic_section'].get('stdout',''))
            if short=='ld':
                rec['emulations']=run([str(path),'-V'])
                rec['sysroot']=run([str(path),'--print-sysroot'])
                verbose=run([str(path),'--verbose'])
                rec['verbose_command']={'returncode':verbose.get('returncode'), 'stderr':verbose.get('stderr','')}
                rec['search_dirs']=re.findall(r'SEARCH_DIR\("([^\"]+)"\)',verbose.get('stdout',''))
                rec['default_script_host_path_hits']=sorted(set(re.findall(r'/(?:usr|lib|opt|home)/[^\s;\)\"]+',verbose.get('stdout',''))))[:100]
        tools[short]=rec
    object_path=work/'check-reloc.o'
    obj={'path':str(object_path),'exists':object_path.is_file()}
    if obj['exists']:
        obj['sha256']=digest(object_path)
        obj['header']=run(['/usr/bin/readelf','-h',str(object_path)])
        obj['symbols']=run(['/usr/bin/readelf','-sW',str(object_path)])
    checks={'assembler_exists':tools['as']['exists'],'linker_exists':tools['ld']['exists'],
            'tools_are_elf':all('ELF Header:' in x.get('elf_header',{}).get('stdout','') for x in tools.values()),
            'target_object_exists':obj['exists'],
            'target_object_x86_64': 'Advanced Micro Devices X86-64' in obj.get('header',{}).get('stdout',''),
            'linker_search_dirs_observed':bool(tools['ld'].get('search_dirs')),
            'linker_emulations_observed':bool(tools['ld'].get('emulations',{}).get('stdout'))}
    return {'schema_version':1,'stage':'B1.2-binutils-audit','status':'observed' if all(checks.values()) else 'incomplete',
        'workspace':str(work),'host':{'uid':os.geteuid()},'tools':tools,'target_object':obj,'gates':checks,
        'interpretation':{'host_executable_dependencies':'ELF interpreter/NEEDED entries of cross-tools are permitted host-runtime dependencies during bootstrap; their presence is not automatically target leakage.',
        'target_linker_paths':'SEARCH_DIR entries are potential target-output inputs; absolute host paths must be resolved against intended sysroot before native cross-linking.',
        'limitations':['Read-only structural inspection, not a linker hermeticity proof','Does not resolve transitive runtime libraries or execute a target libc link','Does not authenticate upstream source signatures','No compiler/sysroot exists yet']}}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--workspace',type=Path,required=True)
    ap.add_argument('--out',type=Path)
    args=ap.parse_args()
    result=audit(args.workspace.resolve())
    content=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(content)
    else:print(content,end='')
    return 0 if result['status']=='observed' else 1
if __name__=='__main__':raise SystemExit(main())
