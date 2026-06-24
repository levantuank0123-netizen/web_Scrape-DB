// Apps Script v5: routing theo platform
// - getrewardful → tab "metrics"
// - firstpromoter → tab "firstpromoter"
// - các platform khác → tab tên platform
// - tự động bôi đỏ due_now > 0, error có giá trị

var HEADERS = ['scraped_at','metric_date','platform','label','owner','email','ref_link',
               'ref_count','clicks','impressions','orders',
               'total_earned','unpaid','due_now','paid','currency','error'];

var PLATFORM_TO_SHEET = {
  'getrewardful': 'metrics',          // tab metrics chỉ chứa getrewardful
  'firstpromoter': 'firstpromoter',
};

function _sheetName(platform) {
  return PLATFORM_TO_SHEET[platform] || (platform || 'metrics');
}

function _ensureSheet(ss, sheetName) {
  var sheet = ss.getSheetByName(sheetName) || ss.insertSheet(sheetName);
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    // Bôi đỏ due_now (cột thứ 14 = N)
    var dueCol = HEADERS.indexOf('due_now') + 1;
    var dueRange = sheet.getRange(2, dueCol, 10000, 1);
    var dueRule = SpreadsheetApp.newConditionalFormatRule()
      .whenNumberGreaterThan(0)
      .setBackground('#FF6666').setFontColor('#FFFFFF').setBold(true)
      .setRanges([dueRange]).build();
    // Bôi nhẹ cột error
    var errCol = HEADERS.indexOf('error') + 1;
    var errRange = sheet.getRange(2, errCol, 10000, 1);
    var errRule = SpreadsheetApp.newConditionalFormatRule()
      .whenCellNotEmpty().setBackground('#FFE0E0').setRanges([errRange]).build();
    sheet.setConditionalFormatRules([dueRule, errRule]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function doPost(e) {
  var data = JSON.parse(e.postData.contents);
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  // Clear: ?_clear=true sẽ clear theo _sheet hoặc tất cả
  if (data && data._clear) {
    if (data._sheet) {
      // Clear 1 sheet cụ thể
      var s = ss.getSheetByName(data._sheet);
      if (s) s.clear();
      return ContentService.createTextOutput(JSON.stringify({ok:true, cleared:data._sheet}))
        .setMimeType(ContentService.MimeType.JSON);
    } else {
      // Clear tất cả sheet quản lý (metrics + firstpromoter)
      ['metrics','firstpromoter'].forEach(function(n){
        var s = ss.getSheetByName(n);
        if (s) s.clear();
      });
      return ContentService.createTextOutput(JSON.stringify({ok:true, cleared:'all'}))
        .setMimeType(ContentService.MimeType.JSON);
    }
  }

  // Bình thường: route theo platform
  var rows = Array.isArray(data) ? data : [data];
  var bySheet = {};
  rows.forEach(function(r){
    var name = _sheetName(r.platform);
    if (!bySheet[name]) bySheet[name] = [];
    bySheet[name].push(r);
  });

  var written = 0;
  Object.keys(bySheet).forEach(function(name){
    var sheet = _ensureSheet(ss, name);
    bySheet[name].forEach(function(r){
      sheet.appendRow(HEADERS.map(function(h){
        var v = r[h];
        if (h === 'scraped_at') return v || new Date().toISOString();
        if (v == null) return '';
        return v;
      }));
      written++;
    });
  });
  return ContentService.createTextOutput(JSON.stringify({ok:true, written: written, sheets: Object.keys(bySheet)}))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet() {
  return ContentService.createTextOutput('Affiliate metrics webhook v5 (multi-sheet routing)');
}
