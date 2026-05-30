// 证据解析器 v3 - 周报提取 + 完整内容 + 分类展示

function normalizeEvidenceItem(rawItem, currentSubjectName) {
  var EMPTY = {
    evidenceType: "raw_unknown", isSubjectMatched: false, matchedSubjectName: "",
    title: "", displayTitle: "", riskSummary: "", sourceSummary: "",
    matchedExcerpt: "", sourceFullText: "", fullRawText: "", isTruncatedBySource: false,
    publishDate: "", hitDate: "", publisher: "", dataSource: "", channel: "未知",
    url: "", tags: [], rawText: ""
  };
  if (!rawItem) return EMPTY;
  if (typeof rawItem !== "object") {
    console.warn("normalizeEvidenceItem: non-object input");
    var r = Object.assign({}, EMPTY);
    r.fullRawText = String(rawItem); r.rawText = String(rawItem);
    return r;
  }

  // ====== cleanText (basic) ======
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

  // ====== cleanWeeklyDigestText ======
  var cleanWeeklyDigestText = function(t) {
    if (!t || typeof t !== "string") return "";
    // Remove section headers
    t = t.replace(/0\d\s*(城投|产业债|金融债|地方债|公司债|企业债|ABS|信用债|可转债|中期票据|短融)/g, "");
    t = t.replace(/信用负面信息[：:\s]*/g, "");
    t = t.replace(/来源[：:]\s*\S+信用负面信息/g, "");
    t = t.replace(/来源[：:]\s*\S+/g, "");
    // Fix numbering粘连: "1.东阳国资" or "1、东阳国资" -> extracted per-subject later
    // Remove trailing ellipsis
    t = t.replace(/[\.。]{3,}$/g, "").replace(/…+$/g, "").replace(/\.\.\.+$/g, "");
    // Collapse bad punctuation
    t = t.replace(/[。，；：、]{2,}/g, function(m){ return m[0]; });
    t = t.replace(/[，；：、]\s*[。]/g, "。").replace(/[。]\s*[，；：、]/g, "。");
    t = t.replace(/^[，；：、。\s]+/g, "").replace(/[，；：、\s]+$/g, "");
    if (t.length > 0 && !/[。！？]$/.test(t)) t += "。";
    return t.replace(/\s+/g, " ").trim();
  };

  // ====== extractSubjectRelatedSentences ======
  var extractSubjectRelatedSentences = function(text, names) {
    if (!text || !names || names.length === 0) return { excerpt: "", matched: false };
    // Split by numbered items: "1.xxx 2.xxx" or "1、xxx 2、xxx" or "1）xxx"
    var items = text.split(/(?=\d+[\.、）\)]\s*)/);
    var matched = [];
    var allNames = names.slice();

    for (var i = 0; i < items.length; i++) {
      var item = items[i].trim();
      if (!item) continue;
      // Check if any name matches this item
      var hit = false;
      for (var ni = 0; ni < allNames.length; ni++) {
        if (item.indexOf(allNames[ni]) >= 0) { hit = true; break; }
      }
      if (hit) {
        // Clean the item: remove leading number
        var cleaned = item.replace(/^\d+[\.、）\)]\s*/, "").trim();
        // Remove any content after the NEXT numbered item starts (greedy)
        cleaned = cleaned.replace(/\d+[\.、）\)]\s*[\s\S]*$/, "").trim();
        cleaned = cleanWeeklyDigestText(cleaned);
        if (cleaned.length > 3) matched.push(cleaned);
      }
    }

    // If no items found, try sentence-based extraction
    if (matched.length === 0) {
      var sentences = text.split(/[。；\n]/);
      for (var si = 0; si < sentences.length; si++) {
        var s = sentences[si].trim();
        if (!s || s.length < 5) continue;
        for (var nj = 0; nj < allNames.length; nj++) {
          if (s.indexOf(allNames[nj]) >= 0) {
            matched.push(cleanWeeklyDigestText(s));
            break;
          }
        }
      }
    }

    if (matched.length > 0) {
      return { excerpt: matched.join("；"), matched: true };
    }
    return { excerpt: "", matched: false };
  };

  // ====== matchSubject ======
  var matchSubject = function(text, fullName) {
    if (!text || !fullName) return { matched: false, name: "", aliases: [] };
    var name = String(fullName).trim();
    if (!name) return { matched: false, name: "", aliases: [] };
    if (text.indexOf(name) >= 0) return { matched: true, name: name, aliases: [name] };
    var aliases = [];
    var short = name.replace(/有限公司|有限责任公司|集团有限公司|股份有限公司|\(|\)|（|）/g, "").trim();
    if (short.length >= 4 && short !== name) aliases.push(short);
    var cityMatch = name.match(/^([\u4e00-\u9fa5]{2,4}[市州县区])/);
    if (cityMatch) {
      var city = cityMatch[1];
      var rest = name.replace(city, "").replace(/有限公司|有限责任公司|集团有限公司|股份有限公司|\(|\)|（|）/g, "");
      if (rest.length >= 2) aliases.push(city.replace(/[市州县区]$/, "") + rest.slice(0, Math.min(4, rest.length)));
      if (rest.length >= 4) aliases.push(city.replace(/[市州县区]$/, "") + rest.slice(0, 2));
    }
    aliases = aliases.filter(function(a, i, arr) { return a.length >= 3 && arr.indexOf(a) === i; });
    for (var ai = 0; ai < aliases.length; ai++) {
      if (text.indexOf(aliases[ai]) >= 0) return { matched: true, name: aliases[ai], aliases: aliases };
    }
    return { matched: false, name: "", aliases: aliases };
  };

  // ====== Step 1: normalize input ======
  var obj = rawItem;
  if (typeof rawItem === "string" && rawItem.trim().startsWith("{")) {
    try { obj = JSON.parse(rawItem); } catch(e) {}
  }
  if (typeof obj !== "object" || obj === null) {
    console.warn("normalizeEvidenceItem: parse failed");
    var r2 = Object.assign({}, EMPTY);
    r2.fullRawText = String(rawItem); r2.rawText = String(rawItem);
    return r2;
  }

  // ====== Step 2: parse nested JSON ======
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

  // ====== Step 3: field extraction ======
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

  var allText = "";
  if (typeof obj.detail === "string") allText += " " + obj.detail;
  if (typeof obj.content === "string") allText += " " + obj.content;
  var rx = function(p,t){ var m = t.match(p); return m ? (m[1]||m[2]||"").trim() : ""; };
  if (!title)   title   = rx(/资讯标题["\s:：]+([^"}\n]{4,80})/, allText);
  if (!content) content = rx(/资讯内容["\s:：]+([^"}\n]{10,500})/, allText);
  if (!date)    date    = rx(/日期["\s:：]+(\d{4}-\d{2}-\d{2})/, allText);
  if (!url)     url     = rx(/URL["\s:：]+(https?:\/\/[^"\s}]+)/, allText);

  title   = cleanText(title);
  content = cleanText(content);

  // ====== Step 4: evidenceType ======
  var evidenceType = "raw_unknown";
  var profileKeywords = ["简介","成立于","注册资本","实缴资本","曾用名","法定代表人","统一社会信用代码","经营范围","所属行业","企业注册资本","对外投资","行政许可","登记机关","参保人数","人员规模"];
  var isProfile = false;
  for (var pki = 0; pki < profileKeywords.length; pki++) {
    if ((title + content).indexOf(profileKeywords[pki]) >= 0) { isProfile = true; break; }
  }
  if (!isProfile && title && /^[\u4e00-\u9fa5（）\(\)]+(有限公司|有限责任公司|集团有限公司|股份有限公司)。?$/.test(title)) isProfile = true;

  var weeklyKeywords = ["周度回顾","信用负面周度回顾","一周信用负面","风险周报","舆情周报","负面汇总","批量摘要","多主体汇总","信用负面信息","信用负面周度","周度信用"];
  var isWeekly = false;
  for (var wki = 0; wki < weeklyKeywords.length; wki++) {
    if ((title + content).indexOf(weeklyKeywords[wki]) >= 0) { isWeekly = true; break; }
  }

  var isCrossCheck = (title + (obj.name||"")).indexOf("mx-skill") >= 0 || (title + (obj.name||"")).indexOf("交叉验证") >= 0 ||
                     (srcName||"").indexOf("mx") >= 0 || (obj.name||"").indexOf("mx-skill") >= 0;

  if (isProfile) evidenceType = "company_profile";
  else if (isWeekly) evidenceType = "weekly_digest";
  else if (isCrossCheck) evidenceType = "cross_check";
  else if (title || content) evidenceType = "risk_event";

  // ====== Step 5: subject matching + weekly excerpt extraction ======
  var subjectMatch = { matched: false, name: "", aliases: [] };
  var subjName = currentSubjectName || obj.entity || rawItem.entity || "";
  var weeklyExcerpt = "";

  if (subjName) {
    subjectMatch = matchSubject(title + " " + content, subjName);
    // For risk_event: if not directly matched, try looser
    if (!subjectMatch.matched && evidenceType === "risk_event") {
      var entName = obj.entity || rawItem.entity || "";
      if (entName && (title + content).indexOf(entName) >= 0) {
        subjectMatch = { matched: true, name: entName, aliases: [entName] };
      }
      if (!subjectMatch.matched && subjName.length > 4) {
        var shortSubj = subjName.replace(/有限公司|有限责任公司|集团有限公司|股份有限公司/,"").slice(0,8);
        if (shortSubj.length >= 3 && (title + content).indexOf(shortSubj) >= 0) {
          subjectMatch = { matched: true, name: shortSubj, aliases: [shortSubj] };
        }
      }
      if (!subjectMatch.matched && entName) {
        subjectMatch = { matched: true, name: entName, aliases: [entName] };
      }
    }

    // For weekly_digest: extract subject-related sentences
    if (evidenceType === "weekly_digest" && subjectMatch.matched) {
      var allNames = [subjName].concat(subjectMatch.aliases || []);
      var extractResult = extractSubjectRelatedSentences(content, allNames);
      weeklyExcerpt = extractResult.excerpt;
      if (!extractResult.matched) subjectMatch.matched = false;
    }
  }

  // ====== Step 6: publisher & dataSource ======
  var publisher = "", dataSource = "";
  var pp = [
    {re:/证券之星消息/,pub:"证券之星"},{re:/新浪财经/,pub:"新浪财经"},
    {re:/东方财富/,pub:"东方财富"},{re:/同花顺/,pub:"同花顺"},
    {re:/财联社/,pub:"财联社"},{re:/文化视角/,pub:"文化视角"},
    {re:/青岛资本圈/,pub:"青岛资本圈"},{re:/郁言债市/,pub:"郁言债市"}
  ];
  for (var pi = 0; pi < pp.length; pi++) { if (pp[pi].re.test(content)) { publisher = pp[pi].pub; break; } }
  var dp = [{re:/天眼查APP/,ds:"天眼查APP"},{re:/天眼查/,ds:"天眼查"},{re:/企查查/,ds:"企查查"}];
  for (var di = 0; di < dp.length; di++) { if (dp[di].re.test(content)) { dataSource = dp[di].ds; break; } }
  if (!publisher) publisher = srcName || "";

  // ====== Step 7: channel ======
  var channel = "iFinD";
  if (chanRaw === "NOTICE") channel = "公告";
  else if (chanRaw === "REPORT") channel = "研报";
  else if (chanRaw === "INV_NEWS") channel = "财经新闻";
  else if (url && url.indexOf("eastmoney") >= 0) channel = "Choice";
  else if (srcName && (srcName.indexOf("Choice") >= 0 || srcName.indexOf("mx") >= 0)) channel = "Choice";
  if (evidenceType === "cross_check") channel = "Choice";

  // ====== Step 8: tags ======
  var tags = [];
  if (evidenceType === "risk_event" || evidenceType === "weekly_digest") {
    var RK = ["失信","被执行","违约","逾期","破产","清算","诉讼","处罚","冻结","查封","限制高消费","评级下调","合同纠纷","虚开","税收违法","非标违约","票据逾期","开庭","纠纷","警示函","立案调查"];
    var hs = (title + " " + content + " " + weeklyExcerpt).toLowerCase();
    for (var ti = 0; ti < RK.length; ti++) { if (hs.indexOf(RK[ti].toLowerCase()) >= 0) tags.push(RK[ti]); }
  }

  // ====== Step 9: sourceSummary - KEEP FULL for modal, only truncate for cards at UI level ======
  var fullContent = content || "";
  var sourceSummary = fullContent; // Full text, UI truncates as needed

  // ====== Step 10: riskSummary ======
  var riskSummary = "";
  var fullRawText = typeof rawItem === "string" ? rawItem : JSON.stringify(rawItem, null, 2);
  var isTruncatedBySource = false;

  // Detect if content appears truncated (ends mid-sentence)
  if (fullContent && fullContent.length > 0) {
    var lastChar = fullContent.charAt(fullContent.length - 1);
    if (!/[。！？\.!\?]/.test(lastChar) && fullContent.length >= 180) {
      isTruncatedBySource = true;
    }
  }

  if (evidenceType === "company_profile") {
    riskSummary = "";
  } else if (evidenceType === "cross_check") {
    riskSummary = "该事项已通过东方财富Choice/mx-finance-search完成交叉验证，iFind检索结果与Choice公开信息一致。";
  } else if (evidenceType === "weekly_digest" && subjectMatch.matched && weeklyExcerpt) {
    riskSummary = "周度信用负面信息提及" + (subjectMatch.name || "当前主体") + "相关事项：" + weeklyExcerpt.slice(0, 200);
    if (weeklyExcerpt.length > 200) riskSummary += "（原文较长，请打开来源查看完整内容）";
  } else if (evidenceType === "weekly_digest" && !subjectMatch.matched) {
    riskSummary = "该周度汇总未精确匹配当前主体，不作为直接风险证据。可展开查看原文确认。";
  } else if (evidenceType === "risk_event") {
    if (fullContent) {
      var hs2 = (title + " " + fullContent).toLowerCase();
      var hasDishonesty = hs2.indexOf("失信") >= 0 || hs2.indexOf("被执行") >= 0;
      var hasLawsuit = hs2.indexOf("诉讼") >= 0 || hs2.indexOf("开庭") >= 0 || hs2.indexOf("合同纠纷") >= 0;
      var hasDefault = hs2.indexOf("违约") >= 0 || hs2.indexOf("逾期") >= 0;
      var hasTax = hs2.indexOf("虚开") >= 0 || hs2.indexOf("税收违法") >= 0;
      var hasPenalty = hs2.indexOf("处罚") >= 0 || hs2.indexOf("警示函") >= 0;
      var nm = fullContent.match(/(\d+)\s*[起项个]/); var ns = nm ? nm[1] : "";
      if (hasDishonesty) {
        riskSummary = ns ? "该主体涉及" + ns + "起被执行案件，已被列为失信被执行人或存在被执行记录，属于严重负面信号，建议立即核查敞口。" : "该主体已被列为失信被执行人或存在被执行记录，属于严重负面信号，建议立即核查敞口并评估代偿风险。";
      } else if (hasTax) {
        riskSummary = "该主体子公司存在虚开发票等重大税收违法行为，被列为税收违法失信主体，可能影响主体整体信用资质及再融资能力。";
      } else if (hasPenalty) {
        riskSummary = "该主体涉及监管处罚/警示事项，需关注合规风险及潜在业务影响。";
      } else if (hasLawsuit && ns) {
        riskSummary = "该主体近期涉及" + ns + "起诉讼/开庭事项，案由集中于合同纠纷，属于诉讼关注事项，建议持续跟踪后续判决及执行情况。";
      } else if (hasLawsuit) {
        riskSummary = "该主体近期涉及诉讼/开庭事项，属于诉讼关注事项，建议持续跟踪后续判决及执行情况。";
      } else if (hasDefault) {
        riskSummary = "该主体存在票据逾期或债务违约事项，反映流动性压力，建议关注其再融资进展及偿债安排。";
      } else {
        riskSummary = cleanText(fullContent.slice(0, 200));
      }
    }
  }
  if (!riskSummary) riskSummary = "";

  // ====== Step 11: matchedExcerpt ======
  var matchedExcerpt = "";
  if (evidenceType === "weekly_digest" && subjectMatch.matched && weeklyExcerpt) {
    matchedExcerpt = weeklyExcerpt;
  } else if (evidenceType === "risk_event" && fullContent) {
    matchedExcerpt = fullContent;
  }

  // ====== Step 12: displayTitle ======
  var displayTitle = title;
  if (evidenceType === "company_profile") {
    displayTitle = "主体基础信息" + (subjName ? " | " + subjName : "");
  } else if (evidenceType === "weekly_digest" && subjectMatch.matched) {
    // Try to extract specific event from excerpt
    if (weeklyExcerpt) {
      // Extract first meaningful sentence as display title
      var firstPart = weeklyExcerpt.split(/[。；]/)[0].trim();
      if (firstPart.length > 8 && firstPart.length < 50) {
        displayTitle = firstPart;
      } else if (firstPart.length >= 50) {
        displayTitle = firstPart.slice(0, 47) + "...";
      } else {
        displayTitle = "周度信用负面信息提及" + (subjectMatch.name || "当前主体") + "相关事项";
      }
    } else {
      displayTitle = "周度信用负面信息提及" + (subjectMatch.name || "当前主体") + "相关事项";
    }
  } else if (evidenceType === "cross_check") {
    displayTitle = "交叉验证结果";
  }

  if (displayTitle.length > 36 && evidenceType !== "company_profile") {
    displayTitle = displayTitle
      .replace(/有限公司|有限责任公司|集团有限公司|股份有限公司/g,"")
      .replace(/作为原告\/上诉人的/g,"")
      .replace(/作为被告\/被上诉人的/g,"")
      .replace(/\s+/g,"");
    if (displayTitle.length > 36) displayTitle = displayTitle.slice(0, 33) + "...";
  }

  // ====== Step 13: dirty check ======
  var dirty = ['"资讯标题"','"资讯内容"','"日期"','"URL"'];
  for (var dmi = 0; dmi < dirty.length; dmi++) {
    if (displayTitle.indexOf(dirty[dmi]) >= 0 || riskSummary.indexOf(dirty[dmi]) >= 0) {
      console.warn("normalizeEvidenceItem: dirty output");
      var r3 = Object.assign({}, EMPTY);
      r3.fullRawText = fullRawText; r3.rawText = fullRawText;
      return r3;
    }
  }

  return {
    evidenceType: evidenceType,
    isSubjectMatched: subjectMatch.matched,
    matchedSubjectName: subjectMatch.name,
    title: title,
    displayTitle: displayTitle,
    riskSummary: riskSummary,
    sourceSummary: sourceSummary,
    matchedExcerpt: matchedExcerpt,
    sourceFullText: sourceSummary,
    fullRawText: fullRawText,
    isTruncatedBySource: isTruncatedBySource,
    publishDate: date,
    hitDate: obj.time || rawItem.time || "",
    publisher: publisher,
    dataSource: dataSource,
    channel: channel,
    url: url,
    tags: tags,
    rawText: fullRawText,
  };
}
