
// Provide a default path to dwr.engine
if (dwr == null) var dwr = {};
if (dwr.engine == null) dwr.engine = {};
if (DWREngine == null) var DWREngine = dwr.engine;

if (jworkLogService == null) var jworkLogService = {};
jworkLogService._path = '/dwr';
jworkLogService.getWeekStartDate = function(p0, p1, callback) {
  dwr.engine._execute(jworkLogService._path, 'jworkLogService', 'getWeekStartDate', p0, p1, callback);
}
