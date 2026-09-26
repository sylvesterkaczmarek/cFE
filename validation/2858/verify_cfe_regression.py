"""Compare inherited sanitizer failure, then verify the changed paths independently."""
from pathlib import Path
import os
import re
import subprocess

r=Path('/tmp/cfs/cfe')
b=Path('/tmp/cfs/build/native/default_cpu1')
out=Path(os.environ['EVIDENCE_DIR'])
source=Path(os.environ['GITHUB_WORKSPACE'])/'source'
env=os.environ.copy()
env.update(ASAN_OPTIONS='detect_leaks=1',UBSAN_OPTIONS='halt_on_error=1')

def run(name,args,allowed=(0,)):
    p=subprocess.run(args,text=True,errors='replace',capture_output=True,env=env)
    text=p.stdout+p.stderr
    (out/(name+'.log')).write_text(text)
    assert p.returncode in allowed,(name,p.returncode,text[-3500:])
    print(name,'exit',p.returncode,flush=True)
    return text

def build(name):
    # Remove obsolete instrumentation data between variants; source is never excluded.
    for p in b.rglob('*.gcda'):
        p.unlink()
    run(name,['cmake','--build',str(b),'--target','coverage-tbl-ALL-testrunner','coverage-fs-ALL-testrunner','-j4'])

def getfn(s,name):
    m=re.search(r'(?m)^(?:static )?(?:CFE_Status_t|void|int32|bool)\s+'+name+r'\s*\(',s)
    assert m,name
    a=m.start();brace=s.index('{',m.end());n=1;e=brace+1
    while n:
        if s[e]=='{':n+=1
        elif s[e]=='}':n-=1
        e+=1
    return a,e,s[a:e]

def replacefn(s,name,new):
    a,e,_=getfn(s,name)
    return s[:a]+new+s[e:]

def focus(name):
    run(name+'-fs',['ctest','--test-dir',str(b),'--no-tests=error','-V','-R','^coverage-fs-ALL$'])
    run(name+'-build',['python3',str(out/'build_cfe_integration.py')])
    run(name+'-snapshots',['/tmp/cfe-integration/table-focused'])
    run(name+'-integration',['/tmp/cfe-integration/integration'])

# The full uninstrumented suites ran before this step. Under GCC 13 UBSan,
# TaskInit's pre-existing null-message fixture fails before any snapshot tests.
build('sanitizer-build')
full=['ctest','--test-dir',str(b),'--no-tests=error','-V','-R','^(coverage-tbl-|coverage-fs)']
fixed_text=run('full-sanitizer-current',full,(8,))
pattern=r'cfe_tbl_dispatch\.c:\d+:\d+: runtime error: member access within null pointer'
assert re.search(pattern,fixed_text),fixed_text[-4000:]
paths=subprocess.check_output(['git','-C',str(source),'diff','--name-only','HEAD^','HEAD'],text=True).splitlines()
fixed_files={p:(r/p).read_bytes() for p in paths}
try:
    for p in paths:
        old=subprocess.run(['git','-C',str(source),'show','HEAD^:'+p],capture_output=True)
        if old.returncode==0:
            (r/p).write_bytes(old.stdout)
        else:
            (r/p).unlink()
    build('untouched-upstream-build')
    base_text=run('full-sanitizer-untouched-upstream',full,(8,))
    assert re.search(pattern,base_text),base_text[-4000:]
    print('The full TBL sanitizer failure reproduces on untouched upstream in TaskInit, before snapshot tests.',flush=True)
finally:
    for p,data in fixed_files.items():
        (r/p).write_bytes(data)

build('restored-current-build')
focus('current-sanitized')

dump=r/'modules/tbl/fsw/src/cfe_tbl_dump.c'
fixed=dump.read_text()
original=(out/'original-cfe-tbl-dump.c').read_text()
try:
    oldwrite=getfn(original,'CFE_TBL_WriteSnapshotToFile')[2].replace('const CFE_TBL_DumpControl_t','CFE_TBL_DumpControl_t')
    helper=getfn(original,'CFE_TBL_TxnOpenTableDumpFile')[2]
    mutant=replacefn(fixed,'CFE_TBL_WriteSnapshotToFile',helper+'\n\n'+oldwrite)
    mutant=replacefn(mutant,'CFE_TBL_TableDumpExecuteBackground',getfn(original,'CFE_TBL_TableDumpExecuteBackground')[2])
    for name in ['CFE_TBL_WriteSnapshotHeader','CFE_TBL_SnapshotDataGetter','CFE_TBL_SnapshotEventHandler']:
        mutant=replacefn(mutant,name,'')
    dump.write_text(mutant)
    build('original-synchronous-build')
    run('original-synchronous-runner-build',['python3',str(out/'build_cfe_integration.py')])
    text=run('original-synchronous-regression',['/tmp/cfe-integration/table-focused'],(1,))
    failures=[line for line in text.splitlines() if '[ FAIL]' in line]
    assert any('OS_write()' in line or 'BackgroundFileDumpRequest' in line for line in failures)
    print('Original synchronous path detected by',len(failures),'assertions.',flush=True)
finally:
    dump.write_text(fixed)

fs=r/'modules/fs/fsw/src/cfe_fs_api.c'
fixedfs=fs.read_text()
try:
    mutant='''CFE_Status_t CFE_FS_WriteHeaderFromBuffer(osal_id_t FileDes, const CFE_FS_Header_t *Hdr)
{
    CFE_FS_Header_t Copy = *Hdr;
    return CFE_FS_WriteHeader(FileDes, &Copy);
}'''
    fs.write_text(replacefn(fixedfs,'CFE_FS_WriteHeaderFromBuffer',mutant))
    build('restamping-build')
    run('restamping-runner-build',['python3',str(out/'build_cfe_integration.py')])
    text=run('restamping-regression',['/tmp/cfe-integration/integration'],(1,))
    assert 'Header.TimeSeconds' in text and 'Header.ApplicationID' in text
finally:
    fs.write_text(fixedfs)

build('final-restored-build')
focus('final-restored-sanitized')
for p,data in fixed_files.items():
    assert (r/p).read_bytes()==data,p
print('Final restored FS, all six snapshot groups, and four integrated groups pass under address/undefined sanitizers and leak detection.',flush=True)
