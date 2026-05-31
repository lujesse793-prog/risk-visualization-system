import pathlib
p = pathlib.Path('index.html')
content = p.read_text(encoding='utf-8')

if '{searchDetail && (' not in content:
    anchor = '            {actionModal && ('
    modal_file = pathlib.Path('scripts/search_detail_modal.txt')
    modal_text = modal_file.read_text(encoding='utf-8')
    content = content.replace(anchor, modal_text + anchor)
    p.write_text(content, encoding='utf-8')
    print('Modal inserted')
else:
    print('Modal already exists')
