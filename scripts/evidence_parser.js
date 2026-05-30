// 证据解析器 - normalizeEvidenceItem
// 独立文件加载，避免内联Babel转义问题

function normalizeEvidenceItem(rawItem) {
  if (!rawItem) return { title:"", displayTitle:"", summary:"", riskSummary:"", publishDate:"", displayDate:"", source:"未知", publisher:"", dataSource:"", channel:"未知", url:"", tags:[], rawText:"" };
  if (typeof rawItem !== "object") {
    console.warn("normalizeEvidenceItem: non-object input");
    return { title:"来源解析失败", displayTitle:"来源解析失败", summary:"", riskSummary:"该条来源返回内容暂未完成结构化解析", publishDate:"", displayDate:"", source:"未知", publisher:"", dataSource:"", channel:"未知", url:"", tags:[], rawText:String(rawItem) };
  }

  var cleanText = function(t) {
    if (!t || typeof t !== "string") return "";
    t = t.replace(/详细内容如下[\(\（][^）\)]*[）\)]?[：:]?/g,"").replace(/详细内容如下[：:]/g,"").replace(/前\d+条[：:]?/g,"");
    t = t.replace(/以上内容为.*?(不构成投资建议|不作投资参考|投资建议|AI算法生成|证券之星据公开信息整理)[^。]*[。]?/g,"");
    t = t.replace(/网信算备[^。\n]*[。]?/g,"");
    t = t.replace(/[。，；：、]{2,}/g,function(m){return m[0];});
    t = t.replace(/[，；：、]\s*[。]/g,"。").replace(/[。]\s*[，；：、]/g,"。");
    t = t.replace(/^[，；：、。\s]+/g,"").replace(/[，；：、\s]+$/g,"");
    if (t.length > 0 && !/[。！？]$/.test(t)) t += "。";
    return t.replace(/\s+/g," ").trim();
  };

  var obj = rawItem;
  if (typeof rawItem === "string" && rawItem.trim().startsWith("{")) {
    try { obj = JSON.parse(rawItem); } catch(e) {}
  }
  if (typeof obj !== "object" || obj === null) {
    console.warn("normalizeEvidenceItem: parse failed");
    return { title:"来源解析失败", displayTitle:"来源解析失败", summary:"", riskSummary:"该条来源返回内容暂未完成结构化解析", publishDate:"", displayDate:"", source:"未知", publisher:"", dataSource:"", channel:"未知", url:"", tags:[], rawText:String(rawItem) };
  }

  // Parse nested JSON in content/detail
  var sourceObj = obj;
  for (var k = 0; k < 2; k++) {
    var tk = k === 0 ? "content" : "detail";
    var tv = obj[tk];
    if (typeof tv === "string" && tv.trim().startsWith("{")) {
      try {
        var p = JSON.parse(tv);
        if (p && typeof p === "object" && Object.keys(p).length >= 2) { sourceObj = p; break; }
      } catch(e) {}
    }
  }

  var gf = function(keys) {
    for (var i = 0; i < keys.length; i++) {
      var v = sourceObj[keys[i]];
      if (v !== undefined && v !== null && String(v).trim()) return String(v).trim();
    }
    if (sourceObj !== obj) {
      for (var j = 0; j < keys.length; j++) {
        var v2 = obj[keys[j]];
        if (v2 !== undefined && v2 !== null && String(v2).trim()) return String(v2).trim();
      }
    }
    return "";
  };

  var title   = gf(["资讯标题","title","标题","name"]);
  var content = gf(["资讯内容","content","正文","内容","summary"]);
  var date    = gf(["日期","date","publishDate","时间","time","发布时间"]);
  var url     = gf(["URL","url","link","jumpUrl"]);
  var srcName = gf(["数据来源","source","来源","insName"]);
  var chanRaw = gf(["informationType","channel","渠道"]);

  // Regex fallback from raw text
  var allText = "";
  if (typeof obj.detail === "string") allText += " " + obj.detail;
  if (typeof obj.content === "string") allText += " " + obj.content;
  var rx = function(p,t){ var m = t.match(p); return m ? (m[1]||m[2]||"").trim() : ""; };
  if (!title)   title   = rx(/资讯标题["\s:：]+([^"}\n]{4,80})/, allText);
  if (!content) content = rx(/资讯内容["\s:：]+([^"}\n]{10,300})/, allText);
  if (!date)    date    = rx(/日期["\s:：]+(\d{4}-\d{2}-\d{2})/, allText);
  if (!url)     url     = rx(/URL["\s:：]+(https?:\/\/[^"\s}]+)/, allText);

  title   = cleanText(title);
  content = cleanText(content);
  if (!title || title.length < 3 || /^[\[{"]/.test(title) || title.indexOf('"资讯标题"') >= 0) {
    if (content && content.length > 10) {
      var tm = content.match(/^([^。，；]{12,60})/);
      title = tm ? tm[1].trim() : content.slice(0,60);
    } else {
      var rn = obj.name || "";
      title = (!/^iFind\s*segment/i.test(rn) && rn.length > 3) ? rn : "iFinD 资讯片段";
    }
  }

  // Publisher & dataSource detection
  var publisher = "", dataSource = "";
  var pp = [
    {re:/证券之星消息/,pub:"证券之星"},{re:/新浪财经/,pub:"新浪财经"},
    {re:/东方财富/,pub:"东方财富"},{re:/同花顺/,pub:"同花顺"},
    {re:/财联社/,pub:"财联社"},{re:/文化视角/,pub:"文化视角"},
    {re:/青岛资本圈/,pub:"青岛资本圈"}
  ];
  for (var pi = 0; pi < pp.length; pi++) { if (pp[pi].re.test(content)) { publisher = pp[pi].pub; break; } }
  var dp = [{re:/天眼查APP/,ds:"天眼查APP"},{re:/天眼查/,ds:"天眼查"},{re:/企查查/,ds:"企查查"}];
  for (var di = 0; di < dp.length; di++) { if (dp[di].re.test(content)) { dataSource = dp[di].ds; break; } }
  if (!publisher) publisher = srcName || "";

  // Channel
  var channel = "iFinD";
  if (chanRaw === "NOTICE") channel = "公告";
  else if (chanRaw === "REPORT") channel = "研报";
  else if (chanRaw === "INV_NEWS") channel = "财经新闻";
  else if (url && url.indexOf("eastmoney") >= 0) channel = "Choice";
  else if (srcName && (srcName.indexOf("Choice") >= 0 || srcName.indexOf("mx") >= 0)) channel = "Choice";

  // Tags
  var tags = [];
  var RK = ["失信","被执行","违约","逾期","破产","清算","诉讼","处罚","冻结","查封","限制高消费","评级下调","合同纠纷","虚开","税收违法","非标违约","票据逾期","开庭","纠纷"];
  var hs = (title + " " + content).toLowerCase();
  for (var ti = 0; ti < RK.length; ti++) { if (hs.indexOf(RK[ti].toLowerCase()) >= 0) tags.push(RK[ti]); }

  // Summary (cleaned original)
  var summary = content;
  if (summary && summary.length > 200) summary = summary.slice(0,197) + "...";

  // RiskSummary
  var riskSummary = "";
  if (content) {
    var hasDishonesty = hs.indexOf("失信") >= 0 || hs.indexOf("被执行") >= 0;
    var hasLawsuit = hs.indexOf("诉讼") >= 0 || hs.indexOf("开庭") >= 0 || hs.indexOf("合同纠纷") >= 0;
    var hasDefault = hs.indexOf("违约") >= 0 || hs.indexOf("逾期") >= 0;
    var hasTax = hs.indexOf("虚开") >= 0 || hs.indexOf("税收违法") >= 0;
    var nm = content.match(/(\d+)\s*[起项个]/); var ns = nm ? nm[1] : "";
    if (hasDishonesty) {
      riskSummary = "该主体已被列为失信被执行人或存在被执行记录，属于严重负面信号，建议立即核查敞口并评估代偿风险。";
      if (ns) riskSummary = "该主体涉及" + ns + "起被执行案件，已被列为失信被执行人或存在被执行记录，属于严重负面信号，建议立即核查敞口。";
    } else if (hasTax) {
      riskSummary = "该主体子公司存在虚开发票等重大税收违法行为，被列为税收违法失信主体，可能影响主体整体信用资质及再融资能力。";
    } else if (hasLawsuit && ns) {
      riskSummary = "该主体近期涉及" + ns + "起诉讼/开庭事项，案由集中于合同纠纷，属于诉讼关注事项，建议持续跟踪后续判决及执行情况。";
    } else if (hasLawsuit) {
      riskSummary = "该主体近期涉及诉讼/开庭事项，属于诉讼关注事项，建议持续跟踪后续判决及执行情况。";
    } else if (hasDefault) {
      riskSummary = "该主体存在票据逾期或债务违约事项，反映流动性压力，建议关注其再融资进展及偿债安排。";
    } else {
      riskSummary = summary;
    }
  }
  if (!riskSummary) riskSummary = summary || "";

  // DisplayTitle
  var displayTitle = title;
  if (displayTitle.length > 36) {
    displayTitle = displayTitle
      .replace(/有限公司|有限责任公司|集团有限公司|股份有限公司/g,"")
      .replace(/作为原告\/上诉人的/g,"")
      .replace(/作为被告\/被上诉人的/g,"")
      .replace(/涉及/g,"")
      .replace(/将于\d{4}年\d{1,2}月\d{1,2}日开庭/g,"将开庭")
      .replace(/开庭日期为\d{4}年\d{1,2}月\d{1,2}日/g,"")
      .replace(/\s+/g,"");
    if (displayTitle.length > 36) displayTitle = displayTitle.slice(0,33) + "...";
  }

  // Dirty check
  var dirty = ['"资讯标题"','"资讯内容"','"日期"','"URL"'];
  for (var dmi = 0; dmi < dirty.length; dmi++) {
    if (displayTitle.indexOf(dirty[dmi]) >= 0 || riskSummary.indexOf(dirty[dmi]) >= 0) {
      console.warn("normalizeEvidenceItem: dirty output detected");
      return { title:"来源解析失败", displayTitle:"来源解析失败", summary:"", riskSummary:"该条来源返回内容暂未完成结构化解析", publishDate:"", displayDate:"", source:"未知", publisher:"", dataSource:"", channel:"未知", url:"", tags:[], rawText:JSON.stringify(rawItem,null,2) };
    }
  }

  return {
    title: title, displayTitle: displayTitle, summary: summary, riskSummary: riskSummary,
    publishDate: date, displayDate: obj.time || rawItem.time || "",
    source: srcName || channel, publisher: publisher, dataSource: dataSource,
    channel: channel, url: url, tags: tags,
    rawText: typeof rawItem === "string" ? rawItem : JSON.stringify(rawItem,null,2),
  };
}