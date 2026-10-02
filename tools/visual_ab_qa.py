"""Check real experiment deliverables and comparison interactions."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from lxml import html
from playwright.sync_api import sync_playwright
from tools.visual_ab_test import OUT, dump, sha


def main():
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    for record in manifest['files']:
        path=OUT/record['path']
        assert path.stat().st_size==record['bytes'] and sha(path)==record['sha256'],path
    doc=html.fromstring((OUT/'index.html').read_text(encoding='utf8'))
    links=[s for s in doc.xpath('//@src|//@href') if not s.startswith('#')]
    assert all((OUT/s).is_file() for s in links),links
    with sync_playwright() as pw:
        browser=pw.chromium.launch()
        web=browser.new_page(viewport={'width':1920,'height':1080})
        errors=[]
        web.on('pageerror',lambda err:errors.append(str(err)))
        web.goto((OUT/'index.html').as_uri())
        web.evaluate("document.querySelectorAll('.zoom img').forEach(x=>x.loading='eager')")
        web.wait_for_function("[...document.querySelectorAll('.zoom img')].every(x=>x.complete&&x.naturalWidth===1280)")
        assert web.locator('.sample').count()==6 and web.locator('.zoom img').count()==18
        web.locator('.reference').first.click()
        assert web.locator('dialog').is_visible()
        assert '完整生图' in web.locator('#caption').inner_text()
        web.locator('#close').click()
        web.locator('#preview').select_option('browser')
        web.wait_for_function("[...document.querySelectorAll('.zoom img')].every(x=>x.complete&&x.naturalWidth)")
        assert web.locator('img[data-route="B"]').first.get_attribute('src')=='B/browser01.png'
        web.locator('#preview').select_option('office')
        web.locator('.zoom').first.click()
        assert 'frozen/powerpoint/slide01.png' in web.locator('#large').get_attribute('src')
        web.locator('#close').click()
        web.locator('[data-pref="1"]').select_option('B')
        web.reload()
        assert web.locator('[data-pref="1"]').input_value()=='B'
        web.evaluate('localStorage.clear()')
        web.reload()
        web.screenshot(path=str(OUT/'comparison-preview.png'),full_page=False)
        web.set_viewport_size({'width':390,'height':844})
        assert web.evaluate('document.documentElement.scrollWidth<=390')
        assert not errors,errors
        browser.close()
    result=dict(status='passed',manifest_files_checked=len(manifest['files']),
                local_links_checked=len(links),comparison_pages=6,comparison_images=18,
                reference_modal=True,preview_switch=True,feedback_persistence=True,
                mobile_no_horizontal_overflow=True,user_preference_recorded=False)
    dump(OUT/'delivery_qa.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
