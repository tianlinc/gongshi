
// Provide a default path to dwr.engine
if (dwr == null) var dwr = {};
if (dwr.engine == null) dwr.engine = {};
if (DWREngine == null) var DWREngine = dwr.engine;

if (jtaskEntityBean == null) var jtaskEntityBean = {};
jtaskEntityBean._path = '/dwr';
jtaskEntityBean.dynGetReport = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetReport', p0, p1, callback);
}
jtaskEntityBean.dynSaveTask = function(p0, p1, p2, p3, p4, p5, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynSaveTask', p0, p1, p2, p3, p4, p5, callback);
}
jtaskEntityBean.dynPasteTask = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynPasteTask', p0, callback);
}
jtaskEntityBean.dynGetTskTypeJson = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTskTypeJson', p0, p1, callback);
}
jtaskEntityBean.dynUpdateView = function(p0, p1, p2, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynUpdateView', p0, p1, p2, callback);
}
jtaskEntityBean.dynGetObjectPlans = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetObjectPlans', p0, callback);
}
jtaskEntityBean.dynSaveNodeDate = function(p0, p1, p2, p3, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynSaveNodeDate', p0, p1, p2, p3, callback);
}
jtaskEntityBean.dynSaveTakeNote = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynSaveTakeNote', p0, p1, callback);
}
jtaskEntityBean.dynGetTaskChanges = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskChanges', p0, p1, callback);
}
jtaskEntityBean.dynDelTaskNote = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynDelTaskNote', p0, callback);
}
jtaskEntityBean.dynGetTaskNodes = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskNodes', p0, callback);
}
jtaskEntityBean.dynGetTaskDate = function(p0, p1, p2, p3, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskDate', p0, p1, p2, p3, callback);
}
jtaskEntityBean.dynGetWfAction = function(callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetWfAction', callback);
}
jtaskEntityBean.dynSaveTaskSharePro = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynSaveTaskSharePro', p0, p1, callback);
}
jtaskEntityBean.dynPrepareTask = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynPrepareTask', p0, p1, callback);
}
jtaskEntityBean.dynGetIsProjectGantt = function(callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetIsProjectGantt', callback);
}
jtaskEntityBean.dynGetTaskWorkDays = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskWorkDays', p0, p1, callback);
}
jtaskEntityBean.dynGetDecomposeData = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetDecomposeData', p0, p1, callback);
}
jtaskEntityBean.dynGetTaskRelate = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskRelate', p0, p1, callback);
}
jtaskEntityBean.dynMoreTaskInfo = function(p0, p1, p2, p3, p4, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynMoreTaskInfo', p0, p1, p2, p3, p4, callback);
}
jtaskEntityBean.dynGetTaskObjectInfo = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskObjectInfo', p0, p1, callback);
}
jtaskEntityBean.dynGetPrqOwner = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetPrqOwner', p0, p1, callback);
}
jtaskEntityBean.dynGetServerToday = function(callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetServerToday', callback);
}
jtaskEntityBean.dynDeleteMulTasks = function(p0, p1, p2, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynDeleteMulTasks', p0, p1, p2, callback);
}
jtaskEntityBean.dynGetTaskStatus = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskStatus', p0, callback);
}
jtaskEntityBean.dynUnShareTask = function(p0, p1, p2, p3, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynUnShareTask', p0, p1, p2, p3, callback);
}
jtaskEntityBean.dynGetTaskObjectId = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskObjectId', p0, p1, callback);
}
jtaskEntityBean.dynGetShareProInfo = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetShareProInfo', p0, callback);
}
jtaskEntityBean.dynGetTaskSignInfo = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskSignInfo', p0, p1, callback);
}
jtaskEntityBean.dynUpdateCustomView = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynUpdateCustomView', p0, p1, callback);
}
jtaskEntityBean.dynUpdateData = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynUpdateData', p0, p1, callback);
}
jtaskEntityBean.dynUpdateNode = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynUpdateNode', p0, callback);
}
jtaskEntityBean.dynGetProjectMiles = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetProjectMiles', p0, callback);
}
jtaskEntityBean.dynGetTaskInfo = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynGetTaskInfo', p0, callback);
}
jtaskEntityBean.dynBaseSearch = function(callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynBaseSearch', callback);
}
jtaskEntityBean.dynCancelCooperate = function(p0, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynCancelCooperate', p0, callback);
}
jtaskEntityBean.dynCheckAcrossDay = function(p0, p1, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynCheckAcrossDay', p0, p1, callback);
}
jtaskEntityBean.dynCheckWorkDate = function(p0, p1, p2, p3, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynCheckWorkDate', p0, p1, p2, p3, callback);
}
jtaskEntityBean.dynConvertEntity = function(p0, p1, p2, callback) {
  dwr.engine._execute(jtaskEntityBean._path, 'jtaskEntityBean', 'dynConvertEntity', p0, p1, p2, callback);
}
