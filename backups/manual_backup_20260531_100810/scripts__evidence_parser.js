// 证据解析器 v4 - 完整数据链路：rawEvidence -> parsedEvidence -> displayEvidence -> riskConclusion
// 禁止截断原始数据，区分摘要/全文，标记获取状态与来源可靠性

function normalizeEvidenceItem(rawItem, currentSubjectName) {
  // ====== 生成唯一 evidenceId ======
  var genId = function() {
    return "ev_" + Date.now().toString(36) + "_" + Math.random().toString(36).slice(2, 8);
  };

  // ====== EMPTY 模板：所有字段必须有默认值 ======
  var EMPTY = {
    evidenceId: genId(),
    evidenceType: "raw_unknown",
    subjectMatched: false,
    matchedSubjectName: "",
    // 获取状态：full_text | snippet_only | source_blocked | login_required | unknown
    accessLevel: "unknown",
    // 来源可靠性：verified | reliable | moderate | uncertain
    sourceReliability: "uncertain",
    // 展示字段
    title: "",
    displayTitle: "",
    riskSummary: "",
    cardSummary: "",
    matchedExcerpt: "",
    sourceFullText: "",
    fullRawText: "",
    // 标记
    isTruncatedBySource: false,
    parseStatus: "ok",
    warning: "",
    // 元信息
    publishDate: "", hitDate: "",
    publisher: "", dataSource: "", channel: "未知",
    url: "", tags: [],
    rawText: ""
  };

  if (!rawItem) {
    var empty = Object.assign({}, EMPTY);
    empty.parseStatus = "empty_input";
    empty.warning = "输入数据为空";
    return empty;
  }
  if (typeof rawItem !== "object") {
    console.warn("normalizeEvidenceItem: non-object input");
    var r = Object.assign({}, EMPTY);
    r.fullRawText = String(rawItem);
    r.rawText = String(rawItem);
    r.parseStatus = "non_object";
    r.warning = "输入非结构化数据";
    return r;
  }

  var SUMMARY_END_PUNCT_RE = /(?:[。.!！？!?…]|\.{3}|……)$/;
  var RISK_SUMMARY_TERMS = ["行政处罚", "重大行政处罚", "税收违法", "失信", "被执行", "虚开", "诉讼", "开庭", "违约", "逾期", "评级关注", "评级观察", "警示函", "处罚", "债务", "担保", "冻结", "执行"];
  var BACKGROUND_SUMMARY_TERMS = ["成立于", "注册资本", "主营业务", "中国企业500强", "企业500强", "AAA级", "AAA 级", "下设", "一级子公司", "控股或参股", "历史沿革", "正式更名", "组建成立", "获评", "跻身", "公司简介", "资料显示"];

  var ensureTextEnding = function(t) {
    t = String(t || "").trim().replace(/[，,、；;：:\s]+$/g, "");
    if (t && !SUMMARY_END_PUNCT_RE.test(t)) t += "。";
    return t;
  };

  var repairKnownPublicTextAbbreviations = function(t) {
    return String(t || "")
      .replace(/\bq\s*d\b(?=(市委|市政府|市国资|国资|海发|西海岸|资本|城投|[，,。；;]))/gi, "青岛")
      .replace(/\bqd(?=(市委|市政府|市国资|国资|海发|西海岸|资本|城投|[，,。；;]))/gi, "青岛");
  };

  var hasAnyTerm = function(text, terms) {
    text = String(text || "");
    for (var ti = 0; ti < terms.length; ti++) {
      if (text.indexOf(terms[ti]) >= 0) return true;
    }
    return false;
  };

  var focusedRiskSummary = function(text, subjectName) {
    var cleaned = cleanText(text);
    if (!cleaned) return "";
    var parts = cleaned.match(/[^。！？!?]+[。！？!?]?/g) || [cleaned];
    var chosen = [];
    var seen = {};
    var total = 0;
    for (var pi = 0; pi < parts.length; pi++) {
      var sentence = ensureTextEnding(parts[pi]);
      var key = sentence.replace(/\s+/g, "");
      if (!key || seen[key]) continue;
      seen[key] = true;
      var hasRisk = hasAnyTerm(sentence, RISK_SUMMARY_TERMS);
      var isBackground = hasAnyTerm(sentence, BACKGROUND_SUMMARY_TERMS) && !hasRisk;
      if (isBackground) continue;
      var score = 0;
      if (subjectName && sentence.indexOf(subjectName) >= 0) score += 2;
      if (hasRisk) score += 4;
      if (/(\d+(?:\.\d+)?\s*(亿元|万元|起|项|笔|%|％))/.test(sentence)) score += 2;
      if (/子公司|旗下|控股|持股|担保|关联|同一控制|股权|上游|下游/.test(sentence)) score += 2;
      if (/信用资质|融资能力|偿债|声誉|再融资|不利影响|整改|披露|持续关注|建议/.test(sentence)) score += 2;
      if (score <= 0 && chosen.length > 0) continue;
      if (chosen.length >= 3) continue;
      if (total + sentence.length > 190 && chosen.length > 0) continue;
      chosen.push(sentence);
      total += sentence.length;
    }
    if (!chosen.length) chosen.push(ensureTextEnding(parts[0]));
    var summary = chosen.join("");
    if (summary.length > 220) {
      var beforeLimit = summary.slice(0, 190);
      var lastEnd = Math.max(beforeLimit.lastIndexOf("。"), beforeLimit.lastIndexOf("！"), beforeLimit.lastIndexOf("？"), beforeLimit.lastIndexOf("."), beforeLimit.lastIndexOf("!"), beforeLimit.lastIndexOf("?"));
      summary = lastEnd >= 80 ? beforeLimit.slice(0, lastEnd + 1) : beforeLimit.replace(/[，,、；;：:\s]+[^，,、；;：:]*$/g, "");
    }
    return ensureTextEnding(summary);
  };

  // ====== cleanText: 清洗但保留完整长度，禁止截断 ======
  var cleanText = function(t) {
    if (!t || typeof t !== "string") return "";
    t = t.replace(/<[^>]+>/g, " ").replace(/&nbsp;|&#160;/gi, " ").replace(/\u00a0/g, " ");
    t = repairKnownPublicTextAbbreviations(t);
    t = t.replace(/详细内容如下[\(\（][^）\)]*[）\)]?[：:]?/g,"").replace(/详细内容如下[：:]/g,"").replace(/前\d+条[：:]?/g,"");
    t = t.replace(/以上内容为.*?(不构成投资建议|不作投资参考|投资建议|AI算法生成|证券之星据公开信息整理)[^。]*[。]?/g,"");
    t = t.replace(/网信算备[^。\n]*[。]?/g,"");
    t = t.replace(/mx-finance-search接口已完成[^。！？!?]*[。！？!?]?/gi, " ");
    t = t.replace(/公开信息交叉验证已完成[^。！？!?]*[。！？!?]?/gi, " ");
    t = t.replace(/详见运行报告中[^。！？!?]*[。！？!?]?/gi, " ");
    t = t.replace(/[。，；：、]{2,}/g,function(m){return m[0];});
    t = t.replace(/[，；：、]\s*[。]/g,"。").replace(/[。]\s*[，；：、]/g,"。");
    t = t.replace(/^[，；：、。\s]+/g,"").replace(/[，；：、\s]+$/g,"");
    return ensureTextEnding(t.replace(/\s+/g," ").trim());
  };

  // ====== detectAccessLevel: 检测数据获取完整度 ======
  var detectAccessLevel = function(text, source) {
    if (!text || text.length === 0) return "unknown";
    var s = String(source || "").toLowerCase();
    // 公开信息抓取到的全文
    if (s.indexOf("公开信息") >= 0 || s.indexOf("web_fetch") >= 0) return "full_text";
    // 检查是否以截断标记结尾
    var trimmed = text.trim();
    if (/[\.。…]{3,}$/.test(trimmed) || /…+$/.test(trimmed)) return "snippet_only";
    // 检查长度：过短的可能是摘要
    if (text.length < 150 && !/[。！？]$/.test(trimmed)) return "snippet_only";
    // 检查是否以不完整句子结尾
    if (text.length > 200 && !/[。！？.!?]$/.test(trimmed)) return "snippet_only";
    // MCP/skill 返回通常 ~500 字符，应检查是否有完整结尾
    if (text.length >= 480 && text.length <= 520) {
      if (!/[。！？.!?]$/.test(trimmed)) return "snippet_only";
    }
    return "full_text";
  };

  // ====== detectSourceReliability ======
  var detectSourceReliability = function(source, channel, publisher) {
    var s = (source + " " + channel + " " + (publisher || "")).toLowerCase();
    if (s.indexOf("公开信息") >= 0 || s.indexOf("web_fetch") >= 0) return "verified";
    if (s.indexOf("ifind") >= 0 || s.indexOf("choice") >= 0 || s.indexOf("同花顺") >= 0 || s.indexOf("东方财富") >= 0) return "reliable";
    if (s.indexOf("财经") >= 0 || s.indexOf("证券") >= 0 || s.indexOf("新闻") >= 0) return "moderate";
    return "uncertain";
  };

  // ====== cleanWeeklyDigestText ======
  var cleanWeeklyDigestText = function(t) {
    if (!t || typeof t !== "string") return "";
    t = t.replace(/0\d\s*(城投|产业债|金融债|地方债|公司债|企业债|ABS|信用债|可转债|中期票据|短融)/g, "");
    t = t.replace(/信用负面信息[：:\s]*/g, "");
    t = t.replace(/来源[：:]\s*\S+信用负面信息/g, "");
    t = t.replace(/来源[：:]\s*\S+/g, "");
    t = t.replace(/[\.。]{3,}$/g, "").replace(/…+$/g, "").replace(/\.\.\.+$/g, "");
    t = t.replace(/[。，；：、]{2,}/g, function(m){ return m[0]; });
    t = t.replace(/[，；：、]\s*[。]/g, "。").replace(/[。]\s*[，；：、]/g, "。");
    t = t.replace(/^[，；：、。\s]+/g, "").replace(/[，；：、\s]+$/g, "");
    if (t.length > 0 && !/[。！？]$/.test(t)) t += "。";
    return t.replace(/\s+/g, " ").trim();
  };

  // ====== extractSubjectRelatedSentences ======
  var extractSubjectRelatedSentences = function(text, names) {
    if (!text || !names || names.length === 0) return { excerpt: "", matched: false };
    var items = text.split(/(?=\d+[\.、）\)]\s*)/);
    var matched = [];
    var allNames = names.slice();
    for (var i = 0; i < items.length; i++) {
      var item = items[i].trim();
      if (!item) continue;
      var hit = false;
      for (var ni = 0; ni < allNames.length; ni++) {
        if (item.indexOf(allNames[ni]) >= 0) { hit = true; break; }
      }
      if (hit) {
        var cleaned = item.replace(/^\d+[\.、）\)]\s*/, "").trim();
        cleaned = cleaned.replace(/\d+[\.、）\)]\s*[\s\S]*$/, "").trim();
        cleaned = cleanWeeklyDigestText(cleaned);
        if (cleaned.length > 3) matched.push(cleaned);
      }
    }
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
    if (short.length >= 3 && text.indexOf(short) >= 0) aliases.push(short);
    var city = name.replace(/市.*$/, "").replace(/县.*$/, "").replace(/区.*$/, "");
    if (city.length >= 2) {
      var rest = short.replace(city, "");
      if (rest.length >= 2) aliases.push(city.replace(/[市州县区]$/, "") + rest.slice(0, Math.min(4, rest.length)));
      if (rest.length >= 4) aliases.push(city.replace(/[市州县区]$/, "") + rest.slice(0, 2));
    }
    var nameNoSpace = name.replace(/\s+/g, "");
    if (text.indexOf(nameNoSpace) >= 0) aliases.push(nameNoSpace);
    for (var ai = 0; ai < aliases.length; ai++) {
      if (text.indexOf(aliases[ai]) >= 0) return { matched: true, name: aliases[ai], aliases: aliases };
    }
    return { matched: false, name: "", aliases: aliases };
  };

  // ====== classifyEvidenceType ======
  var classifyEvidenceType = function(item) {
    var combined = ((item.title || "") + " " + (item.content || item.summary || item.text || "")).toLowerCase();
    if (combined.indexOf("周报") >= 0 || combined.indexOf("周度") >= 0 || combined.indexOf("weekly") >= 0) return "weekly_digest";
    if (combined.indexOf("交叉验证") >= 0 || combined.indexOf("cross") >= 0) return "cross_check";
    if (combined.indexOf("主体基础信息") >= 0 || combined.indexOf("公司简介") >= 0 || combined.indexOf("企业信息") >= 0) return "company_profile";
    if (combined.indexOf("诉讼") >= 0 || combined.indexOf("被执行") >= 0 || combined.indexOf("处罚") >= 0 || combined.indexOf("违约") >= 0 || combined.indexOf("逾期") >= 0 || combined.indexOf("失信") >= 0 || combined.indexOf("虚开") >= 0 || combined.indexOf("风险") >= 0) return "risk_event";
    return "raw_unknown";
  };

  // ====== MAIN PARSING ======
  var obj = rawItem;
  if (typeof rawItem === "string") {
    try { obj = JSON.parse(rawItem); } catch(e) {}
    if (typeof obj !== "object") obj = rawItem;
  }

  // Extract fields
  var gf = function(keys) {
    for (var ki = 0; ki < keys.length; ki++) {
      var v = obj[keys[ki]];
      if (v !== undefined && v !== null && v !== "") return String(v);
    }
    return "";
  };

  var subjName = String(currentSubjectName || "").trim();
  var title = gf(["title","资讯标题","名称","标题","Title","name"]);
  var content = gf(["content","资讯内容","正文","内容","summary","text","detail"]);
  var date = gf(["date","日期","publishDate","time","发布时间","publish_date"]);
  var url = gf(["url","URL","jumpUrl","链接","sourceUrl","href"]);
  var publisher = gf(["publisher","来源","source","author","发布机构"]);
  var channel = gf(["channel","informationType","渠道","type"]);
  var source = gf(["source","dataSource"]);
  var tags = [];
  if (obj.tags && Array.isArray(obj.tags)) tags = obj.tags;
  else if (obj.keywords && Array.isArray(obj.keywords)) tags = obj.keywords;

  // ====== 保留完整原始数据，禁止截断 ======
  var fullRawText = "";
  try {
    fullRawText = JSON.stringify(rawItem, null, 2);
  } catch(e) {
    fullRawText = String(rawItem);
  }

  // ====== 清洗内容，保留完整长度 ======
  var fullContent = cleanText(content);
  var evidenceType = classifyEvidenceType(obj);
  var isTruncatedBySource = false;

  // 检测源数据截断
  if (fullContent.length > 50) {
    var trimmedContent = fullContent.trim();
    if (/[\.。…]{3,}$/.test(trimmedContent) || /…+$/.test(trimmedContent)) {
      isTruncatedBySource = true;
    } else if (fullContent.length >= 480 && fullContent.length <= 520 && !/[。！？.!?]$/.test(trimmedContent)) {
      isTruncatedBySource = true;
    }
  }

  // ====== 主体匹配 ======
  var subjectMatch = matchSubject(fullContent + " " + title, subjName);

  // ====== 周报处理 ======
  var weeklyExcerpt = "";
  if (evidenceType === "weekly_digest" && subjectMatch.matched) {
    var names = subjectMatch.aliases.length > 0 ? subjectMatch.aliases : [subjName];
    var result = extractSubjectRelatedSentences(fullContent, names);
    if (result.matched) weeklyExcerpt = result.excerpt;
  }

  // ====== evidenceType 重新确认 ======
  if (!subjectMatch.matched && evidenceType === "weekly_digest") {
    var subjShort = subjName.replace(/有限公司|有限责任公司|集团有限公司|股份有限公司/,"").slice(0,8);
    if (fullContent.indexOf(subjShort) < 0 && weeklyExcerpt.length === 0) {
      evidenceType = "weekly_digest"; // Keep type but mark unmatched
    }
  }

  // ====== channel 标准化 ======
  if (!channel || channel === "") {
    if (obj.informationType) channel = obj.informationType;
    else if (url && url.indexOf("weixin") >= 0) channel = "微信公众号";
    else if (url && url.indexOf("sina") >= 0) channel = "新浪财经";
    else if (url && url.indexOf("sohu") >= 0) channel = "搜狐";
    else if (url && url.indexOf("163.com") >= 0) channel = "网易";
    else if (url && url.indexOf("baijiahao") >= 0) channel = "百家号";
    else if (url && url.indexOf("toutiao") >= 0) channel = "今日头条";
    else if (publisher) channel = publisher;
    else channel = "未知来源";
  }
  if (!publisher && source) publisher = source;

  // ====== accessLevel 检测 ======
  var sourceForAccess = (obj.source || "") + " " + (channel || "");
  var accessLevel = detectAccessLevel(fullContent, sourceForAccess);
  // 如果 source 明确标记，优先使用
  if (obj.accessLevel) accessLevel = obj.accessLevel;
  // 公开信息默认 full_text（已人工/脚本验证）
  if (String(obj.source || "").indexOf("公开信息") >= 0) accessLevel = "full_text";

  // ====== sourceReliability 检测 ======
  var sourceReliability = detectSourceReliability(source, channel, publisher);

  // ====== cardSummary（卡片摘要，可以截断） ======
  var cardSummary = focusedRiskSummary(fullContent, subjName) || fullContent;
  if (cardSummary.length > 120) {
    cardSummary = ensureTextEnding(cardSummary.slice(0, 117).replace(/[，,、；;：:\s]+[^，,、；;：:]*$/g, ""));
  }

  // ====== riskSummary（风控摘要，不再截断） ======
  var riskSummary = "";
  if (evidenceType === "company_profile") {
    riskSummary = fullContent;
  } else if (evidenceType === "cross_check") {
    riskSummary = "已通过多渠道交叉验证，iFind检索结果与Choice公开信息一致。";
  } else if (evidenceType === "weekly_digest" && subjectMatch.matched) {
    riskSummary = "周度信用负面信息提及" + (subjectMatch.name || "当前主体") + "相关事项：" + (weeklyExcerpt || fullContent);
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
        riskSummary = focusedRiskSummary(fullContent, subjName);
      }
    }
  }
  if (!riskSummary) riskSummary = "";
  riskSummary = ensureTextEnding(riskSummary);

  // ====== matchedExcerpt（命中原文，保留完整） ======
  var matchedExcerpt = "";
  if (evidenceType === "weekly_digest" && subjectMatch.matched && weeklyExcerpt) {
    matchedExcerpt = weeklyExcerpt;
  } else if (evidenceType === "risk_event" && fullContent) {
    matchedExcerpt = fullContent;
  }

  // ====== sourceFullText（来源全文） ======
  var sourceSummary = fullContent; // 保留完整

  // ====== displayTitle（卡片短标题，可以截断） ======
  var displayTitle = title;
  if (evidenceType === "company_profile") {
    displayTitle = "主体基础信息" + (subjName ? " | " + subjName : "");
  } else if (evidenceType === "weekly_digest" && subjectMatch.matched) {
    if (weeklyExcerpt) {
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

  // ====== parseStatus 和 warning ======
  var parseStatus = "ok";
  var warning = "";
  if (isTruncatedBySource) {
    warning = "该来源仅获取到摘要，未获取完整原文，建议点击来源核验。";
    if (accessLevel === "full_text") accessLevel = "snippet_only";
  }
  if (!subjectMatch.matched && evidenceType !== "company_profile") {
    parseStatus = "subject_not_matched";
    if (!warning) warning = "未精确匹配当前主体，结果可能不相关。";
  }
  if (accessLevel === "snippet_only" && !warning) {
    warning = "该来源仅获取到摘要，未获取完整原文，建议点击来源核验。";
  }

  // ====== dirty check ======
  var dirty = ['"资讯标题"','"资讯内容"','"日期"','"URL"'];
  for (var dmi = 0; dmi < dirty.length; dmi++) {
    if (displayTitle.indexOf(dirty[dmi]) >= 0 || riskSummary.indexOf(dirty[dmi]) >= 0) {
      console.warn("normalizeEvidenceItem: dirty output");
      var r3 = Object.assign({}, EMPTY);
      r3.fullRawText = fullRawText; r3.rawText = fullRawText;
      r3.parseStatus = "dirty_output";
      r3.warning = "解析异常，请查看原始返回内容";
      return r3;
    }
  }

  return {
    evidenceId: genId(),
    evidenceType: evidenceType,
    subjectMatched: subjectMatch.matched,
    matchedSubjectName: subjectMatch.name,
    accessLevel: accessLevel,
    sourceReliability: sourceReliability,
    title: title,
    displayTitle: displayTitle,
    riskSummary: riskSummary,
    cardSummary: cardSummary,
    matchedExcerpt: matchedExcerpt,
    sourceFullText: sourceSummary,
    fullRawText: fullRawText,
    isTruncatedBySource: isTruncatedBySource,
    parseStatus: parseStatus,
    warning: warning,
    publishDate: date,
    hitDate: obj.time || rawItem.time || "",
    publisher: publisher,
    dataSource: source,
    channel: channel,
    url: url,
    tags: tags,
    rawText: fullRawText,
  };
}
