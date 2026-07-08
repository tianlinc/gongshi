
// Provide a default path to dwr.engine
if (dwr == null) var dwr = {};
if (dwr.engine == null) dwr.engine = {};
if (DWREngine == null) var DWREngine = dwr.engine;

if (jviewConfigUtil == null) var jviewConfigUtil = {};
jviewConfigUtil._path = '/dwr';
jviewConfigUtil.dynAdjustProperty = function(p0, p1, p2, p3, p4, p5, callback) {
  dwr.engine._execute(jviewConfigUtil._path, 'jviewConfigUtil', 'dynAdjustProperty', p0, p1, p2, p3, p4, p5, callback);
}
jviewConfigUtil.dynGetConfigItem = function(p0, p1, p2, p3, p4, callback) {
  dwr.engine._execute(jviewConfigUtil._path, 'jviewConfigUtil', 'dynGetConfigItem', p0, p1, p2, p3, p4, callback);
}
jviewConfigUtil.dynRemoveView = function(p0, callback) {
  dwr.engine._execute(jviewConfigUtil._path, 'jviewConfigUtil', 'dynRemoveView', p0, callback);
}
jviewConfigUtil.dynAdjustPosition = function(p0, p1, p2, p3, p4, callback) {
  dwr.engine._execute(jviewConfigUtil._path, 'jviewConfigUtil', 'dynAdjustPosition', p0, p1, p2, p3, p4, callback);
}
jviewConfigUtil.dynCopyView = function(p0, callback) {
  dwr.engine._execute(jviewConfigUtil._path, 'jviewConfigUtil', 'dynCopyView', p0, callback);
}
jviewConfigUtil.dynToggleProperty = function(p0, p1, p2, p3, p4, p5, callback) {
  dwr.engine._execute(jviewConfigUtil._path, 'jviewConfigUtil', 'dynToggleProperty', p0, p1, p2, p3, p4, p5, callback);
}
jviewConfigUtil.dynResetViewSelect = function(p0, p1, p2, p3, callback) {
  dwr.engine._execute(jviewConfigUtil._path, 'jviewConfigUtil', 'dynResetViewSelect', p0, p1, p2, p3, callback);
}
