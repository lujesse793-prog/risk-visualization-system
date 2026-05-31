#!/usr/bin/env python3
"""
public_supplement.py - 公开信息补充搜索工具
用法: python public_supplement.py <公司名1> [公司名2...]
功能:
1. 从 iFinD / mx-skill 导出数据中检测被截断的记录
2. 通过公开网页搜索获取完整原文
3. 生成补充 JSON 供合并使用
"""

import json, os, re, sys, time, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
OUTPUT_PATH = WORKSPACE / "data" / "public_supplement.json"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TRUNCATION_MARKERS = ["...", "......", ".....", "…..."]

def is_truncated(text):
    """检查文本是否在末尾被截断"""
    if not text or len(text) < 50:
        return False
    last_50 = text[-50:]
    for marker in TRUNCATION_MARKERS:
        if last_50.strip().endswith(marker):
            return True
    # 检查是否以不完整的句子结尾
    if not re.search(r'[。！？.!?]$', text.strip()):
        if len(text) > 200:
            # 长文本未以句号结尾，可能被截断
            return True
    return False

def fetch_page(url, timeout=15):
    """抓取网页内容"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [WARN] fetch failed: {url[:80]} - {e}")
        return None

def extract_text(html):
    """从HTML中提取正文"""
    # 移除script和style
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
    # 移除标签
    text = re.sub(r'<[^>]+>', '\n', html)
    # 清理空白
    text = re.sub(r'\n\s*\n+', '\n', text)
    lines = [l.strip() for l in text.split('\n') if l.strip() and len(l.strip()) > 15]
    return '\n'.join(lines)

def search_bing(query, max_results=5):
    """通过Bing搜索"""
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}"
    html = fetch_page(url)
    if not html:
        return []
    
    urls = re.findall(r'<cite[^>]*>(.*?)</cite>', html, re.DOTALL)
    results = []
    for u in urls:
        clean = re.sub(r'<[^>]+>', '', u).strip()
        if clean and not any(x in clean for x in ['microsoft.com', 'bing.com']):
            results.append(clean)
    return results[:max_results]

def supplement_subject(subject_name, articles):
    """为单个主体补充数据"""
    supplements = []
    for art in articles:
        title = art.get("title") or art.get("资讯标题", "")
        content = art.get("content") or art.get("资讯内容", "")
        url = art.get("url") or art.get("URL") or art.get("jumpUrl", "")
        
        if not is_truncated(content):
            continue
        
        print(f"  [TRUNCATED] {title[:60]}... ({len(content)} chars)")
        
        # 尝试从URL获取全文
        full_text = None
        if url:
            html = fetch_page(url)
            if html:
                full_text = extract_text(html)
                if full_text and len(full_text) > len(content) * 1.5:
                    print(f"    -> Got full text: {len(full_text)} chars")
                else:
                    full_text = None
        
        if full_text:
            supplements.append({
                "source": "web_fetch",
                "url": url,
                "title": title,
                "originalLength": len(content),
                "fullLength": len(full_text),
                "fullText": full_text[:5000],  # cap at 5000 chars
                "date": art.get("date") or art.get("日期") or art.get("time", ""),
            })
    
    return supplements

def main():
    subjects = sys.argv[1:] if len(sys.argv) > 1 else []
    if not subjects:
        print("用法: python public_supplement.py <公司名1> [公司名2...]")
        return
    
    result = {
        "generatedAt": datetime.now().isoformat(),
        "method": "public_web_search_supplement",
        "subjects": {}
    }
    
    for subject in subjects:
        print(f"\n=== {subject} ===")
        # 这里可以接入现有数据源
        # 当前仅做框架搭建
        result["subjects"][subject] = {
            "note": "请手动配置或接入数据源",
            "supplements": []
        }
    
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n输出: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
