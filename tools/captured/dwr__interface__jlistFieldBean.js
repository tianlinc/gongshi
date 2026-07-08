
// Provide a default path to dwr.engine
if (dwr == null) var dwr = {};
if (dwr.engine == null) dwr.engine = {};
if (DWREngine == null) var DWREngine = dwr.engine;

if (jlistFieldBean == null) var jlistFieldBean = {};
jlistFieldBean._path = '/dwr';
jlistFieldBean.dynSelectItems = function(p0, p1, callback) {
  dwr.engine._execute(jlistFieldBean._path, 'jlistFieldBean', 'dynSelectItems', p0, p1, callback);
}
jlistFieldBean.dynTskFilterTypeSelect = function(p0, p1, p2, callback) {
  dwr.engine._execute(jlistFieldBean._path, 'jlistFieldBean', 'dynTskFilterTypeSelect', p0, p1, p2, callback);
}
