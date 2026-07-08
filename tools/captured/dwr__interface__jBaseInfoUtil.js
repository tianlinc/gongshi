
// Provide a default path to dwr.engine
if (dwr == null) var dwr = {};
if (dwr.engine == null) dwr.engine = {};
if (DWREngine == null) var DWREngine = dwr.engine;

if (jBaseInfoUtil == null) var jBaseInfoUtil = {};
jBaseInfoUtil._path = '/dwr';
jBaseInfoUtil.dynGetFilterField = function(p0, p1, p2, p3, p4, callback) {
  dwr.engine._execute(jBaseInfoUtil._path, 'jBaseInfoUtil', 'dynGetFilterField', p0, p1, p2, p3, p4, callback);
}
jBaseInfoUtil.dynGetSelectFilter = function(p0, p1, p2, p3, callback) {
  dwr.engine._execute(jBaseInfoUtil._path, 'jBaseInfoUtil', 'dynGetSelectFilter', p0, p1, p2, p3, callback);
}
jBaseInfoUtil.dynGetCode = function(p0, p1, p2, callback) {
  dwr.engine._execute(jBaseInfoUtil._path, 'jBaseInfoUtil', 'dynGetCode', p0, p1, p2, callback);
}
