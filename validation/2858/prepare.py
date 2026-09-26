from pathlib import Path
import os, subprocess, shutil
root = Path('/tmp/cfs')
root.mkdir()
source = Path(os.environ['GITHUB_WORKSPACE']) / 'source'
shutil.copytree(source, root / 'cfe', ignore=shutil.ignore_patterns('.git'))
pins = {
    'osal': ('nasa/osal', '5befd8e9f6c62b44bb7ff4c15db8629c0e00efa0'),
    'psp': ('nasa/PSP', '36c24cb953b047ab5525240579aeb06adf5ac11f'),
    'tools/elf2cfetbl': ('nasa/elf2cfetbl', 'f97ba87035688f0cf82d22b762d42c3c7e4292a6'),
}
for directory, (repo, sha) in pins.items():
    path = root / directory
    path.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'fetch', '--depth=1', 'https://github.com/' + repo + '.git', sha], check=True)
    subprocess.run(['git', '-C', str(path), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
shutil.copytree(root / 'cfe/cmake/sample_defs', root / 'sample_defs')
shutil.copy2(root / 'cfe/cmake/Makefile.sample', root / 'Makefile')
(root / 'apps').mkdir()
(root / 'libs').mkdir()
(root / 'tools/CMakeLists.txt').write_text('add_subdirectory(elf2cfetbl)\n')
(root / 'sample_defs/targets.cmake').write_text('SET(MISSION_NAME TableBackgroundRegression)\nSET(SPACECRAFT_ID 0x42)\nSET(MISSION_CPUNAMES cpu1)\nSET(cpu1_PROCESSORID 1)\nSET(MISSION_GLOBAL_APPLIST)\n')
output = Path(os.environ['EVIDENCE_DIR'])
original = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD^:modules/tbl/fsw/src/cfe_tbl_dump.c'])
(output / 'original-cfe-tbl-dump.c').write_bytes(original)
print('Prepared exact submitted source and three pinned dependencies.')
