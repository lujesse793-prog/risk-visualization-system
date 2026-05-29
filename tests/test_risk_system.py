"""
贷后风险检测系统 - Playwright 自动化测试 (CDN镜像版)
"""
import sys, os, time, subprocess
from playwright.sync_api import sync_playwright

PROJECT_DIR = r"C:\Users\luyng\Documents\风控可视化系统"
PORT = 8765
BASE_URL = f"http://localhost:{PORT}"

# CDN 镜像映射 - 解决国内访问慢的问题
CDN_MIRRORS = {
    "cdn.tailwindcss.com": "cdn.bootcdn.net/ajax/libs/tailwindcss/3.4.17/tailwind.min.js",
    "unpkg.com/@babel/standalone/babel.min.js": "cdn.bootcdn.net/ajax/libs/babel-standalone/7.24.5/babel.min.js",
}

def start_server():
    os.chdir(PROJECT_DIR)
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(1.5)
    return proc

def main():
    server = start_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()

            # 拦截 CDN 请求, 重定向到国内镜像
            def handle_route(route):
                url = route.request.url
                for original, mirror in CDN_MIRRORS.items():
                    if original in url:
                        print(f"    [镜像] {original} -> {mirror}")
                        route.fulfill(status=301, headers={"Location": f"https://{mirror}"})
                        return
                route.continue_()

            page.route("**/*", handle_route)

            console_logs = []
            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            page_errors = []
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            print("=" * 60)
            print(" 贷后风险检测系统 - 自动化测试")
            print("=" * 60)

            # 打开页面, 等待加载
            print("\n[1] 正在加载页面...")
            page.goto(f"{BASE_URL}/index.html", wait_until="domcontentloaded", timeout=30000)
            print("    DOM 加载完成, 等待 React 渲染...")

            try:
                page.wait_for_selector("#root > *", timeout=45000)
                print("    React 渲染完成!")
            except:
                print("    React 未渲染, 尝试继续...")
            page.wait_for_timeout(2000)

            # 页面信息
            title = page.title()
            print(f"\n[2] 页面标题: {title}")

            # 元素统计
            print("\n[3] 元素统计:")
            for tag in ["button", "select", "input", "nav"]:
                count = page.locator(tag).count()
                print(f"    <{tag}>: {count} 个")

            # 控制台
            errors = [l for l in console_logs if "error" in l.lower()]
            print(f"\n[4] 控制台: {len(console_logs)} 条 (错误: {len(errors)})")
            for e in errors[:3]:
                print(f"    {e[:150]}")

            # 截图
            print("\n[5] 截图...")
            os.makedirs(os.path.join(PROJECT_DIR, "tests"), exist_ok=True)
            
            full = os.path.join(PROJECT_DIR, "tests", "screenshot_full.png")
            page.screenshot(path=full, full_page=True)
            print(f"    全页: {full}")

            fold = os.path.join(PROJECT_DIR, "tests", "screenshot_above_fold.png")
            page.screenshot(path=fold)
            print(f"    首屏: {fold}")

            print("\n" + "=" * 60)
            print(" 测试完成!")
            print("=" * 60)

            browser.close()
    finally:
        server.terminate()
        server.wait()

if __name__ == "__main__":
    main()
