from pathlib import Path
import shlex, subprocess, re, os
w=Path(os.environ.get('EVIDENCE_DIR', '/work')); b=Path('/tmp/cfs/build/native/default_cpu1'); tbl=b/'tbl/ut-coverage'; fs=b/'fs/ut-coverage'; dst=Path('/tmp/cfe-integration');dst.mkdir(exist_ok=True)
flags=(tbl/'CMakeFiles/coverage-tbl-ALL-testrunner.dir/flags.make').read_text(); args=['cc']
for key in ['C_DEFINES','C_INCLUDES','C_FLAGS']:
 args+=shlex.split(re.search(r'^'+key+r' = (.*)$',flags,re.M).group(1))
args+=['-I/tmp/cfs/osal/src/ut-stubs','-I/tmp/cfs/cfe/modules/tbl/ut-coverage','-I/tmp/cfs/cfe/modules/fs/fsw/src','-c',str(w/'tbl_fs_integration.c'),'-o',str(dst/'integration.o')]
subprocess.run(args,check=True)
original=tbl/'CMakeFiles/coverage-tbl-ALL-testrunner.dir/tbl_UT.c.o'
subprocess.run(['objcopy','--redefine-sym','UtTest_Setup=UT_TBL_OriginalSetup',str(original),str(dst/'tbl_UT.o')],check=True)
link=shlex.split((tbl/'CMakeFiles/coverage-tbl-ALL-testrunner.dir/link.txt').read_text());link=[str(dst/'tbl_UT.o') if x=='CMakeFiles/coverage-tbl-ALL-testrunner.dir/tbl_UT.c.o' else x for x in link]
link[link.index('-o')+1]=str(dst/'integration')
link[2:2]=[str(dst/'integration.o')]+[str(x) for x in (fs/'CMakeFiles/coverage-fs-ALL-object.dir').rglob('*.o')]
subprocess.run(link,cwd=tbl,check=True)
print('Linked actual FS and TBL coverage objects, with a separate integration entry point.')

# A separate sanitizer entry point runs all added/adapted snapshot groups without
# the unchanged TaskInit fixture, which supplies a null software-bus message.
args[args.index(str(w/'tbl_fs_integration.c'))] = str(w/'tbl_sanitizer_focus.c')
args[args.index(str(dst/'integration.o'))] = str(dst/'focused.o')
subprocess.run(args, check=True)
link=shlex.split((tbl/'CMakeFiles/coverage-tbl-ALL-testrunner.dir/link.txt').read_text())
link=[str(dst/'tbl_UT.o') if x=='CMakeFiles/coverage-tbl-ALL-testrunner.dir/tbl_UT.c.o' else x for x in link]
link[link.index('-o')+1]=str(dst/'table-focused')
link[2:2]=[str(dst/'focused.o')]
subprocess.run(link,cwd=tbl,check=True)
print('Built focused sanitizer entry point using the actual submitted snapshot tests.')
