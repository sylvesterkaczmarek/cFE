#include "tbl_UT.h"
#include "tbl_ut_helpers.h"

void UtTest_Setup(void)
{
    UT_Init("table-snapshot-sanitizers");
    UtTest_Add(Test_CFE_TBL_DumpToFile, UT_TBL_GlobalDataReset, NULL, "Snapshot queueing");
    UtTest_Add(Test_CFE_TBL_TableDumpExecuteBackground, UT_TBL_GlobalDataReset, NULL, "Snapshot lifetime");
    UtTest_Add(Test_CFE_TBL_SnapshotHeaders, UT_TBL_GlobalDataReset, NULL, "Snapshot headers");
    UtTest_Add(Test_CFE_TBL_SnapshotBlocks, UT_TBL_GlobalDataReset, NULL, "Snapshot block boundaries");
    UtTest_Add(Test_CFE_TBL_SnapshotEvents, UT_TBL_GlobalDataReset, NULL, "Snapshot events");
    UtTest_Add(Test_CFE_TBL_SnapshotMultiple, UT_TBL_GlobalDataReset, NULL, "Independent snapshots");
}
