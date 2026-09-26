from pathlib import Path
import subprocess,re,os
root=Path('/tmp/cfs');r=root/'cfe';b=root/'build/native/default_cpu1';out=Path(os.environ.get('EVIDENCE_DIR', '/work'))
env=os.environ.copy();env.update(ASAN_OPTIONS='detect_leaks=1',UBSAN_OPTIONS='halt_on_error=1')
def run(name,args,allowed=(0,)):
 p=subprocess.run(args,text=True,errors='replace',capture_output=True,env=env)
 text=p.stdout+p.stderr;(out/(name+'.log')).write_text(text)
 assert p.returncode in allowed,(name,p.returncode,text[-2500:])
 print(name,'exit',p.returncode,flush=True);return text,p.returncode
def build(name):run(name,['cmake','--build',str(b),'--target','coverage-tbl-ALL-testrunner','coverage-fs-ALL-testrunner','-j4'])
def getfn(s,name):
 m=re.search(r'(?m)^(?:static )?(?:CFE_Status_t|void|int32|bool)\s+'+name+r'\s*\(',s);assert m,name
 a=m.start();brace=s.index('{',m.end());n=1;e=brace+1
 while n:
  if s[e]=='{':n+=1
  elif s[e]=='}':n-=1
  e+=1
 return a,e,s[a:e]
def replacefn(s,name,new):
 a,e,_=getfn(s,name);return s[:a]+new+s[e:]
build('formatted-build')
run('formatted-components',['ctest','--test-dir',str(b),'--no-tests=error','-V','-R','^(coverage-tbl-|coverage-fs)'])
dump=r/'modules/tbl/fsw/src/cfe_tbl_dump.c';fixed=dump.read_text();original=(out/'original-cfe-tbl-dump.c').read_text()
try:
 oldwrite=getfn(original,'CFE_TBL_WriteSnapshotToFile')[2].replace('const CFE_TBL_DumpControl_t','CFE_TBL_DumpControl_t')
 helper=getfn(original,'CFE_TBL_TxnOpenTableDumpFile')[2]
 mutant=replacefn(fixed,'CFE_TBL_WriteSnapshotToFile',helper+'\n\n'+oldwrite)
 mutant=replacefn(mutant,'CFE_TBL_TableDumpExecuteBackground',getfn(original,'CFE_TBL_TableDumpExecuteBackground')[2])
 for unused in ['CFE_TBL_WriteSnapshotHeader','CFE_TBL_SnapshotDataGetter','CFE_TBL_SnapshotEventHandler']:
  mutant=replacefn(mutant,unused,'')
 dump.write_text(mutant);build('original-synchronous-build')
 text,rc=run('original-synchronous-tests',['ctest','--test-dir',str(b),'--no-tests=error','-V','-R','^coverage-tbl-ALL$'],(8,))
 failures=[x for x in text.splitlines() if '[ FAIL]' in x]
 assert any('OS_write()' in x or 'BackgroundFileDumpRequest' in x for x in failures),failures
 print('Original synchronous path rejected by',len(failures),'assertions.',flush=True)
finally:dump.write_text(fixed)
build('restored-async-build')
run('restored-async-components',['ctest','--test-dir',str(b),'--no-tests=error','-V','-R','^(coverage-tbl-|coverage-fs)'])
fs=r/'modules/fs/fsw/src/cfe_fs_api.c';fixedfs=fs.read_text()
try:
 mutant='''CFE_Status_t CFE_FS_WriteHeaderFromBuffer(osal_id_t FileDes, const CFE_FS_Header_t *Hdr)
{
    CFE_FS_Header_t Copy = *Hdr;
    return CFE_FS_WriteHeader(FileDes, &Copy);
}'''
 fs.write_text(replacefn(fixedfs,'CFE_FS_WriteHeaderFromBuffer',mutant));build('restamping-header-build')
 run('restamping-integration-build',['python3',str(out/'build_cfe_integration.py')])
 text,rc=run('restamping-integration-tests',['/tmp/cfe-integration/integration'],(1,))
 assert 'Header.TimeSeconds' in text and 'Header.ApplicationID' in text
 print('Integrated check detects snapshot timestamp and producer restamping.',flush=True)
finally:fs.write_text(fixedfs)
build('final-restored-build')
run('final-restored-components',['ctest','--test-dir',str(b),'--no-tests=error','-V','-R','^(coverage-tbl-|coverage-fs)'])
run('final-restored-integration-build',['python3',str(out/'build_cfe_integration.py')])
text,rc=run('final-restored-integration-tests',['/tmp/cfe-integration/integration'])
assert 'FAIL::0' in text
print('Final submitted source restored; all component and integration tests pass with sanitizers.',flush=True)
