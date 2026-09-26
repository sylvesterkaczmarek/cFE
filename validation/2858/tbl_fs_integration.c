/* Focused host integration of the actual table and background file writer modules. */
#include "tbl_UT.h"
#include "tbl_ut_helpers.h"
#include "cfe_fs_priv.h"
#include "cfe_fs_core_internal.h"
#include <stdint.h>
#include "utstub-helpers.h"

static uint8 Input[12 * CFE_TBL_DUMP_BLOCK_SIZE + 7];
static uint8 Output[sizeof(Input) + 512];
static size_t Position;
static size_t Extent;
static uint32 WriteCalls;
static size_t MaxWrite;

static void OpenFile(void *UserObj, UT_EntryKey_t FuncKey, const UT_StubContext_t *Context)
{
    osal_id_t *Fd = UT_Hook_GetArgValueByName(Context, "filedes", osal_id_t *);
    int32 Status;
    UT_Stub_GetInt32StatusCode(Context, &Status);
    *Fd = Status == OS_SUCCESS ? UT_AllocStubObjId(OS_OBJECT_TYPE_OS_STREAM) : OS_OBJECT_ID_UNDEFINED;
    Position = 0;
    Extent = 0;
    UT_Stub_SetReturnValue(FuncKey, Status);
}

static void WriteFile(void *UserObj, UT_EntryKey_t FuncKey, const UT_StubContext_t *Context)
{
    const void *Buffer = UT_Hook_GetArgValueByName(Context, "buffer", const void *);
    size_t Size = UT_Hook_GetArgValueByName(Context, "nbytes", size_t);
    int32 Status;
    if (!UT_Stub_GetInt32StatusCode(Context, &Status)) Status = Size;
    ++WriteCalls;
    if (Size > MaxWrite) MaxWrite = Size;
    if (Status > 0 && (size_t)Status <= Size && Position + Status <= sizeof(Output))
    {
        memcpy(Output + Position, Buffer, Status);
        Position += Status;
        if (Position > Extent) Extent = Position;
    }
    UT_Stub_SetReturnValue(FuncKey, Status);
}

static void SeekFile(void *UserObj, UT_EntryKey_t FuncKey, const UT_StubContext_t *Context)
{
    osal_offset_t Offset = UT_Hook_GetArgValueByName(Context, "offset", osal_offset_t);
    uint32 Whence = UT_Hook_GetArgValueByName(Context, "whence", uint32);
    int32 Status;
    if (!UT_Stub_GetInt32StatusCode(Context, &Status))
    {
        if (Whence == OS_SEEK_SET) Position = Offset;
        else if (Whence == OS_SEEK_CUR) Position += Offset;
        Status = Position;
    }
    UT_Stub_SetReturnValue(FuncKey, Status);
}

static void Reset(void)
{
    UT_InitData_TBL();
    UT_TBL_GlobalDataReset();
    CFE_FS_EarlyInit();
    UT_InitData_TBL();
    memset(&CFE_FS_Global.FileDump, 0, sizeof(CFE_FS_Global.FileDump));
    memset(Output, 0, sizeof(Output));
    Position = Extent = WriteCalls = MaxWrite = 0;
    UT_SetHandlerFunction(UT_KEY(OS_OpenCreate), OpenFile, NULL);
    UT_SetHandlerFunction(UT_KEY(OS_write), WriteFile, NULL);
    UT_SetHandlerFunction(UT_KEY(OS_lseek), SeekFile, NULL);
}

static CFE_TBL_DumpControl_t *Snapshot(uint32 Index, size_t Size)
{
    CFE_TBL_LoadBuff_t *Buffer = UT_TBL_SetupLoadBuff(NULL, false, Index);
    CFE_TBL_DumpControl_t *Control;
    Buffer->IsValid = true;
    Buffer->BufferPtr = Input;
    Buffer->AllocationSize = sizeof(Input);
    Buffer->ContentSize = Size;
    Buffer->FileTime.Seconds = 12345;
    Buffer->FileTime.Subseconds = 0x87654321;
    UT_TBL_SetName(Buffer->DataSource, sizeof(Buffer->DataSource), "snapshot.tbl");
    UT_TBL_SetupPendingDump(Index, Buffer, NULL, &Control);
    Control->SourceBuffId = CFE_TBL_LOADBUFFID_UNDEFINED;
    Control->State = CFE_TBL_DUMP_PERFORMED;
    return Control;
}

static void Drain(CFE_TBL_DumpControl_t *Control)
{
    uint32 Step;
    for (Step = 0; CFE_FS_BackgroundFileDumpIsPending(&Control->FileWrite) && Step < 1000; ++Step)
    {
        CFE_FS_RunBackgroundFileDump(10, NULL);
        UtAssert_BOOL_TRUE(CFE_TBL_DumpCtrlBlockIsUsed(Control));
    }
    UtAssert_True(Step < 1000, "Writer reaches terminal state");
    CFE_TBL_TableDumpExecuteBackground();
    UtAssert_BOOL_FALSE(CFE_TBL_DumpCtrlBlockIsUsed(Control));
}

static void HeaderAndData(void)
{
    const size_t Sizes[] = {0, 1, 1023, 1024, 1025, sizeof(Input)};
    const uint32 Endian = 1;
    size_t Case, i;
    CFE_FS_Header_t Header;
    CFE_TBL_File_Hdr_t TableHeader;
    CFE_TBL_DumpControl_t *Control;
    for (i = 0; i < sizeof(Input); ++i) Input[i] = (uint8)(i * 37U);
    for (Case = 0; Case < sizeof(Sizes) / sizeof(Sizes[0]); ++Case)
    {
        Reset();
        Control = Snapshot(0, Sizes[Case]);
        CFE_TBL_TableDumpExecuteBackground();
        UtAssert_ZERO(WriteCalls);
        UtAssert_BOOL_TRUE(CFE_FS_BackgroundFileDumpIsPending(&Control->FileWrite));
        Drain(Control);
        UtAssert_UINT32_EQ(Extent, sizeof(Header) + sizeof(TableHeader) + Sizes[Case]);
        memcpy(&Header, Output, sizeof(Header));
        memcpy(&TableHeader, Output + sizeof(Header), sizeof(TableHeader));
        if (*(const uint8 *)&Endian)
        {
            CFE_FS_ByteSwapCFEHeader(&Header);
            CFE_TBL_ByteSwapTblHeader(&TableHeader);
        }
        UtAssert_UINT32_EQ(Header.ApplicationID, CFE_RESOURCEID_TO_ULONG(CFE_TBL_Global.TableTaskAppId));
        UtAssert_UINT32_EQ(Header.TimeSeconds, 12345);
        UtAssert_UINT32_EQ(Header.TimeSubSeconds, 0x87654321);
        UtAssert_UINT32_EQ(Header.SubType, CFE_FS_SubType_TBL_IMG);
        UtAssert_UINT32_EQ(TableHeader.NumBytes, Sizes[Case]);
        UtAssert_ZERO(TableHeader.Offset);
        UtAssert_ZERO(TableHeader.Reserved);
        UtAssert_STRINGBUF_EQ(TableHeader.TableName, sizeof(TableHeader.TableName), Control->TableName, -1);
        UtAssert_MemCmp(Output + sizeof(Header) + sizeof(TableHeader), Input, Sizes[Case], "Exact table payload");
        UtAssert_True(MaxWrite <= CFE_TBL_DUMP_BLOCK_SIZE, "No unbounded filesystem write");
        UtAssert_STRINGBUF_EQ(CFE_TBL_Global.HkPacket.Payload.LastFileDumped, -1, "snapshot.tbl", -1);
    }
}

static void WriteFailures(void)
{
    size_t Case;
    CFE_TBL_DumpControl_t *Control;
    for (Case = 0; Case < 5; ++Case)
    {
        Reset();
        Control = Snapshot(0, 1025);
        if (Case == 0) UT_SetDefaultReturnValue(UT_KEY(OS_OpenCreate), OS_ERROR);
        else if (Case < 4) UT_SetDeferredRetcode(UT_KEY(OS_write), Case, 1);
        else UT_SetDeferredRetcode(UT_KEY(OS_lseek), 2, OS_ERROR);
        CFE_TBL_TableDumpExecuteBackground();
        Drain(Control);
        UtAssert_INT32_EQ(Control->WriteStatus, CFE_TBL_ERR_ACCESS);
        UtAssert_STRINGBUF_EQ(CFE_TBL_Global.HkPacket.Payload.LastFileDumped, -1, "", -1);
        CFE_UtAssert_EVENTSENT(Case == 0 ? CFE_TBL_CREATING_DUMP_FILE_ERR_EID :
                              Case == 1 ? CFE_TBL_WRITE_CFE_HDR_ERR_EID :
                              Case == 3 ? CFE_TBL_WRITE_TBL_IMG_ERR_EID : CFE_TBL_WRITE_TBL_HDR_ERR_EID);
    }
}

static bool EmptyData(void *Meta, uint32 Record, void **Buffer, size_t *Size)
{
    *Buffer = NULL;
    *Size = 0;
    return true;
}
static void EmptyEvent(void *Meta, CFE_FS_FileWriteEvent_t Event, int32 Status,
                       uint32 Record, size_t BlockSize, size_t Pos) {}

static void QueueBackpressure(void)
{
    CFE_FS_FileWriteMetaData_t Others[CFE_FS_MAX_BACKGROUND_FILE_WRITES - 1];
    CFE_TBL_DumpControl_t *Control;
    size_t i;
    Reset();
    memset(Others, 0, sizeof(Others));
    for (i = 0; i < sizeof(Others) / sizeof(Others[0]); ++i)
    {
        strcpy(Others[i].FileName, "other.bin");
        Others[i].GetData = EmptyData;
        Others[i].OnEvent = EmptyEvent;
        CFE_UtAssert_SUCCESS(CFE_FS_BackgroundFileDumpRequest(&Others[i]));
    }
    Control = Snapshot(0, 1025);
    CFE_TBL_TableDumpExecuteBackground();
    UtAssert_INT32_EQ(Control->State, CFE_TBL_DUMP_PERFORMED);
    UtAssert_BOOL_TRUE(CFE_TBL_DumpCtrlBlockIsUsed(Control));
    CFE_FS_RunBackgroundFileDump(100, NULL);
    CFE_TBL_TableDumpExecuteBackground();
    UtAssert_INT32_EQ(Control->State, CFE_TBL_DUMP_WRITING);
    Drain(Control);
    UtAssert_INT32_EQ(Control->WriteStatus, CFE_SUCCESS);
}

static void IndependentRequests(void)
{
    CFE_TBL_DumpControl_t *First, *Second;
    Reset();
    First = Snapshot(0, 1);
    Second = Snapshot(1, 1025);
    CFE_TBL_TableDumpExecuteBackground();
    CFE_FS_RunBackgroundFileDump(100, NULL);
    CFE_TBL_TableDumpExecuteBackground();
    UtAssert_BOOL_FALSE(CFE_TBL_DumpCtrlBlockIsUsed(First));
    UtAssert_BOOL_TRUE(CFE_TBL_DumpCtrlBlockIsUsed(Second));
    UtAssert_BOOL_TRUE(CFE_FS_BackgroundFileDumpIsPending(&Second->FileWrite));
    Drain(Second);
    UtAssert_INT32_EQ(CFE_FS_Global.FileDump.RequestCount, 2);
    UtAssert_INT32_EQ(CFE_FS_Global.FileDump.CompleteCount, 2);
}

void UtTest_Setup(void)
{
    UT_Init("table-fs-integration");
    UtTest_Add(HeaderAndData, NULL, NULL, "Snapshot headers and data boundaries");
    UtTest_Add(WriteFailures, NULL, NULL, "Filesystem failures release snapshots");
    UtTest_Add(QueueBackpressure, NULL, NULL, "Full queues retry retained snapshots");
    UtTest_Add(IndependentRequests, NULL, NULL, "Independent queued snapshots");
}
